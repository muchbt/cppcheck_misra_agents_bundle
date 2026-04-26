# cppcheck + MISRA agent pipeline

一个纯 Python 3、跨 Windows/Linux 的工程内自包含方案，用于：

- 解析 `cppcheck.xml`
- 识别普通 cppcheck 与 MISRA 结果
- 按文件聚类并切 chunk
- 调用本地 agent CLI
- 记录 issue 状态、修改点、chunk 结果、统一运行日志
- 支持按 `年月日-序号` 的 `run_id` 归档
- 支持 `oneshot` 统一入口和默认续跑
- 通过 `.agents/` 统一管理，并自动生成兼容层

## 系统要求

- **Python 3.8+**（入口自动检查版本）
- **跨平台支持**：Windows / Linux

## 支持的 Agent Provider

| Provider | CLI 命令 | 认证方式 | 特点 |
|----------|----------|----------|------|
| **codex** | `codex exec` | `~/.codex/auth.json` | 需要 CODEX_HOME 工作区目录 |
| **claude** | `claude -p` | `claude auth login` 或 `ANTHROPIC_API_KEY` | 无需额外工作区配置 |
| **opencode** | `opencode` | OpenCode CLI 全局配置 | 自动隔离 XDG_DATA_HOME/XDG_STATE_HOME |
| **kimi** | `kimi --print` | `KIMI_API_KEY` 或 `~/.kimi/credentials/` | 自动隔离 KIMI_SHARE_DIR |

切换 provider 只需修改 `.agents/config/pipeline.json` 中的 `agent.provider` 字段，或通过 CLI 参数覆盖：

```bash
python3 .agents/tools/pipeline_cli.py --provider kimi oneshot
```

## CLI 命令

唯一入口：`pipeline_cli.py`

| 命令 | 功能 |
|------|------|
| `oneshot` | 一键执行 split → run → merge，支持自动续跑 |
| `split` | 解析 cppcheck.xml，按策略切分 chunk |
| `run` | 执行 agent 修复 pipeline |
| `merge` | 合并结果，生成中文报告和归档 |
| `doctor` | 运行环境诊断检查 |
| `bootstrap` | 生成 agent 兼容层（AGENTS.md、SKILL.md） |
| `verify` | 验证单个 chunk 结果 |
| `validate-real` | 真实 provider 验证（1 issue / 1 chunk） |
| `policy` | 策略模板管理（list/init/test/add） |

## 目录结构

- `.agents/config/*.json`：配置
- `.agents/config/templates/*.json`：策略模板
- `.agents/prompts/*.txt`：prompt 模板
- `.agents/skills/*`：主 skill 源
- `.agents/tools/*.py`：工具脚本（仅通过 pipeline_cli 调用）
- `.agents/runtime/*`：当前运行态、chunk、结果、日志
- `.agents/reports/*`：当前运行的中文报告
- `.agents/runs/<run_id>/*`：历史归档

## 策略模板

### 模板列表

| 模板文件 | 适用场景 | 特点 |
|----------|----------|------|
| `misra_c2012_conservative.json` | 保守 MISRA C:2012 | 所有 MISRA 规则标记为 `needs_manual_review` |
| `misra_c2012_relaxed.json` | 放宽 MISRA C:2012 | 低风险 `auto_fix`，中风险 `careful_fix`，高风险 `needs_manual_review` |
| `cppcheck_common.json` | 通用 cppcheck | 常见 cppcheck error/warning 策略 |
| `autosar_baseline.json` | AUTOSAR 基线 | RTE/MCAL/BSW 组件强制人工复核 |

### 使用模板

```bash
# 查看可用模板
python3 .agents/tools/pipeline_cli.py policy list

# 从模板初始化策略文件
python3 .agents/tools/pipeline_cli.py policy init misra_c2012_relaxed

# 测试规则匹配
python3 .agents/tools/pipeline_cli.py policy test misra-c2012-2.2

# 添加自定义规则
python3 .agents/tools/pipeline_cli.py policy add misra-c2012-8.1 --action auto_fix --risk-level low
```

### 模板详解

#### misra_c2012_conservative.json

最保守策略，覆盖 MISRA C:2012 全部 143 条规则（Directive 1-4 + Rule 1-22）。

- **默认动作**：所有规则 `needs_manual_review`
- **风险等级**：全部 `high`
- **特殊模式**：`volatile` / `interrupt` / `register` / `rte_` / `mcal` / `bsw` 关键字强制人工复核

适用场景：安全关键系统、首次接入、对自动修复持保守态度的项目。

#### misra_c2012_relaxed.json

放宽策略，根据规则实际风险分级：

| 动作 | 含义 | 典型规则 |
|------|------|----------|
| `auto_fix` | 高置信度自动修复 | 2.2/2.3（死代码）、2.7（未用参数）、7.2（常量后缀）、8.11（const）、15.6/15.7（块结构）、20.7（宏参数括号） |
| `careful_fix` | 需验证后修复 | 5.1-5.5（标识符）、8.3-8.10（类型定义）、10.1/10.3（类型转换）、16.1/16.3（switch） |
| `needs_manual_review` | 必须人工复核 | 9.1（未初始化）、11.1/11.2（函数指针转换）、17.1/17.2（指针使用）、21.3/21.4（内存分配）、全部 Directive |

