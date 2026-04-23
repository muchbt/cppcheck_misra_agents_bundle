# cppcheck/MISRA 流水线评审与归档改进设计

## 背景

当前工程提供 `cppcheck + MISRA` 自动修复流水线：解析 `cppcheck.xml`，按风险和文件切分 chunk，调用本地 agent 修复，再合并运行结果。现有基础流程可用，但用户侧仍存在几个直接影响使用的问题：命令需要手动串联、报告不适合人工 review、运行结果缺少按时间归档、失败后重跑可能覆盖当前运行态。

本设计吸收 `improvements.md` 中的反馈，目标是在不重写核心 `split -> run -> merge` 流程的前提下，补齐低风险、高收益的基础能力。

## 目标

- 提供 `oneshot` 入口，自动完成预检、拆分、运行、合并、归档。
- `oneshot` 发现已有未完成运行时默认续跑，并在终端明确提示用户；只有显式 `--fresh` 才开始新运行并清空当前 runtime。
- `oneshot` 续跑时若用户传入的 `--strategy` 与当前运行策略不一致，应提前拦截并提示使用 `--fresh` 开始新运行。
- 首次运行或发现环境异常时，引导用户执行 `doctor` 检查环境。
- 运行过程中显示当前阶段、chunk 进度、续跑状态和失败摘要。
- 使用统一日志结构，避免 `run_log.jsonl` 混写不同 schema。
- 按 `YYYYMMDD-序号` 保存运行结果，例如 `.agents/runs/20260423-001/`。
- 改进面向人工 review 的 Markdown 报告，使用自然、准确的简体中文。
- 专业术语首次出现时保留英文原文，例如“需人工复核（needs manual review）”。
- 更新 skill 和 prompt，让 agent 尽量在工作区内完成修改、状态记录和验证结果记录，减少因沙箱或权限问题导致工作流卡住。
- 保持 Python 3.8 兼容。

## 非目标

- 不重写 agent 调用架构。
- 不引入数据库或外部服务。
- 不改变 chunk JSON 的主结构。
- 不移动现有 `.agents/runtime` 工作目录。
- 不自动删除 `.agents/runs/` 历史归档；只在 `doctor` 中提示归档数量和大小。
- 不添加 `docter` 之类的错误拼写别名。
- 暂不改变 Codex prompt 传递协议；仅增加 prompt 长度诊断，待确认 CLI 支持后再考虑 stdin 或临时文件传递。

## 用户流程

推荐入口：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --strategy conservative
```

`oneshot` 执行流程：

1. 运行基础预检。若存在阻塞问题，输出原因，并提示：

   ```bash
   python3 .agents/tools/pipeline_cli.py doctor
   ```

2. 检查 `.agents/runtime/progress.json`：
   - 若存在未完成运行，默认续跑，并提示当前 `run_id`、已完成 chunk、失败 chunk、剩余 chunk。
   - 续跑时以已有 `progress.json` 的 `fix_strategy` 为准；若用户显式传入不同的 `--strategy`，直接退出，并提示使用 `--fresh --strategy <目标策略>`。
   - 若用户传入 `--fresh`，开始新运行，执行 split 并清空当前 runtime。
   - 若用户传入 `--resume`，行为与默认续跑一致，用于脚本中表达意图。

3. 新运行时执行 `split`：解析 `cppcheck.xml`，生成 chunk，创建或使用指定 `run_id`。
4. 执行 `run`：逐 chunk 调用 agent，成功产出 result JSON 后调用轻量验证逻辑。
5. 执行 `merge`：生成中文 review 报告、机器可读摘要和归档目录。

保留原有分步入口：

```bash
python3 .agents/tools/pipeline_cli.py doctor
python3 .agents/tools/pipeline_cli.py split --strategy conservative
python3 .agents/tools/pipeline_cli.py run --strategy conservative
python3 .agents/tools/pipeline_cli.py merge
```

## 归档模型

保留 `.agents/runtime` 作为活动运行态，新增 `.agents/runs/<run_id>/` 保存归档结果。`run_id` 使用 `YYYYMMDD-序号`：

- 当天第一次运行是 `YYYYMMDD-001`。
- 同一天后续运行按现有归档目录递增。
- `run_id`、`started_at`、`finished_at` 写入 `.agents/runtime/progress.json`。

归档目录结构：

```text
.agents/runs/20260423-001/
  run_manifest.json
  runtime/
    issues_master.json
    issue_status.json
    file_change_index.json
    progress.json
    chunks/
    results/
  reports/
    final_summary.md
    review_checklist.md
    final_summary.json
    final_patch_index.md
  logs/
    pipeline.log
    run_log.jsonl
