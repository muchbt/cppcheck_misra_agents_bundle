# cppcheck + MISRA agent pipeline

一个纯 Python 3、跨 Windows/Linux 的工程内自包含方案，用于：

- 解析 `cppcheck.xml`
- 识别普通 cppcheck 与 MISRA 结果
- 按文件聚类并切 chunk
- 调用本地 agent（当前默认 `opencode` CLI）
- 记录 issue 状态、修改点、chunk 结果、统一运行日志
- 支持按 `年月日-序号` 的 `run_id` 归档
- 支持 `oneshot` 统一入口和默认续跑
- 通过 `.agents/` 统一管理，并自动生成兼容层

## 目录

- `.agents/config/*.json`：配置
- `.agents/prompts/*.txt`：prompt 模板
- `.agents/skills/*`：主 skill 源
- `.agents/tools/*.py`：工具脚本
- `.agents/runtime/*`：当前运行态、chunk、结果、日志
- `.agents/reports/*`：当前运行的中文报告
- `.agents/runs/<run_id>/*`：历史归档

## Agent 配置

`pipeline.json` 中的 `agent` 必须使用结构化配置，不再支持旧的 `type` / `command` 字符串模型。

当前配置内置了已兼容的 provider。用户日常只需要修改 `agent.provider`，其余 provider 配置保持不动。

默认配置如下：

```json
"agent": {
  "provider": "opencode",
  "staging_dir": ".agents/staging",
  "providers": {
    "codex": {
      "launch": {
        "argv": ["codex", "exec", "--full-auto"],
        "prompt_via": "stdin",
        "cwd": "project_root",
        "env": {
          "CODEX_HOME": ".agents/runtime/agent-home"
        },
        "requires_tty": false,
        "output": {
          "mode": "exit_code"
        }
      },
      "capabilities": {
        "non_interactive": true,
        "workspace_write_required": true
      }
    },
    "claude": {
      "launch": {
        "argv": ["claude", "-p", "--output-format", "text", "--permission-mode", "acceptEdits"],
        "prompt_via": "stdin",
        "cwd": "project_root",
        "env": {},
        "requires_tty": false,
        "output": {
          "mode": "exit_code"
        }
      },
      "capabilities": {
        "non_interactive": true,
        "workspace_write_required": true
      }
    },
    "opencode": {
      "launch": {
        "argv": ["opencode"],
        "prompt_via": "stdin",
        "cwd": "project_root",
        "env": {},
        "requires_tty": false,
        "output": {
          "mode": "exit_code"
        }
      },
      "capabilities": {
        "non_interactive": true,
        "workspace_write_required": true
      }
    }
  },
  "auto_bootstrap_compat": true
}
```

切换到 `Claude Code` 时，只需要把：

```json
"provider": "opencode"
```

改成：

```json
"provider": "claude"
```

切换到 `OpenCode` 时，只需要把：

```json
"provider": "codex"
```

改成：

```json
"provider": "opencode"
```

要求如下：

- 必须使用非交互命令形式；对 `codex` 来说，应使用 `codex exec`
- 对 `Claude Code` 来说，应使用 `claude -p` 一类非交互入口
- 对 `OpenCode` 来说，应使用 `opencode` 命令，运行时会自动设置 `XDG_DATA_HOME` 和 `XDG_STATE_HOME` 到工作区内的 `.opencode/` 目录
- `prompt_via` 当前推荐 `stdin`
- `CODEX_HOME` 这类运行目录应映射到工作区内可写路径
- `Claude Code` 的认证默认依赖本机 `claude auth login` 状态或运行环境中的 `ANTHROPIC_API_KEY`
- `OpenCode` 的认证依赖 OpenCode CLI 的全局配置，状态目录会自动隔离到工作区
- 运行时会优先复用 `~/.codex/auth.json` 和 `~/.codex/config.toml`，同步到工作区 `CODEX_HOME`
- 运行时会自动移除继承下来的 `CODEX_SANDBOX_NETWORK_DISABLED`，避免用户手动解除该环境变量
- `Claude Code` 通过 `--append-system-prompt` CLI 参数注入 cppcheck-misra-fix skill 指令，同时保留 `.claude/skills/` 目录作为 skill 元数据来源；推荐始终生成项目内兼容层，避免不同机器行为不一致
- 如果配置仍依赖交互式 TUI、TTY 或不可写运行目录，`doctor` 会直接报阻塞错误

**Provider 环境配置策略差异：**

- `codex`：需要 `CODEX_HOME` 指向工作区内可写目录，用于存放认证文件 (`auth.json`) 和配置 (`config.toml`)。运行时会自动从 `~/.codex/` 复制到工作区。
- `claude`：认证依赖本机 `claude auth login` 或环境变量 `ANTHROPIC_API_KEY`，不需要额外工作区目录配置。`env` 字段可保持为空对象 `{}`。
- `opencode`：运行时会自动设置 `XDG_DATA_HOME` 和 `XDG_STATE_HOME` 环境变量，分别指向工作区内的 `.opencode/data` 和 `.opencode/state` 目录。这样可以将 OpenCode 的状态（如配置、缓存、日志）隔离在项目工作区内，避免污染用户全局 `~/.local/share/` 和 `~/.local/state/` 目录。认证依赖 OpenCode CLI 的全局配置，无需在 `env` 中额外指定。
- `opencode`：常见 `connection refused`、`dial tcp`、`timed out` 或 `zen/v1/messages` 请求失败会在运行时归类为 `network_error`，优先检查外网连通性和 OpenCode 服务可达性。

