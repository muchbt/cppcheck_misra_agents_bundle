# cppcheck + MISRA agent pipeline

一个纯 Python 3、跨 Windows/Linux 的工程内自包含方案，用于：

- 解析 `cppcheck.xml`
- 识别普通 cppcheck 与 MISRA 结果
- 按文件聚类并切 chunk
- 调用本地 agent（默认 Codex CLI）
- 记录 issue 状态、文件修改点、chunk 结果
- 支持断点续跑
- 通过 `.agents/` 统一管理，并自动生成 Codex 兼容层

## 目录

- `.agents/config/*.json`：配置
- `.agents/prompts/*.txt`：prompt 模板
- `.agents/skills/*`：主 skill 源
- `.agents/tools/*.py`：工具脚本
- `.agents/runtime/*`：运行时状态与结果
- `.agents/reports/*`：汇总报告

## 快速开始

1. 把整个目录内容放到你的工程根目录
2. 确保工程根目录下存在 `cppcheck.xml`
3. 运行：

```bash
python3 .agents/tools/bootstrap_agents.py --mode merge
python3 .agents/tools/split_cppcheck_xml.py --strategy conservative
python3 .agents/tools/run_fix_pipeline.py --strategy conservative
python3 .agents/tools/merge_results.py
```

也可以使用统一入口：

```bash
python3 .agents/tools/pipeline_cli.py split --strategy conservative
python3 .agents/tools/pipeline_cli.py run --strategy conservative
python3 .agents/tools/pipeline_cli.py merge
```

Windows 下可用：

```bat
py .agents\tools\bootstrap_agents.py --mode merge
py .agents\tools\split_cppcheck_xml.py --strategy conservative
py .agents\tools\run_fix_pipeline.py --strategy conservative
py .agents\tools\merge_results.py
```

## 自动修复策略

默认策略是 `conservative`：

- 只让 agent 修复高置信度、局部可判定的问题
- 高风险 MISRA / volatile / interrupt / register / RTE / MCAL 等问题标记为 `needs_manual_review`

如需让 agent 尝试修复所有问题，可显式使用 `all_auto`：

```bash
python3 .agents/tools/split_cppcheck_xml.py --strategy all_auto
python3 .agents/tools/run_fix_pipeline.py --strategy all_auto
```

或使用统一入口：

```bash
python3 .agents/tools/pipeline_cli.py split --strategy all_auto
python3 .agents/tools/pipeline_cli.py run --strategy all_auto
```

Windows 下：

```bat
py .agents\tools\split_cppcheck_xml.py --strategy all_auto
py .agents\tools\run_fix_pipeline.py --strategy all_auto
```

`all_auto` 会把高风险问题也分发给 agent，但必须在结果中标记 `risk_level=high`、`risk_reason` 和 `review_required_after_fix=true`。高风险自动修复不代表免人工复核。

## bootstrap_agents.py 模式

- `--mode merge`：默认；对 `AGENTS.md` 使用标记块替换/追加，对 `.codex/skills/.../SKILL.md` 执行同步覆盖
- `--mode overwrite`：重建兼容层
- `--dry-run`：只显示将变更哪些文件，不写盘

## 兼容层说明

`.agents/` 是主目录。为了兼容 Codex：

- 生成项目根目录 `AGENTS.md`
- 生成项目根目录 `.codex/skills/cppcheck-misra-fix/SKILL.md`

## 结果文件

- `.agents/runtime/issues_master.json`
- `.agents/runtime/issue_status.json`
- `.agents/runtime/file_change_index.json`
- `.agents/runtime/progress.json`
- `.agents/runtime/chunks/chunk_XXX.json`
- `.agents/runtime/results/chunk_XXX_result.json`
- `.agents/reports/final_summary.md`
- `.agents/reports/final_summary.json`

## 注意

- 本方案默认只自动修复高置信度、局部可判定的问题
- 高风险 MISRA / volatile / interrupt / register / RTE 等问题默认标记为 `needs_manual_review`
- `verify_chunk.py` 默认只做轻量验证；如需工程级编译验证，请在配置中开启自定义命令
