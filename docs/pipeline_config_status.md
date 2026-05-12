# Pipeline 配置功能实现状态说明

本文档记录 `.agents/config/pipeline.json` 中各配置项的实现状态。

## 已实现功能

- `project.runtime_dir` / `reports_dir` / `chunks_dir` / `results_dir`
- `input.cppcheck_xml`
- `chunking.max_issues_per_chunk` / `max_files_per_chunk`
- `chunking.split_high_risk_alone`
- `filter.include_severity` / `exclude_information`
- `misra.enabled` / `detect_prefixes`
- `fix_strategy.mode` / `require_review_after_high_risk_fix`
- `verification.mode` / `custom_command`
- `agent.provider` / `staging_dir` / `providers` / `auto_bootstrap_compat`

## 配置存在但功能未实现或实现不完整

### `verification.rerun_cppcheck_for_touched_files`

**当前状态**: 部分实现，功能与名称不完全匹配。

**名称暗示的行为**: 在 verify 阶段对修改过的文件重新运行 `cppcheck` 二进制，验证修复是否真正消除了原始告警。

**实际实现**: `split_cppcheck_xml.py` 中的 `_check_previous_fix()` 函数，在 **split 阶段**检查源文件中是否已有 `/* fix: <rule_id> ... */` 注释。若存在则设置 `previous_fix_attempted: true`，提示 agent 该问题曾被修复但未成功。

**配置生效情况**: 当且仅当此 boolean 为 `true` 时才启用检测；为 `false` 时 `previous_fix_attempted` 恒为 `false`。

**局限性**:
- 不是真正的 cppcheck 重跑，只是基于文本模式匹配
- 仅检查问题报告行本身，不检查相邻行
- 不验证修复后问题是否实际消除

**如需真正的 cppcheck 重跑**: 需在 `verify_chunk.py` 中扩展逻辑——从 chunk result 提取 `touched_files` → 运行 `cppcheck --xml` → 解析新 XML → 对比修改前后 issue 差异。

### `fix_strategy.mark_high_risk_in_all_auto`

**当前状态**: 仅 boolean 校验，未读取。

`classify_issue()` 已根据 `require_review_after_high_risk_fix` 设置 `requires_review_after_fix`，此 flag 当前未在任何逻辑分支中使用。

### `chunking.prefer_group_by_file`

**当前状态**: 仅 boolean 校验，未使用。

`build_chunks()` 中硬编码按文件分组，未检查此 flag。如需支持非文件分组模式，需在此函数中读取该配置并添加替代分块策略。
