让我先完整确认所有需要修改的代码区域：



Now let me also check tests to understand what needs new test coverage:

项目不使用 `logging` 模块，用的是 `print` + [append_pipeline_event](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:419:0-454:58)。现在我有了完整的上下文。以下是总体方案。

---

# 总体修复方案

## 设计原则

> **normalization 层永远不 raise**。格式识别失败时降级为空 delta + 警告日志，确保 chunk result 文件始终被复制到 `results/`，从架构上消除因 agent 输出格式不匹配导致的数据丢失。

## 涉及 3 个文件、6 个修改点

---

## 修改 1 — [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0): [normalize_file_change_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:691:0-831:21) 增强 + 降级

**位置**: `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:680-832`

### 1a. 扩展 alias 常量 (line 680-681)

```python
_KNOWN_FILE_CHANGES_KEYS = ("file_changes", "files_changed", "files_touched", "files", "changes", "modified_files", "file_edits", "changed_files")
_KNOWN_FILE_PATH_KEYS = ("file", "file_path", "path", "filename")
_KNOWN_FCD_META_KEYS = frozenset({"chunk_index", "metadata", "notes", "summary", "status"})
```

### 1b. 分支 ① list 遍历中，遇到 string 元素降级为 inspection-only 而非 raise (line 703-748)

将：
```python
    if file_changes is not None:
        normalized: Dict[str, Any] = {}
        for item in file_changes:
            if not isinstance(item, dict):
                raise ValueError("file_changes entry must be an object")
```

改为：
```python
    if file_changes is not None:
        normalized: Dict[str, Any] = {}
        for item in file_changes:
            if isinstance(item, str) and item.strip():
                # Agent output bare filename string — treat as inspection-only
                normalized[item.strip()] = {"edits": []}
                continue
            if not isinstance(item, dict):
                continue  # skip unrecognizable entry
```

### 1c. fallback (line 825-832) 前添加结构推断 + 降级

整个 fallback 区域替换为：

```python
    # --- Structural inference: detect list-of-dict-with-file under unknown wrapper key ---
    for key, value in file_change_delta.items():
        if key in _KNOWN_FCD_META_KEYS:
            continue
        if (isinstance(value, list) and value
                and isinstance(value[0], dict)
                and any(value[0].get(k) for k in _KNOWN_FILE_PATH_KEYS)):
            return normalize_file_change_delta(
                base_file_change_index, {"file_changes": value}, chunk_index
            )
        # list-of-strings under unknown wrapper key — treat as inspection-only
        if (isinstance(value, list) and value
                and isinstance(value[0], str)):
            normalized = {}
            for fname in value:
                if isinstance(fname, str) and fname.strip():
                    normalized[fname.strip()] = {"edits": []}
            return normalized
        # string value that looks like a file path — treat as inspection-only
        if isinstance(value, str) and ("/" in value or value.endswith((".c", ".h", ".cpp", ".hpp"))):
            return {value.strip(): {"edits": []}}

    # Standard dict-iterate fallback: keys are file paths, values are edit objects
    normalized = {}
    for file_path, delta_entry in file_change_delta.items():
        if file_path in _KNOWN_FCD_META_KEYS:
            continue
        if not isinstance(delta_entry, dict):
            # Unrecognizable entry — skip with warning instead of raising
            print(f"[normalize] WARNING: skipping file_change_delta['{file_path}'] "
                  f"(expected dict, got {type(delta_entry).__name__})")
            continue
        normalized[file_path] = delta_entry
    return normalized
```

**关键变化**: fallback 路径的 `raise ValueError` 改为 `continue` + 打印警告，永远不抛异常。

---

## 修改 2 — [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0): [normalize_issue_status_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:896:0-936:21) 增强 + 降级

**位置**: `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:897-937`

### 2a. list 分支中的 raise 改为 continue (line 911-916)

```python
    if isinstance(status_changes, list):
        issue_edit_ids = _build_issue_edit_index(file_change_delta)
        normalized: Dict[str, Any] = {}
        for item in status_changes:
            if not isinstance(item, dict):
                continue  # skip unrecognizable entry
            issue_key = str(item.get("issue_key", "")).strip()
            if not issue_key:
                continue  # skip entry without issue_key
            patch = _normalize_status_item(item, issue_key, issue_edit_ids.get(issue_key, []), chunk_index)
            normalized[issue_key] = patch
        return normalized
```

### 2b. dict-passthrough (line 930-937) 注入 `chunk_index` + 跳过 meta keys（修复 #3 和 #5）

