# 2026-05-08-catch-llm-output-alias-plan.md
# Plan: Normalization Layer Degradation + Chunk Result Safety Net

> Design: `docs/superpowers/specs/2026-05-08-catch-llm-output-alias-design.md`

## 实施步骤（按文件分组，组内按依赖顺序）

### Step 1 — `common.py`: `normalize_file_change_delta()` 增强 + 降级

**文件**: `.agents/tools/common.py`

1. **扩展常量** (line ~680)
   - `_KNOWN_FILE_CHANGES_KEYS` 追加 `"files"`, `"changed_files"`
   - `_KNOWN_FILE_PATH_KEYS` 追加 `"filename"`
   - 新增 `_KNOWN_FCD_META_KEYS = frozenset({"chunk_index", "metadata", "notes", "summary", "status"})`

2. **list 分支降级** (line ~703-711)
   - 将 `if not isinstance(item, dict): raise ValueError(...)` 改为：
     - `isinstance(item, str) and item.strip()` → `normalized[item.strip()] = {"edits": []}`; `continue`
     - `else` → `continue` (skip unrecognizable)
    - `file_path` 为空时（dict 中无 file path key）：从 `raise ValueError` 改为 `continue` skip

3. **fallback 前结构推断** (line ~825 之前)
   - 遍历 `file_change_delta.items()`，跳过 `_KNOWN_FCD_META_KEYS`
   - 检测到 `list[dict]` 且首个 dict 含 file path key → `return normalize_file_change_delta(base, {"file_changes": value}, chunk_index)`
   - 检测到 `list[str]` → 所有字符串降级为 inspection-only
   - 检测到 `str` 且含 `/` 或 `.c/.h/.cpp/.hpp` 后缀 → 降级为 inspection-only

4. **fallback 不 raise** (line ~825-832)
   - 遍历中跳过 `_KNOWN_FCD_META_KEYS`
   - `not isinstance(delta_entry, dict)` → `print` 警告 + `continue`
   - 删除原有的 `raise ValueError(...)`

**验证**: 运行 `tests/test_normalization.py::TestFileChangeDeltaDegradation`（新增测试）

---

### Step 2 — `common.py`: `normalize_issue_status_delta()` 增强 + 降级

**文件**: `.agents/tools/common.py`

1. **list 分支不 raise** (line ~908-919)
   - `not isinstance(item, dict)` → `continue`
   - `not issue_key` → `continue`
   - 删除原有的两处 `raise ValueError`

2. **dict-passthrough 注入 + 跳过 meta keys** (line ~930-937)
   - 新增 `_KNOWN_ISD_META_KEYS`（含 `issue_status_delta`, `status_changes`, `issue_status_changes` 等）
   - 遍历前调用 `_build_issue_edit_index(file_change_delta)`
   - 遍历中：跳过 `_KNOWN_ISD_META_KEYS`；非 dict value → `print` 警告 + `continue`
    - 遍历中：`normalized_patch = dict(patch)`（不 mutate 原始输入）
    - `"chunk_index" not in normalized_patch` → `normalized_patch["chunk_index"] = int(chunk_index)`
    - `"edit_ids" not in normalized_patch` → `normalized_patch["edit_ids"] = issue_edit_ids.get(issue_key, [])`
    - `normalized[issue_key] = normalized_patch`

**验证**: 运行 `tests/test_normalization.py::TestIssueStatusDeltaDegradation`

---

### Step 3 — `common.py`: `import_chunk_staging_artifacts()` 安全网

**文件**: `.agents/tools/common.py`

1. **包裹数据转换块** (line ~963-970)
   - 将 `normalize_file_change_delta()` + `merge_file_change_index()` 整体包裹 `try/except Exception`
   - 异常时：`print` 警告 + `file_change_delta = {}` + `merged_file_change_index = dict(file_change_index)`
   - `normalize_issue_status_delta()` 调用同理

