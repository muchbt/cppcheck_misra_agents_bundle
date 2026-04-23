# cppcheck/MISRA 流水线评审与归档改进设计

## 背景

当前工程提供一套 `cppcheck + MISRA` 自动修复流水线：解析 `cppcheck.xml`，按风险和文件切分 chunk，调用本地 agent 修复，再合并运行结果。现有流程已经具备基础能力，但用户需要手动串联多个命令，报告偏统计化，不利于人工 review，运行结果也缺少按时间归档的稳定目录。

本次改进目标是先完成低风险、高收益的基础增强：提升用户跑通体验、改善中文 review 文档、保存可追溯运行结果，同时保持现有 `split -> run -> merge` 核心流程不变。

## 目标

- 提供 `oneshot` 入口，自动完成 `split`、`run`、`merge`。
- 首次运行或发现环境异常时，引导用户使用 `doctor` 检查环境。
- 运行过程中显示当前阶段、chunk 进度和失败摘要。
- 显示、记录并归档运行日志。
- 运行结果按 `YYYYMMDD-序号` 保存，例如 `.agents/runs/20260423-001/`。
- 改进面向人工 review 的 Markdown 报告，使用自然、准确的简体中文。
- 专业术语首次出现时保留英文原文，例如“需人工复核（needs manual review）”。
- 更新 skill 和 prompt，让 agent 尽量在工作区内完成修改、状态记录和验证结果记录，减少因沙箱或权限问题导致整个流程卡住。

## 非目标

- 不重写 agent 调用架构。
- 不引入数据库或外部服务。
- 不改变 chunk JSON 的主结构。
- 不移动现有 `.agents/runtime` 工作目录。
- 不批量重排现有代码风格。
- 不添加 `docter` 之类的错误拼写别名。

## 用户流程

推荐入口：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --strategy conservative
```

`oneshot` 自动执行：

1. 运行基础检查。检查失败时输出原因，并提示用户执行：

   ```bash
   python3 .agents/tools/pipeline_cli.py doctor
   ```

2. 执行 `split`：解析 `cppcheck.xml`，生成 chunk，创建本次 `run_id`。
3. 执行 `run`：逐 chunk 调用 agent，终端显示当前处理进度。
4. 执行 `merge`：生成中文 review 报告、机器可读摘要和归档目录。

保留原有分步入口，方便高级用户调试：

```bash
python3 .agents/tools/pipeline_cli.py doctor
python3 .agents/tools/pipeline_cli.py split --strategy conservative
python3 .agents/tools/pipeline_cli.py run --strategy conservative
python3 .agents/tools/pipeline_cli.py merge
```

## 归档模型

保留 `.agents/runtime` 作为当前运行态，新增 `.agents/runs/<run_id>/` 保存归档结果。`run_id` 使用 `YYYYMMDD-序号`：

- 当天第一次运行是 `YYYYMMDD-001`。
- 同一天后续运行按现有归档目录递增。
- `run_id` 写入 `.agents/runtime/progress.json`。

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

`run_manifest.json` 记录运行 ID、开始时间、结束时间、输入 XML、策略、chunk 数、issue 数、完成/失败数量和报告路径。

## 报告设计

面向人工 review 的文档使用简体中文。表述要求清楚、自然，避免直译腔；专业术语首次出现时保留英文原文。

`final_summary.md` 面向整体 review，包含：

- 运行概览：运行 ID、策略、输入文件、issue 总数、chunk 总数、完成状态。
- Review 重点：高风险已修复项、需人工复核（needs manual review）项、失败项、未验证项。
- 按文件汇总：每个文件涉及的规则、状态和修改点。
- 按规则汇总：每条规则的 fixed / needs manual review / failed 数量。
- 修改索引：edit_id、文件、chunk、关联 issue 和摘要。
- 验证结果：是否执行验证命令、命令、返回码、未验证原因。

`review_checklist.md` 面向 reviewer，包含：

- 必看项：高风险修复、`review_required_after_fix=true`、失败项。
- 抽查项：普通自动修复、同文件多 issue 合并修改。
- 验证项：是否重新运行 cppcheck，是否执行自定义验证命令。
- 放行前确认项：仍需人工判断的问题和未完成验证。

报告不得声称“安全通过”，除非工程级验证命令真实执行并通过。轻量验证只表述为“未执行工程级验证”。

## 预检设计

新增 `doctor` 命令，检查：

- `cppcheck.xml` 是否存在、是否为合法 XML、是否包含 `<error>` 节点。
- `.agents/config/pipeline.json` 必需字段是否存在，类型和枚举值是否合理。
- `agent.command` 是否可执行。
- 自定义验证命令是否存在或可执行。
- `.agents/runtime/progress.json` 中的策略是否与当前配置一致。
- 当前运行是否会覆盖 `.agents/runtime`，以及最终归档位置。

`oneshot` 在启动时执行基础预检。遇到阻塞问题时退出，并提示用户运行 `doctor` 查看完整诊断。

## 日志设计

新增统一日志能力：

- 终端输出当前阶段，例如“正在拆分 XML”“正在处理 chunk 1/3”“正在生成 review 报告”。
- 写入 `.agents/runtime/pipeline.log`，便于人工排查。
- 写入 `.agents/runtime/run_log.jsonl`，便于程序处理。
- 归档时复制日志到 `.agents/runs/<run_id>/logs/`。

日志记录开始时间、结束时间、阶段、命令参数、策略、chunk、返回码和错误摘要。日志不记录密钥、令牌、账号口令或其他敏感信息。

## Skill 与 Prompt 改进

更新 `cppcheck-misra-fix` 的 `SKILL.md` 和 `fix_chunk_prompt.txt`：

- agent 应优先在当前工作区内完成代码修改、状态更新和验证记录。
- 遇到沙箱、权限或外部命令不可用问题时，应把问题记录为 blocker、failed 或 needs manual review。
- 能跳过当前 chunk 并继续后续流程时，不应让整个工作流无期限等待。
- 只有确实需要用户授权才能继续时才询问用户。
- 结果文件必须说明哪些问题已修复、哪些因环境限制未处理、需要用户采取什么动作。

## 维护性设计

- 将配置校验、运行 ID 生成、日志写入、归档复制放入公共模块，避免各脚本重复实现。
- `merge_results.py` 拆出统计构建、中文报告生成、checklist 生成和归档函数。
- `pipeline_cli.py` 只负责命令分发，不承载业务逻辑。
- `oneshot.py` 负责串联流程，不复制 `split`、`run`、`merge` 的核心逻辑。

## 测试策略

新增最小测试集，覆盖：

- 合法和非法 cppcheck XML 的识别。
- `run_id` 按日期递增。
- 配置缺字段和策略不一致诊断。
- 报告包含高风险项、需人工复核项、失败项、未验证项。
- 归档目录包含 manifest、reports、runtime 和 logs。
- `pipeline_cli.py` 支持 `doctor` 和 `oneshot`，不支持 `docter`。

## 自审结论

- 本设计没有保留未决占位内容。
- 设计范围聚焦于用户入口、报告、归档、日志、预检和 skill 改进，适合单个实施计划。
- 设计没有要求重写核心修复流程，符合低风险基础改进目标。
- `docter` 错误拼写别名已明确排除。