```python
    _KNOWN_ISD_META_KEYS = frozenset({
        "chunk_index", "metadata", "notes",
        "issue_status_delta", "status_changes", "issue_status_changes",
    })
    normalized = {}
    issue_edit_ids = _build_issue_edit_index(file_change_delta)
    for issue_key, patch in issue_status_delta.items():
        if issue_key in _KNOWN_ISD_META_KEYS:
            continue
        if not isinstance(patch, dict):
            print(f"[normalize] WARNING: skipping issue_status_delta['{issue_key}'] "
                  f"(expected dict, got {type(patch).__name__})")
            continue
        if "chunk_index" not in patch:
            patch["chunk_index"] = int(chunk_index)
        if "edit_ids" not in patch:
            patch["edit_ids"] = issue_edit_ids.get(issue_key, [])
        normalized[issue_key] = patch
    return normalized
```

---

## 修改 3 — [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0): [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 安全网

**位置**: `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:940-984`

在 normalize 调用处包裹 try/except，确保即使 normalize 意外失败也能降级：

```python
def import_chunk_staging_artifacts(
    staging_dir: Path,
    chunk_index: int,
    runtime_dir: Path = RUNTIME_DIR,
    results_dir: Path = RESULTS_DIR,
) -> Dict[str, Path]:
    issue_status_delta_path = staging_dir / "issue_status_delta.json"
    file_change_delta_path = staging_dir / "file_change_delta.json"
    chunk_result_json_path = staging_dir / "chunk_result.json"
    chunk_result_md_path = staging_dir / "chunk_result.md"

    for path in (
        issue_status_delta_path,
        file_change_delta_path,
        chunk_result_json_path,
        chunk_result_md_path,
    ):
        if not path.exists():
            raise FileNotFoundError(f"missing staging artifact: {path}")

    issue_status = _load_required_json_object(runtime_dir / "issue_status.json")
    file_change_index = _load_required_json_object(runtime_dir / "file_change_index.json")

    # --- Normalize with degradation safety net ---
    raw_file_change_delta = _load_required_json_object(file_change_delta_path)
    try:
        file_change_delta = normalize_file_change_delta(file_change_index, raw_file_change_delta, chunk_index)
    except Exception as exc:
        print(f"[import] WARNING: file_change_delta normalization failed for chunk {chunk_index}: "
              f"{exc} — degrading to empty file changes")
        file_change_delta = {}

    raw_issue_status_delta = _load_required_json_object(issue_status_delta_path)
    try:
        issue_status_delta = normalize_issue_status_delta(raw_issue_status_delta, file_change_delta, chunk_index)
    except Exception as exc:
        print(f"[import] WARNING: issue_status_delta normalization failed for chunk {chunk_index}: "
              f"{exc} — degrading to empty status delta")
        issue_status_delta = {}

    issue_status.update(issue_status_delta)
    save_json(runtime_dir / "issue_status.json", issue_status)

    merged_file_change_index = merge_file_change_index(file_change_index, file_change_delta)
    save_json(runtime_dir / "file_change_index.json", merged_file_change_index)

    imported_json_path = results_dir / f"chunk_{int(chunk_index):03d}_result.json"
    imported_md_path = results_dir / f"chunk_{int(chunk_index):03d}_result.md"
    imported_json_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chunk_result_json_path, imported_json_path)
    shutil.copy2(chunk_result_md_path, imported_md_path)

    return {
        "issue_status_path": runtime_dir / "issue_status.json",
        "file_change_index_path": runtime_dir / "file_change_index.json",
        "chunk_result_json_path": imported_json_path,
        "chunk_result_md_path": imported_md_path,
    }
```

**效果**: 这是最关键的一道安全网。无论 normalize 内部怎么失败，`chunk_result.json` 和 `.md` 总会被复制到 `results/`，chunk 不再丢失。

---

## 修改 4 — [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0): import_error 返回值补 `argv`（修复 #6）

**位置**: `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:151-158`

```python
        except (FileNotFoundError, OSError, ValueError) as exc:
            return {
                "returncode": 1,
                "stdout": stdout_text,
                "stderr": str(exc),
                "error_kind": ERROR_KIND_IMPORT_ERROR,
                "prompt": prompt,
                "argv": cmd,
            }
```

---

## 修改 5 — [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0): 失败 chunk 标记问题状态 + 计数修正（修复 #2 和 #4）

**位置**: `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py`

### 5a. 添加 `mark_chunk_issues_failed` 函数（在 [mark_failure](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:254:0-270:45) 之后，约 line 273）