**验证**: 运行 `tests/test_normalization.py::TestImportDegradation`

---

### Step 4 — `agent_runner.py`: import_error 补 `argv`

**文件**: `.agents/tools/agent_runner.py`

1. **修改返回 dict** (line ~151-158)
   - 在 `except (FileNotFoundError, OSError, ValueError)` 分支的返回 dict 中添加 `"argv": cmd`

**验证**: 运行 `tests/test_agent_runner.py` 中 import_error 相关测试

---

### Step 5 — `run_fix_pipeline.py`: 失败 chunk 标记 + 计数修正

**文件**: `.agents/tools/run_fix_pipeline.py`

1. **新增 `mark_chunk_issues_failed()`** (在 `mark_failure()` 之后)
   - 读取 `issue_status.json`
   - 读取 chunk payload (`load_chunk_payload(idx)`)
    - 遍历 chunk issues，将 `status == "pending"` 的改为 `failed`
   - 注入 `chunk_index` 和 `error_kind`

2. **在失败分支调用** (chunk 处理 `not success` 时)
   - 在现有失败处理逻辑之前调用 `mark_chunk_issues_failed(idx, last_error_kind or ERROR_KIND_RUNTIME_ERROR)`

3. **计数器拆分** (line ~331)
   - `processed_this_run` → `attempted_this_run` + `succeeded_this_run`
   - `for attempt` 循环前：`attempted_this_run += 1`
   - chunk 成功时：`succeeded_this_run += 1`
   - `--max-chunks` 检查使用 `succeeded_this_run`
   - 事件日志中 `"processed"` → `"attempted"` / `"succeeded"`
   - print 语句更新

**验证**: 运行 `tests/test_run_pipeline.py`

---

### Step 6 — `SKILL.md`: 强化格式约束

**文件**: `.claude/skills/cppcheck-misra-fix/SKILL.md`（主文件）

1. **更新 staging output format contract**
   - 在 `file_change_delta.json` 部分精确列出 3 种允许格式（A/B/C）
   - 显式禁止其他 wrapper key 名

2. **同步到兼容层**
   - 同步更新 `.codex/skills/cppcheck-misra-fix/SKILL.md` 和 `.opencode/skills/cppcheck-misra-fix/SKILL.md`（如存在）

**验证**: 不需要代码测试，人工检查即可

---

### Step 7 — 在已有测试文件中追加测试类

**文件**: `tests/test_normalization.py`（已存在，422 行）

1. `TestFileChangeDeltaDegradation`
   - `test_list_of_strings_degrades_to_inspection`
   - `test_unknown_wrapper_list_of_dicts_inferred`
   - `test_unknown_wrapper_string_value_degrades`
   - `test_non_dict_value_skipped_not_raised`
   - `test_completely_empty`

2. `TestIssueStatusDeltaDegradation`
   - `test_passthrough_injects_chunk_index`
   - `test_passthrough_skips_meta_keys`
   - `test_non_dict_entry_skipped_not_raised`

3. `TestImportDegradation`
   - `test_import_survives_garbage_file_change_delta`

---

### Step 8 — 全量回归测试

```bash
python3 -m pytest tests/ -v
```

预期：所有现有测试通过 + 新增测试通过。

---

## 回滚策略

若发现问题：
1. 单独 revert `common.py` 的修改会恢复 raise 行为（但会重新引入 chunk 丢失 bug）
2. 建议回滚整个 PR，因为修改相互依赖

## 工作量估计

| 步骤 | 估计时间 |
|---|---|
| Step 1-3 (common.py) | 30 min |
| Step 4 (agent_runner.py) | 5 min |
| Step 5 (run_fix_pipeline.py) | 15 min |
| Step 6 (SKILL.md) | 10 min |
| Step 7 (tests) | 20 min |
| Step 8 (regression) | 10 min |
| **总计** | **约 90 min** |
