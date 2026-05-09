# 2026-05-08-catch-llm-output-alias-design.md
# Design: Normalization Layer Degradation + Chunk Result Safety Net

## 背景

在运行 `misra-pipeline run`（provider=claude，strategy=all_auto）处理 cppcheck XML 时，chunk 4 和 chunk 8 因 `import_error` 失败。根因是 agent 输出的 `file_change_delta.json` 使用了未预期的 key 名（如 `{"files": [...]}`），而 `normalize_file_change_delta()` 无法识别该格式，抛出 `ValueError` 导致 chunk result 文件未被复制到 `results/`，造成修复结果丢失。

问题触发链：
1. Agent 完成修复并写入 staging 文件
2. `import_chunk_staging_artifacts()` 调用 `normalize_file_change_delta()`
3. normalize 抛出 `ValueError: file_change_index entry must be an object: files`
4. `agent_runner` 捕获异常，返回 `error_kind=import_error`
5. `chunk_result.json/.md` 未被复制 → 结果永久丢失

## 设计原则

> **normalization 层永远不 raise。**
> 格式识别失败时降级为空 delta + 警告日志，确保 chunk result 文件始终被复制到 `results/`，从架构上消除因 agent 输出格式不匹配导致的数据丢失。

## 修改范围

涉及 3 个文件的产品代码修改 + 1 个 SKILL.md 更新 + 1 个测试文件新增。

### 修改 1 — `common.py`: `normalize_file_change_delta()` 增强 + 降级

**位置**: `common.py:692-832`

#### 1a. 扩展别名常量

```python
_KNOWN_FILE_CHANGES_KEYS = (
    "file_changes", "files_changed", "files_touched", "files",
    "changes", "modified_files", "file_edits", "changed_files"
)
_KNOWN_FILE_PATH_KEYS = ("file", "file_path", "path", "filename")
_KNOWN_FCD_META_KEYS = frozenset({"chunk_index", "metadata", "notes", "summary", "status"})
```

#### 1b. list 分支：string 元素降级为 inspection-only

将 `file_changes` 数组遍历中的严格 raise 改为降级处理：
- `str` 元素 → 视为 inspection-only（`{filename: {"edits": []}}`）
- 其他非 dict 元素 → skip
- `file_path` 为空（dict 中无 file path key）→ skip 而非 raise

#### 1c. fallback 前添加结构推断 + 降级

在标准 dict-iterate fallback 之前，遍历 `file_change_delta` 的所有键值对：
- 跳过 `_KNOWN_FCD_META_KEYS`
- 检测到 `list[dict]` 且 dict 中包含 file path key → 递归调用自身（`{"file_changes": value}`）
- 检测到 `list[str]` → 所有字符串降级为 inspection-only
- 检测到 `str` 且看起来像文件路径 → 降级为 inspection-only
- fallback 中：非 dict value → `continue` + `print` 警告（不再 raise）

### 修改 2 — `common.py`: `normalize_issue_status_delta()` 增强 + 降级

**位置**: `common.py:897-937`

#### 2a. list 分支不 raise

`status_changes` 数组遍历中：非 dict 元素 → `continue` skip。

#### 2b. dict-passthrough 注入 `chunk_index` + 跳过 meta keys

```python
_KNOWN_ISD_META_KEYS = frozenset({
    "chunk_index", "metadata", "notes",
    "issue_status_delta", "status_changes", "issue_status_changes",
})
```

- 遍历 issue_status_delta 时跳过 meta keys
- 自动注入缺失的 `chunk_index` 字段（复制 patch 后注入，不 mutate 原始输入）
- 自动注入缺失的 `edit_ids`（从 `file_change_delta` 推导）
- 非 dict value → `continue` + `print` 警告

### 修改 3 — `common.py`: `import_chunk_staging_artifacts()` 安全网

**位置**: `common.py:940-983`

在数据转换块（`normalize_file_change_delta` → `merge_file_change_index` 和 `normalize_issue_status_delta`）外包裹 `try/except`：
- 异常时降级为空 dict / 原始索引副本
- `print` 警告日志
- **关键保证**：无论 normalize 或 merge 如何失败，`chunk_result.json/.md` 总会被复制到 `results/`

### 修改 4 — `agent_runner.py`: import_error 返回值补 `argv`

**位置**: `agent_runner.py:151-158`

import_error 返回 dict 中补充 `"argv": cmd`，确保 `run_fix_pipeline.py` 的日志能记录完整命令。

### 修改 5 — `run_fix_pipeline.py`: 失败 chunk 标记 + 计数修正

**位置**: `run_fix_pipeline.py`

#### 5a. 新增 `mark_chunk_issues_failed()`

在 chunk 最终失败时，遍历该 chunk 的所有 issue，将 `status == "pending"` 的标记为：
- `status: "failed"`
- `chunk_index: <idx>`
- `error_kind: <error_kind>`

#### 5b. 计数器拆分

- `processed_this_run` → 拆分为 `attempted_this_run` / `succeeded_this_run`
- `--max-chunks` 限制使用 `succeeded_this_run`
- 事件日志中 `"processed"` 替换为 `"attempted"` / `"succeeded"`

### 修改 6 — `SKILL.md`: 强化输出格式约束

在 `.claude/skills/cppcheck-misra-fix/SKILL.md`（主文件）的 staging output format contract 中，精确列出 `file_change_delta.json` 的 3 种允许格式，并同步到 `.codex/skills/cppcheck-misra-fix/SKILL.md` 和 `.opencode/skills/cppcheck-misra-fix/SKILL.md`（如存在）：

- **Format A**（推荐）: flat object，key 为实际文件路径
- **Format B**: wrapper array，key 必须为 `file_changes`
- **Format C**: inspection-only，key 必须为 `files_inspected`

显式禁止其他 wrapper key 名。

## 测试覆盖

新增 `tests/test_normalization.py`：

| 测试类 | 场景 |
|---|---|
| `TestFileChangeDeltaDegradation` | list-of-strings 降级、unknown wrapper 结构推断、string value 降级、非 dict value skip、完全空对象 |
| `TestIssueStatusDeltaDegradation` | chunk_index 自动注入、meta keys 跳过、非 dict entry skip |
| `TestImportDegradation` | 垃圾 file_change_delta 下 chunk_result 仍被复制 |

## 兼容性

- `normalize_file_change_delta` 和 `normalize_issue_status_delta` 的签名不变
- `import_chunk_staging_artifacts` 的签名和返回值不变
- 现有成功路径的行为不变
- 所有降级路径打印警告日志，不影响原有正常流程

## 风险评估

| 风险 | 缓解措施 |
|---|---|
| 过度降级导致本应失败的数据被静默忽略 | 所有降级路径打印 `WARNING`，可通过日志审计发现 |
| 结构推断误匹配 | 仅在明确检测到 file path key 时才推断，误匹配概率低 |
| failed 状态与现有工具链冲突 | `failed` 状态已存在于 `merge_results.py` 中，无需额外处理 |