适用场景：有一定 MISRA 经验、希望减少人工复核负担、但仍保留高风险路径保护。

#### cppcheck_common.json

通用 cppcheck 策略：

| 动作 | 典型错误类型 |
|------|--------------|
| `auto_fix` | unusedVariable、constVariable |
| `careful_fix` | unreadVariable、uninitStructMember、memoryLeak、resourceLeak |
| `needs_manual_review` | uninitvar、nullPointer、bufferAccessOutOfBounds、arrayIndexOutOfBounds、doubleFree |

特殊模式：`volatile` / `interrupt` / `register` / `malloc` / `strcpy` / `sprintf` 关键字强制人工复核。

#### autosar_baseline.json

AUTOSAR 架构专用策略，覆盖 RTE/MCAL/BSW 关键路径：

- **默认动作**：全部 `needs_manual_review`
- **特殊模式**（强制人工复核）：
  - `rte_` / `Rte_` / `RTE_`：AUTOSAR RTE 路径
  - `mcal` / `MCAL`：微控制器抽象层
  - `bsw` / `BSW`：基础软件层
  - `canif` / `CanIf` / `com` / `dem` / `det` / `ecu` / `schm` / `os`：AUTOSAR 模块
  - `volatile` / `interrupt` / `ISR` / `register` / `config`：硬件相关

适用场景：AUTOSAR 项目、需要保护架构层接口的项目。

### 策略动作说明

| 动作 | 含义 | 风险等级 |
|------|------|----------|
| `auto_fix` | agent 可自动修复，无需人工确认 | low |
| `careful_fix` | agent 可修复，但需验证结果 | medium |
| `needs_manual_review` | 必须人工复核，agent 不自动修复 | high |
| `skip` | 跳过该问题 | - |

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

1. 预检查（doctor）
2. `split`（解析 XML、切 chunk）
3. `run`（执行 agent 修复）
4. `merge`（生成报告、归档）

如果检测到已有未完成运行，`oneshot` 会默认续跑。

## fresh 与续跑

默认情况下，只要 `.agents/runtime/progress.json` 的状态是 `ready`、`running`、`partial` 或 `failed`，`oneshot` 就会续跑。

强制从头开始：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh
```

指定策略或 run_id：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --strategy all_auto --run-id 20260423-001
```

## 分步命令

需要拆开执行时：

```bash
python3 .agents/tools/pipeline_cli.py split --strategy conservative
python3 .agents/tools/pipeline_cli.py run --strategy conservative
python3 .agents/tools/pipeline_cli.py merge
```

Windows 下：

```bat
py .agents\tools\pipeline_cli.py doctor
py .agents\tools\pipeline_cli.py oneshot
```

## 自动修复策略

默认策略是 `conservative`：

- 只自动修复高置信度、局部可判定的问题
- 高风险 MISRA / volatile / interrupt / register / RTE / MCAL 等问题标记为 `needs_manual_review`

使用 `all_auto` 让 agent 尝试修复更多问题：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --strategy all_auto
```

`all_auto` 会把高风险问题也分发给 agent，但结果必须保留 `risk_level`、`risk_reason` 和 `review_required_after_fix=true`。

## 运行日志

当前运行的日志位于：

- `.agents/runtime/pipeline.log`：适合人工快速阅读
- `.agents/runtime/run_log.jsonl`：适合脚本消费

## 中文报告

每次 `merge` 会生成：

- `.agents/reports/final_summary.md`：运行总结（简体中文）
- `.agents/reports/final_summary.json`：JSON 格式总结
- `.agents/reports/review_checklist.md`：人工复核清单
- `.agents/reports/run_manifest.json`：运行元数据

## 归档

每次 `merge` 后，当前运行会复制到 `.agents/runs/<run_id>/`，包含：

- `runtime/`：运行态 JSON、chunk、结果
- `reports/`：中文总结、复核清单、manifest
- `logs/`：pipeline.log 与 run_log.jsonl

## bootstrap_agents.py

同步兼容层：

```bash
python3 .agents/tools/pipeline_cli.py bootstrap --mode merge
```

模式说明：

- `--mode merge`：默认；标记块替换/追加 AGENTS.md，覆盖 SKILL.md
- `--mode overwrite`：重建兼容层
- `--dry-run`：预览变更，不写盘

## 兼容层说明

`.agents/` 是主目录。兼容层包括：

- 项目根目录 `AGENTS.md`
- `.codex/skills/cppcheck-misra-fix/SKILL.md`
- `.claude/skills/cppcheck-misra-fix/SKILL.md`

## 注意

- 本方案默认只自动修复高置信度、局部可判定的问题
- 高风险路径默认标记为 `needs_manual_review`
- 涉及环境异常、命令缺失、输入文件问题时，先运行 `doctor`
- Python 低于 3.8 时，入口会直接报错退出