```

`run_manifest.json` 必须记录：

- `run_id`
- `started_at`
- `finished_at`
- `archived_at`
- 输入 XML
- 修复策略
- issue 和 chunk 统计
- 完成/失败 chunk
- 报告路径

## 日志设计

`pipeline.log` 面向人工排查，使用简体中文记录当前阶段、chunk、返回码和失败摘要。

`run_log.jsonl` 面向程序处理，所有记录使用统一事件结构：

```json
{
  "time": "2026-04-23T10:00:00+08:00",
  "event": "chunk_completed",
  "stage": "run",
  "level": "info",
  "message": "chunk 1 处理完成",
  "chunk_index": 1,
  "returncode": 0,
  "data": {
    "attempt": 1
  }
}
```

已有 `run_fix_pipeline.py` 中的 `completed`、`failed`、`retry_scheduled` 记录迁移到统一 helper，避免同一 JSONL 文件混写不同 schema。

## 报告设计

面向人工 review 的文档使用简体中文。表述要求清楚、自然，避免直译腔；专业术语首次出现时保留英文原文。

`final_summary.md` 面向整体 review，包含：

- 运行概览：运行 ID、策略、输入文件、issue 总数、chunk 总数、完成状态。
- Review 重点：高风险已修复项、需人工复核（needs manual review）项、失败项、未验证项。
- 按文件汇总：每个文件涉及的规则、状态和修改点。
- 按规则汇总：每条规则的 fixed / needs manual review / failed 数量。
- 修改索引：edit_id、文件、chunk、关联 issue 和摘要。
- 验证结果：是否执行验证命令、命令、返回码、未验证原因。

`review_checklist.md` 面向 reviewer，不只写计数，必须列出具体 issue key、文件、规则、状态和 edit_id：

- 必看项：高风险已修复、`review_required_after_fix=true`、失败项。
- 抽查项：普通自动修复、同文件多 issue 合并修改。
- 验证项：是否重新运行 cppcheck，是否执行自定义验证命令。
- 放行前确认项：仍需人工判断的问题和未完成验证。

报告不得声称“安全通过”，除非工程级验证命令真实执行并通过。没有自定义验证命令时，报告写“未执行工程级验证”。

## 预检设计

新增 `doctor` 命令，检查：

- 当前 Python 版本是否满足 3.8+。
- 项目根目录是否可从脚本路径定位，避免依赖用户从项目根目录执行。
- `cppcheck.xml` 是否存在、是否为合法 XML、是否包含 `<error>` 节点。
- `.agents/config/pipeline.json` 必需字段是否存在，类型和枚举值是否合理。
- `agent.command` 是否可执行。
- 自定义验证命令是否存在或可执行。
- `.agents/runtime/progress.json` 中的策略是否与当前配置一致。
- 是否存在未完成运行，并说明 `oneshot` 会默认续跑。
- `.agents/runs/` 的归档数量和磁盘占用，仅提示，不自动清理。
- prompt 长度是否明显偏长，提示后续可能需要切换 stdin 或临时文件传递。

## 验证设计

`run_fix_pipeline.py` 在 chunk 成功产出 result JSON 后调用现有 `verify_chunk` 逻辑，将 verification 字段写入 chunk result。没有自定义验证命令时，该字段表示轻量验证，不代表工程级验证通过。

`merge_results.py` 汇总 verification 字段，在中文报告中明确列出：

- 已执行工程级验证并通过的项。
- 已执行工程级验证但失败的项。
- 未执行工程级验证的项。

## Skill 与 Prompt 改进

更新 `cppcheck-misra-fix` 的 `SKILL.md` 和 `fix_chunk_prompt.txt`：

- agent 应优先在当前工作区内完成代码修改、状态更新和验证记录。
- 遇到沙箱、权限或外部命令不可用问题时，应把问题记录为 blocker、failed 或 needs manual review。
- 能跳过当前 chunk 内某个问题并继续处理后续问题时，不应让整个工作流无期限等待。
- 只有确实需要用户授权才能继续时才询问用户。
- 结果文件必须说明哪些问题已修复、哪些因环境限制未处理、需要用户采取什么动作。

更新 skill 后，运行 `bootstrap_agents.py --mode merge` 同步 Codex 兼容层。

## 维护性设计

- 将根目录定位、配置校验、运行 ID 生成、日志写入、归档复制放入公共模块。
- `common.py` 保持 Python 3.8 类型标注兼容，使用 `Tuple[List[str], List[str]]`，不使用 `tuple[...]`。
- `merge_results.py` 拆出统计构建、中文报告生成、checklist 生成和归档函数。
- `pipeline_cli.py` 只负责命令分发，不承载业务逻辑。
- `oneshot.py` 负责串联流程，不复制 `split`、`run`、`merge` 的核心逻辑。
- `oneshot.py` 的阶段执行应封装为独立 runner 接口，当前只需要满足 `split/run/merge` 串联；后续可在该接口下扩展 `--run-id` 透传、并发锁、函数调用模式或更细粒度阶段控制。

## 未来改进计划

以下内容不进入本次实现，但当前设计应避免阻碍二期扩展：

- `oneshot --run-id`：允许通过一键入口指定自定义运行 ID。当前仅要求分步 `split --run-id` 支持自定义 ID。
- `oneshot` 调用方式优化：当前计划不强制 subprocess 或函数调用，要求先封装阶段 runner；二期可在不影响用户参数的前提下切换实现方式。
- 复合 agent 命令诊断：`doctor` 当前按可执行命令做基础检查；二期可支持 `python3 -m xxx` 等复合命令的结构化解析。
- 并发运行保护：二期可加入 `.agents/runtime/.lock`，避免多个 `oneshot` 同时读写 runtime。
- `.agents/reports/` 语义说明：二期文档可明确它始终表示最近一次 merge 结果，历史结果以 `.agents/runs/<run_id>/` 为准。
- 更完整的验证集成测试：二期可覆盖自定义验证命令成功、失败、缺失、超时等组合场景。

## 真实验证反馈与后续阶段

在基于 `gen_scan_files.py` 生成示例源码、使用 `cppcheck --enable=warning,style --addon=misra.py --xml --xml-version=2 . 2> cppcheck.xml` 生成真实输入并执行完整流水线后，`split` 阶段可以稳定完成，但 `run` 阶段在第一个 chunk 上失败。失败原因不是 `split -> run -> merge` 主流程设计错误，也不是 `oneshot` 编排错误，而是当前 agent 接入方式把交互式 CLI 当成了批处理执行器：

- 当前配置模型只有 `agent.command` 字符串，缺少对非交互执行、prompt 传递、工作目录、环境变量、输出模式的结构化表达。
- 当前 `agent_adapter_codex.py` 直接以 `[agent_cmd, prompt]` 形式调用 agent，会拉起交互式 TUI，而不是稳定的非交互执行模式。
- 实际验证中，`codex` CLI 会在启动时尝试更新 PATH 和用户环境；在只读或受限环境下会直接失败。这类问题不应视为 Codex 特例，后续若接入 `Claude Code` 或其他交互式 agent CLI，也会落入同类风险。

因此，本设计在保留 Task 1-6 目标与交付事实的前提下，追加一个新的后续阶段，用于修复通用执行层设计缺陷，而不是回溯性否定前 6 个任务。

前文中关于“不重写 agent 调用架构”、`agent.command` 基础诊断、以及 prompt 传递方式暂不调整等表述，均只适用于 Task 1-6 的一期范围；进入 Task 7 后，这些局部前提以本节的结构化 agent 执行设计为准。

## 后续阶段：Task 7 通用非交互 agent 执行抽象

### 目标

- 将当前 `agent.command` 字符串模型升级为结构化 agent 配置模型。
- 引入通用的非交互执行协议（launch spec / runner），使流水线不再直接依赖某个交互式 CLI 的默认行为。
- 重构当前 `codex` 接入为 provider 目录化实现。
- 升级 `doctor`，从“命令存在”检查提升到“是否适合流水线非交互执行”的能力检查。
- 为 `Claude Code` 二期支持预留 provider 接口、配置模型和诊断边界，但不在本期真正实现其 provider。

### 非目标

- 不在本期实现 `Claude Code` provider。
- 不重写 `split`、`run`、`merge` 的业务逻辑。
- 不改变 chunk JSON 主结构。
- 不为了兼容旧配置保留 `agent.command: "codex"` 字符串模式。
- 不把 provider 体系扩展成通用插件框架或并行多 agent 调度系统。

### 配置模型

将旧配置：

```json
"agent": {
  "type": "codex",
  "command": "codex",
  "auto_bootstrap_compat": true
}
```

升级为新的结构化模型：

```json
"agent": {
  "provider": "codex",
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
  },
  "auto_bootstrap_compat": true
}
```

其中：

- `provider`：一期仅支持 `codex`，二期可扩展 `claude`。
- `launch.argv`：结构化命令参数数组，禁止使用单字符串。
- `launch.prompt_via`：一期支持 `stdin | arg | file`，当前推荐 `stdin`。
- `launch.cwd`：支持 `project_root | runtime_dir | custom`。
- `launch.env`：允许声明工作区内可写目录映射。
- `launch.requires_tty`：显式声明是否依赖交互终端。
- `launch.output.mode`：一期先支持 `exit_code`，为后续 `stdout_json`、`file` 预留扩展位。
- `capabilities`：供 `doctor` 和后续 provider 扩展使用，一期至少包含 `non_interactive` 和 `workspace_write_required`。
- `auto_bootstrap_compat`：保留与现有兼容层同步相关的开关语义，避免影响 `.agents` / `.codex` 双目录同步。

### 模块结构

新增以下结构：

- `.agents/tools/agent_runner.py`
  - 读取结构化 agent 配置
  - 加载 provider
  - 校验 launch spec
  - 处理 cwd / env / stdin / 输出
  - 执行子进程并返回统一结果
- `.agents/tools/providers/base.py`
  - 定义 provider spec、launch spec、执行结果等通用类型
- `.agents/tools/providers/__init__.py`
  - 负责 provider 注册与查找
- `.agents/tools/providers/codex.py`
  - 一期唯一真实 provider
  - 负责组装 prompt、提供 launch spec、声明诊断要求

现有 `.agents/tools/agent_adapter_codex.py` 在 Task 7 落地后删除，不保留并行旧入口。

### 数据流与职责边界

职责划分采用四层模型：

1. `run_fix_pipeline.py`
   - 只负责 chunk 选择、重试、progress 更新、统一日志、verify 调用
   - 不直接拼 CLI 或处理 provider 细节
2. `providers/codex.py`
   - 读取 chunk，组装 prompt，返回 launch spec
   - 不直接执行 subprocess
3. `agent_runner.py`
   - 合并配置与 provider 默认值
   - 校验执行协议
   - 调用 `subprocess`
   - 返回统一执行结果
4. `doctor.py`
   - 复用 provider 和 runner 元信息做执行层诊断

建议的数据流为：

```text
run_fix_pipeline.py
  -> agent_runner.run_chunk_agent(chunk_index)
    -> providers.codex.build_launch_spec(chunk_index, config)
      -> agent_runner.execute_launch_spec(spec)
        -> 返回统一执行结果