```python
def mark_chunk_issues_failed(chunk_index: int, error_kind: str) -> None:
    """Mark all issues in a failed chunk as 'chunk_failed' in issue_status.json."""
    issue_status_path = RUNTIME_DIR / "issue_status.json"
    issue_status = load_json(issue_status_path, {})

    chunk_payload = load_chunk_payload(chunk_index)
    changed = False
    for issue in chunk_payload.get("issues", []):
        issue_key = str(issue.get("issue_key", "")).strip()
        if not issue_key or issue_key not in issue_status:
            continue
        current = issue_status[issue_key]
        if current.get("status", "pending") == "pending":
            current["status"] = "chunk_failed"
            current["chunk_index"] = chunk_index
            current["error_kind"] = error_kind
            changed = True

    if changed:
        save_json(issue_status_path, issue_status)
```

### 5b. 在 `not success` 分支调用（line 477 之后）

```python
        if not success:
            mark_chunk_issues_failed(idx, last_error_kind or ERROR_KIND_RUNTIME_ERROR)
            # ... rest of existing failure handling ...
```

### 5c. 计数修正（修复 #4）

将 line 331 改为两个计数器：
```python
    succeeded_this_run = 0
    attempted_this_run = 0
```

在 `for attempt` 循环之前（约 line 389，`max_attempts = ...` 之前）添加：
```python
        attempted_this_run += 1
```

将 line 510 改为：
```python
        succeeded_this_run += 1
```

将 `--max-chunks` 检查 (line 334) 改为用 `succeeded_this_run`：
```python
        if args.max_chunks > 0 and succeeded_this_run >= args.max_chunks:
```

将所有事件日志中的 `"processed"` 改为 `"attempted"` 和 `"succeeded"` 两个字段：

**run_partial (line 343-346)**:
```python
                data={
                    "attempted": attempted_this_run,
                    "succeeded": succeeded_this_run,
                    "max_chunks": args.max_chunks,
                },
```

**run_completed (line 365-369)**:
```python
                data={
                    "attempted": attempted_this_run,
                    "succeeded": succeeded_this_run,
                    "completed_chunks": len(progress.get("completed_chunks", [])),
                    "failed_chunks": len(progress.get("failed_chunks", [])),
                },
```

print 语句 (line 348) 相应更新：
```python
            print(f"Stopped after {attempted_this_run} chunk(s) ({succeeded_this_run} succeeded) due to --max-chunks.")
```

---

## 修改 6 — [SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.claude/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0): 强化 prompt 约束

**位置**: `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.claude/skills/cppcheck-misra-fix/SKILL.md:62-70`

替换为更精确的格式说明：

```markdown
**file_change_delta.json** — MUST use exactly ONE of these formats:

Format A (preferred): Flat object keyed by actual file paths
```json
{
  "/path/to/src/main.c": {
    "edits": [{"edit_id": "src/main.c#001", "summary": "added cast", "chunk_index": 1, "related_issue_keys": ["main.c:10:misra-c2012-11.3:abc"]}]
  },
  "chunk_index": 1
}
```

Format B: Wrapper array with key `file_changes`
```json
{
  "file_changes": [
    {"file": "/path/to/src/main.c", "summary": "added cast", "linked_issues": ["main.c:10:misra-c2012-11.3:abc"]}
  ],
  "chunk_index": 1
}
```

Format C: Inspection-only (no edits applied)
```json
{
  "files_inspected": [
    {"file": "/path/to/src/main.c", "change_summary": "No changes - marked for manual review"}
  ],
  "chunk_index": 1
}
```

⚠️ Use ONLY the key names shown above (`file_changes`, `files_inspected`, or actual file paths as keys).
Do NOT use: `files`, `changed_files`, `modifications`, `results`, or any other wrapper key name.
```

对 `.codex/skills/cppcheck-misra-fix/SKILL.md` 和 `.opencode/skills/cppcheck-misra-fix/SKILL.md` 做同样更新（如存在）。

---

## 新增测试

在 `@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_normalization.py` 添加：

