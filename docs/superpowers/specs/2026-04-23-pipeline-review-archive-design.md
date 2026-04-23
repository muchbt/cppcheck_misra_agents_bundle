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