```

### 错误处理与诊断规则

将 agent 执行失败统一归类为：

- `config_error`：配置结构不合法，运行前阻断
- `spawn_error`：命令不存在、cwd 无法解析、环境目录不可写、stdin/file 准备失败
- `runtime_error`：agent 进程启动成功但非零退出
- `interactive_not_supported`：配置声明需要 TTY 或不支持非交互执行

`doctor` 从“命令是否存在”升级为“执行协议是否适合流水线”检查，至少覆盖：

- `agent.provider` 是否支持
- `launch.argv` 是否存在且为非空数组
- `prompt_via` 是否为支持值
- `cwd` 是否可解析
- `env` 映射的工作区目录是否可创建 / 可写
- `requires_tty` 与 `capabilities.non_interactive` 是否冲突
- provider 是否为一期真实实现
- 对 `codex` provider，若配置为交互式 TUI 风格调用，直接报 blocker

### 测试策略

Task 7 追加测试，覆盖：

- 新配置模型接受结构化 `agent`，拒绝旧的字符串命令模式
- runner 能正确处理 `stdin` prompt、`cwd`、`env`
- `spawn_error`、非零退出码、交互式配置错误能统一回传
- `codex` provider 生成的 launch spec 符合预期
- `doctor` 能识别非交互能力缺失、TTY 需求、不写环境目录等阻断条件
- `run_fix_pipeline.py` 使用 runner 返回值后，progress / 日志 / 失败语义保持不变

### 与原计划的关系

- Task 1-5 的实现与提交结论保持不变。
- Task 6 的真实链路验证仍然有效，并作为 Task 7 的输入证据。
- `Claude Code` 明确为二期支持目标，一期只预留 provider 接口、配置模型和诊断边界。

## 测试策略

新增最小测试集，覆盖：

- 合法和非法 cppcheck XML 的识别。
- `run_id` 按日期递增。
- 从非项目根目录执行时仍能定位项目根目录。
- 配置缺字段和策略不一致诊断。
- `run_log.jsonl` 每行均符合统一事件结构。
- `oneshot` 对未完成运行默认续跑，`--fresh` 才触发重新 split。
- `oneshot` 续跑时发现 `--strategy` 与已有运行策略不一致，应退出并提示使用 `--fresh`。
- `run_manifest.json` 包含 `started_at`、`finished_at`、`archived_at`。
- 报告包含高风险、需人工复核、失败、未验证和具体 issue/edit 条目。
- 归档目录包含 manifest、reports、runtime 和 logs。
- `pipeline_cli.py` 支持 `doctor` 和 `oneshot`，不支持 `docter`。

## 自审结论

- 本设计已吸收 `improvements.md` 中影响正确性和可用性的反馈。
- 设计范围仍聚焦低风险基础增强，没有要求重写核心修复流程。
- `oneshot` 续跑行为已明确：默认续跑并提示，`--fresh` 才开始新运行。
- 中优先级的策略冲突检测已纳入本次计划，低优先级项已列为未来改进计划。
- `docter` 错误拼写别名已明确排除。
- 真实链路验证已经证明，后续风险集中在通用 agent 执行层，而不是 `split/run/merge` 主流程。
- Task 7 作为追加阶段，能保持 Task 1-6 的交付事实，同时修复执行层设计缺陷并为二期 `Claude Code` 支持预留接口。

## 一期收口与二期方向

截至当前实现，一期范围内的 Task 1-7 已完成，当前方案已经具备：

- `oneshot` / `doctor` / `split` / `run` / `merge` 的统一入口和续跑语义
- 面向人工 review 的中文报告与归档
- 结构化 `agent` 配置、非交互 provider / runner、认证复用与基础阻断诊断

但真实 `codex exec` session 日志进一步暴露了一个结构问题：即使主工作区可写，agent 子会话仍可能把 `.agents` 挂为只读，导致 agent 无法直接写入 `.agents/runtime/*` 的权威运行态文件。这说明当前“一边执行 agent，一边让 agent 直写权威运行态”的模型仍然过于耦合。

因此，二期优先方向明确为：

- 引入一个 agent 可写 staging 目录，把 agent 写入和流水线权威状态分离

二期目标不是迁移整个 `.agents/runtime` 主目录，而是在保持现有权威目录、归档目录和报告目录不变的前提下：

- 为 agent 提供单独的可写 staging 工作区
- 让 provider / runner 只要求 agent 写 staging 结果
- 由流水线在 agent 退出后把 staging 结果导入 `.agents/runtime`
- 将“agent 输出格式”和“流水线权威状态”解耦，降低 sandbox / mount 策略变化带来的失败风险