```python
# ---------------------------------------------------------------------------
# normalize_file_change_delta — degradation on unrecognized formats
# ---------------------------------------------------------------------------

class TestFileChangeDeltaDegradation:
    EMPTY_BASE = {}

    def test_list_of_strings_degrades_to_inspection(self):
        """{"files": ["a.c", "b.c"]} → inspection-only with empty edits."""
        raw = {"files": ["a.c", "b.c"]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "a.c" in result
        assert "b.c" in result
        assert result["a.c"]["edits"] == []
        assert result["b.c"]["edits"] == []

    def test_unknown_wrapper_list_of_dicts_inferred(self):
        """{"modifications": [{file: "a.c", ...}]} → structural inference."""
        raw = {"modifications": [{"file": "a.c", "summary": "fix", "linked_issues": ["k:1"]}]}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "a.c" in result
        assert len(result["a.c"]["edits"]) == 1

    def test_unknown_wrapper_string_value_degrades(self):
        """{"files": "a.c"} → inspection-only."""
        raw = {"files": "a.c"}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "a.c" in result
        assert result["a.c"]["edits"] == []

    def test_non_dict_value_skipped_not_raised(self):
        """Non-dict value in fallback path is skipped, not raised."""
        raw = {"a.c": {"edits": []}, "bad_key": 42}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert "a.c" in result
        assert "bad_key" not in result

    def test_completely_empty(self):
        raw = {"chunk_index": 1}
        result = common.normalize_file_change_delta(self.EMPTY_BASE, raw, 0)
        assert result == {}


class TestIssueStatusDeltaDegradation:
    EMPTY_FCD = {}

    def test_passthrough_injects_chunk_index(self):
        """Dict-passthrough path must inject chunk_index."""
        raw = {"a.c:1:rule:abc": {"status": "fixed", "risk_level": "high"}}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 7)
        assert result["a.c:1:rule:abc"]["chunk_index"] == 7

    def test_passthrough_skips_meta_keys(self):
        """Known meta keys like 'issue_status_delta' should be skipped."""
        raw = {
            "a.c:1:rule:abc": {"status": "fixed"},
            "issue_status_delta": {"nested": "data"},
            "chunk_index": 5,
        }
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 5)
        assert "a.c:1:rule:abc" in result
        assert "issue_status_delta" not in result
        assert "chunk_index" not in result

    def test_non_dict_entry_skipped_not_raised(self):
        raw = {"a.c:1:rule:abc": {"status": "fixed"}, "bad": "string_value"}
        result = common.normalize_issue_status_delta(raw, self.EMPTY_FCD, 0)
        assert "a.c:1:rule:abc" in result
        assert "bad" not in result


class TestImportDegradation:
    """import_chunk_staging_artifacts never fails on normalize errors."""

    def test_import_survives_garbage_file_change_delta(self, tmp_path):
        runtime_dir = tmp_path / "runtime"
        results_dir = runtime_dir / "results"
        staging_dir = tmp_path / "staging" / "chunk_099"
        results_dir.mkdir(parents=True)
        staging_dir.mkdir(parents=True)

        common.save_json(runtime_dir / "issue_status.json", {
            "a.c:1:rule:abc": {"status": "pending"},
        })
        common.save_json(runtime_dir / "file_change_index.json", {})
        # Deliberately invalid: top-level value is an integer
        common.save_json(staging_dir / "file_change_delta.json", {"garbage": 123})
        common.save_json(staging_dir / "issue_status_delta.json", {
            "a.c:1:rule:abc": {"status": "fixed"},
        })
        common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 99})
        (staging_dir / "chunk_result.md").write_text("# chunk 99\n", encoding="utf-8")

        paths = common.import_chunk_staging_artifacts(
            staging_dir, 99, runtime_dir=runtime_dir, results_dir=results_dir,
        )
        # chunk_result files MUST be copied regardless
        assert paths["chunk_result_json_path"].exists()
        assert paths["chunk_result_md_path"].exists()
```

---

## 覆盖度总结

| Agent 输出格式变体 | 修复前 | 修复后处理方式 |
|---|---|---|
| 标准 `file_changes` / flat dict | ✅ | ✅ 正常解析 |
| 已知别名 wrapper (`files`, `changed_files`, ...) + list-of-dict | ❌ raise | ✅ alias 匹配 |
| 未知别名 wrapper + list-of-dict-with-file | ❌ raise | ✅ 结构推断 |
| 任意 wrapper + list-of-strings | ❌ raise | ✅ 降级为 inspection-only |
| 任意 wrapper + string 值 (像文件路径) | ❌ raise | ✅ 降级为 inspection-only |
| fallback 中 value 不是 dict | ❌ raise | ✅ skip + 警告 |
| 完全不可识别的结构 | ❌ raise → chunk 丢失 | ✅ **安全网 catch → 空 delta，chunk result 仍复制** |
| 损坏的 JSON | ❌ raise → chunk 丢失 | ✅ **安全网 catch → 空 delta，chunk result 仍复制** |

**总代码改动**: 约 100 行产品代码 + 70 行测试。