## 推荐用法

首次接入、环境异常、命令失败时，先运行：

```bash
python3 .agents/tools/pipeline_cli.py doctor
```

日常使用推荐直接运行：

```bash
python3 .agents/tools/pipeline_cli.py oneshot
```

`oneshot` 会自动完成：

1. 预检查
2. `split`
3. `run`
4. `merge`

如果检测到已有未完成运行，`oneshot` 会默认续跑，并打印当前 `run_id`、状态和进度摘要。

## fresh 与续跑

默认情况下，只要 `.agents/runtime/progress.json` 的状态是 `ready`、`running`、`partial` 或 `failed`，`oneshot` 就会续跑。

强制从头开始时使用：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh
```

需要显式切换策略时，也应配合 `--fresh`：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --strategy all_auto
```

需要指定本次 fresh 运行的编号时：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --run-id 20260423-001
```

注意：`--run-id` 参数仅在 `--fresh` 模式下有效。续跑模式会使用已有 `progress.json` 中的 `run_id`，传入不一致的 `--run-id` 会触发错误提示。

如果在续跑模式传入与当前运行态不一致的 `--strategy` 或 `--run-id`，命令会提前退出，并提示改用 `--fresh`。

## 分步命令

需要拆开执行时，可继续使用统一入口：

```bash
python3 .agents/tools/pipeline_cli.py split --strategy conservative
python3 .agents/tools/pipeline_cli.py run --strategy conservative
python3 .agents/tools/pipeline_cli.py merge
```

也可以直接调用工具脚本：

```bash
python3 .agents/tools/split_cppcheck_xml.py --strategy conservative
python3 .agents/tools/run_fix_pipeline.py --strategy conservative
python3 .agents/tools/merge_results.py
```

Windows 下可用：

```bat
py .agents\tools\pipeline_cli.py doctor
py .agents\tools\pipeline_cli.py oneshot
```

## 自动修复策略

默认策略是 `conservative`：

- 只自动修复高置信度、局部可判定的问题
- 高风险 MISRA / volatile / interrupt / register / RTE / MCAL 等问题标记为 `needs_manual_review`

如需让 agent 尝试修复更多问题，可显式使用 `all_auto`：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --strategy all_auto
```

`all_auto` 会把高风险问题也分发给 agent，但结果必须保留 `risk_level`、`risk_reason` 和 `review_required_after_fix=true`。高风险自动修复不代表免人工复核。

## 运行日志

当前运行的日志位于：

- `.agents/runtime/pipeline.log`
- `.agents/runtime/run_log.jsonl`

其中：

- `pipeline.log` 适合人工快速阅读
- `run_log.jsonl` 适合脚本消费和后续扩展

`split`、`run`、`oneshot` 都会写统一事件日志。fresh split 会重置当前运行的日志文件。

## 中文报告

每次 `merge` 会生成：

- `.agents/reports/final_summary.md`
- `.agents/reports/final_summary.json`
- `.agents/reports/review_checklist.md`
- `.agents/reports/run_manifest.json`

其中：

- `final_summary.md` 面向人工 review，使用简体中文，并在首次出现时保留关键英文原文，例如“需人工复核（needs manual review）”
- `review_checklist.md` 会列出需重点人工复核的问题、文件、规则、状态和 `edit_id`
- `run_manifest.json` 会记录 `run_id`、开始/结束/归档时间、输入 XML、策略、chunk 统计和报告路径

## 归档

每次 `merge` 后，当前运行会复制到：

```text
.agents/runs/<run_id>/
```

归档内容包括：

- `runtime/`：运行态 JSON、chunk、结果
- `reports/`：中文总结、复核清单、manifest
- `logs/`：`pipeline.log` 与 `run_log.jsonl`

## 验证说明

`verify_chunk.py` 默认只记录轻量验证结果。

如果 `pipeline.json` 中没有配置 `verification.custom_command`，报告会明确写“未执行工程级验证”，不会把轻量验证表述成工程级验证成功。

如果配置了 `verification.custom_command`，对应结果会记录在每个 chunk 的 `verification` 字段中，并汇总进中文报告。

## bootstrap_agents.py

用于同步兼容层：

```bash
python3 .agents/tools/bootstrap_agents.py --mode merge
```

模式说明：

- `--mode merge`：默认；对 `AGENTS.md` 使用标记块替换/追加，对 `.codex/skills/.../SKILL.md` 和 `.claude/skills/.../SKILL.md` 执行同步覆盖
- `--mode overwrite`：重建兼容层
- `--dry-run`：只显示将变更哪些文件，不写盘

## 兼容层说明

`.agents/` 是主目录。当前兼容层包括：

- 生成项目根目录 `AGENTS.md`
- 生成项目根目录 `.codex/skills/cppcheck-misra-fix/SKILL.md`
- 生成项目根目录 `.claude/skills/cppcheck-misra-fix/SKILL.md`

## 注意

- 本方案默认只自动修复高置信度、局部可判定的问题
- 高风险路径默认标记为 `needs_manual_review`
- 涉及环境异常、命令缺失、输入文件问题时，先运行 `doctor`
