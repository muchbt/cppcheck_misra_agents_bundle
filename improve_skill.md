This is a fundamental LLM agent reliability problem. Let me check the current architecture's constraints first.


Now let me check the normalize for issue_status_delta to see how that side handles key variations.

Now I have the complete picture. Here's the comprehensive analysis:

---

# 如何彻底解决 Agent 自行发明 key 名称的问题

这是 LLM agent 系统的经典难题。**不存在单一银弹**，需要在四个层面同时防御：

## 问题本质

LLM 不是程序——它是"近似遵循指令"的统计模型。即使 SKILL.md 明确写了 `file_changes`，agent 仍可能输出 `files_inspected`、`changed_files`、`file_edits` 等语义近似但 key 不同的变体。当前实测已证明这一点。

## 四层防御方案

### 第 1 层：Prompt — 用 JSON Schema + 具体示例锚定输出

当前 SKILL.md 的格式说明过于抽象：

```@/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/skills/cppcheck-misra-fix/SKILL.md:45-47
**file_change_delta.json:**
- Option A: Flat object `{file: data}` where data contains edits, change_summary, etc.
- Option B: Wrapper object `{file_changes: [{file, summary, linked_issues, ...}]}`
```

"Option A / Option B" 给了 LLM 太多自由度。应改为**唯一规范格式 + 完整示例**：

```markdown
**file_change_delta.json** — MUST use exactly ONE of these formats:

Format 1 (preferred): flat dict keyed by file path
```json
{
  "src/main.c": {
    "edits": [{"edit_id": "src/main.c#001", "summary": "...", "chunk_index": 1, "related_issue_keys": ["..."]}]
  },
  "chunk_index": 1
}
```

Format 2: wrapped array with key "file_changes" (EXACT key name, no aliases)
```json
{
  "file_changes": [
    {"file": "src/main.c", "summary": "...", "linked_issues": ["..."], "edits": []}
  ],
  "chunk_index": 1
}
```

⚠️ Do NOT use any other wrapper key names (e.g. files_inspected, changed_files, file_edits).
```

**关键改进：**
- 给出完整 JSON 示例而非文字描述
- 明确禁止别名
- 减少 Option 数量（越少越好）

### 第 2 层：Normalization — 防御性别名映射（当前最需要的修复）

Prompt 无论多完美，LLM 仍可能违反。归一化层是最后防线。

当前 [normalize_issue_status_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:743:0-812:21) 已经做了别名处理：

```@/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:749-751
    status_changes = issue_status_delta.get("status_changes")
    if not isinstance(status_changes, list):
        status_changes = issue_status_delta.get("issue_status_changes")
```

但 [normalize_file_change_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:613:0-724:21) **没有做等价的别名处理**。应统一模式：

```python
# common.py normalize_file_change_delta, line 619 附近
KNOWN_FILE_CHANGES_KEYS = ("file_changes", "files_inspected", "changed_files", "file_edits")

file_changes = None
for key in KNOWN_FILE_CHANGES_KEYS:
    candidate = file_change_delta.get(key)
    if isinstance(candidate, list):
        file_changes = candidate
        break
```

同时在 fallback dict-iterate 分支增加**未识别 key 的保护**：

```python
# line 718-725, 改为
KNOWN_META_KEYS = {"chunk_index", "metadata", "notes"}
normalized = {}
for file_path, delta_entry in file_change_delta.items():
    if file_path in KNOWN_META_KEYS:
        continue
    if not isinstance(delta_entry, dict):
        raise ValueError(
            f"file_change_delta['{file_path}'] must be an object, got {type(delta_entry).__name__}. "
            f"If this is a wrapper key, use one of: {', '.join(KNOWN_FILE_CHANGES_KEYS)}"
        )
    normalized[file_path] = delta_entry
```

### 第 3 层：Schema Validation — 在写入前做结构验证

在 [import_chunk_staging_artifacts()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:815:0-858:5) 加入一个轻量验证步骤，在 normalize 之前先检查 JSON 结构的合理性，提供更具体的错误信息：

```python
def _validate_staging_json_shape(data: dict, expected_name: str) -> None:
    """Quick sanity check on staging JSON before normalization."""
    if not isinstance(data, dict):
        raise ValueError(f"{expected_name} must be a JSON object, got {type(data).__name__}")
    # Warn about unknown top-level keys that look like wrapper arrays
    for key, value in data.items():
        if isinstance(value, list) and key not in KNOWN_FILE_CHANGES_KEYS and key != "chunk_index":
            import logging
            logging.warning(
                f"{expected_name}: unexpected array key '{key}' - "
                f"did you mean one of {KNOWN_FILE_CHANGES_KEYS}?"
            )
```

这不阻断流程，但在日志中留下可审计的警告。

### 第 4 层：Agent Output Post-processor（长期方案）

如果需要极高可靠性，可以加一个**轻量 post-processor** 步骤（不涉及 LLM 调用）：

```python
def coerce_file_change_delta(raw: dict) -> dict:
    """Best-effort coercion of agent output to canonical format."""
    # If any top-level key maps to a list-of-dicts with "file" keys, treat as file_changes
    for key, value in raw.items():
        if key == "chunk_index":
            continue
        if isinstance(value, list) and value and isinstance(value[0], dict) and "file" in value[0]:
            # Looks like a file_changes array under a wrong key
            return {"file_changes": value, "chunk_index": raw.get("chunk_index")}
    return raw
```

这是**结构推断**：如果某个 key 的值是一个 list-of-dict，且每个 dict 包含 `"file"` 字段，那它几乎肯定就是 `file_changes`，无论 key 叫什么。

---

## 推荐实施优先级

| 优先级 | 层 | 工作量 | 收益 |
|--------|---|--------|------|
| **立即做** | 第 2 层 — 别名映射 | ~10 行 | 修复当前 bug + 预防已知变体 |
| **立即做** | 第 1 层 — SKILL.md 示例 | ~20 行文档 | 减少 agent 输出偏差概率 |
| **短期做** | 第 4 层 — 结构推断 coerce | ~15 行 | 兜底处理未知别名 |
| **可选** | 第 3 层 — warning 日志 | ~10 行 | 可审计性 |

**最有效的组合是第 1 层 + 第 2 层 + 第 4 层：**
- Prompt 示例减少偏差频率（从 ~10% 降到 ~2%）
- 别名映射兜住已知变体
- 结构推断兜住未知变体

第 4 层的 `coerce_file_change_delta` 放在 [normalize_file_change_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:613:0-724:21) **之前**调用，形成：

```
raw JSON → coerce (结构推断) → normalize (别名+格式) → merge → save
```

这样即使 LLM 发明了从未见过的 key 名，只要数据结构符合 list-of-dict-with-file 模式，就能正确处理。

---

要切换到 Code mode 实施吗？建议先做第 2 层 + 第 4 层（代码修复）+ 第 1 层（SKILL.md 文档更新），一共约 45 行改动。
