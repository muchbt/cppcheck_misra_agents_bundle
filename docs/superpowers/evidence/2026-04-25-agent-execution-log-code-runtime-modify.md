Let me gather the exact current state of all files that need changes.

Now let me also check the other SKILL.md copies and the compat AGENTS.md to see if they need the same update.

Now let me check the test files to understand existing test patterns.



Now I have all the context. Here's the complete plan:

---

# 完整修改方案

## 修改清单

| # | 文件 | 改动 | 性质 |
|---|------|------|------|
| 1 | [.agents/tools/common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) | 在 [normalize_file_change_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:613:0-724:21) 中增加 `files_inspected` 无编辑分支 | Bug fix |
| 2 | [.agents/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0) | 追加 Option C：inspection-only 格式 | Prompt 加固 |
| 3 | [.agents/compat/.claude/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/compat/.claude/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0) | 同步 SKILL.md | Prompt 加固 |
| 4 | [.agents/compat/.codex/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/compat/.codex/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0) | 同步 SKILL.md | Prompt 加固 |
| 5 | [.claude/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.claude/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0) | 同步 SKILL.md | Prompt 加固 |
| 6 | [.codex/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.codex/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0) | 同步 SKILL.md | Prompt 加固 |
| 7 | [tests/test_agent_staging.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_staging.py:0:0-0:0) | 新增 `test_import_accepts_files_inspected_schema` | 测试 |

---

## Step 1 — [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0)：新增 `files_inspected` 处理分支

在 [normalize_file_change_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:613:0-724:21) 函数中，在 `file_changes` 分支（line 665）之后、单文件分支（line 667）之前插入。

**插入位置：** `common.py:666`（当前是空行），在 `return normalized` 之后

**插入代码：**

```python
    # Handle files_inspected format: inspection-only records with no code edits.
    # Agent may output this when issues are marked for manual review without changes.
    # Normalize to canonical {filepath: {edits: []}} WITHOUT generating edit records.
    files_inspected = file_change_delta.get("files_inspected")
    if isinstance(files_inspected, list):
        normalized: Dict[str, Any] = {}
        for item in files_inspected:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file", "")).strip()
            if not file_path:
                continue
            entry: Dict[str, Any] = {"edits": []}
            change_summary = str(item.get("change_summary", "")).strip()
            if change_summary:
                entry["change_summary"] = change_summary
            normalized[file_path] = entry
        return normalized

```

**修改后 [normalize_file_change_delta](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:613:0-724:21) 完整结构：**

```python
def normalize_file_change_delta(
    base_file_change_index: Dict[str, Any],
    file_change_delta: Dict[str, Any],
    chunk_index: int,
) -> Dict[str, Any]:
    # --- 分支 1: file_changes 数组（有编辑） --- line 619-665
    file_changes = file_change_delta.get("file_changes")
    if isinstance(file_changes, list):
        ...  # 现有代码不变
        return normalized

    # --- 分支 2 [新增]: files_inspected 数组（无编辑） ---
    files_inspected = file_change_delta.get("files_inspected")
    if isinstance(files_inspected, list):
        normalized: Dict[str, Any] = {}
        for item in files_inspected:
            if not isinstance(item, dict):
                continue
            file_path = str(item.get("file", "")).strip()
            if not file_path:
                continue
            entry: Dict[str, Any] = {"edits": []}
            change_summary = str(item.get("change_summary", "")).strip()
            if change_summary:
                entry["change_summary"] = change_summary
            normalized[file_path] = entry
        return normalized

    # --- 分支 3: 单文件 dict --- line 667-716 (原位置偏移)
    single_file_path = file_change_delta.get("file")
    ...  # 现有代码不变

    # --- 分支 4: 扁平 dict fallback --- line 718-725 (原位置偏移)
    normalized = {}
    for file_path, delta_entry in file_change_delta.items():
        ...  # 现有代码不变
    return normalized
```

### 关键设计点

- **`edits: []` 空数组** — 不生成任何 edit_id，[_build_issue_edit_index()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:727:0-740:25) 返回空 dict，issue 不会被挂上伪 edit_ids
- **保留 `change_summary`** — 在 file_change_index 中留下审计线索（如 "No changes applied - issue marked for manual review"）
- **`continue` 跳过非 dict / 空 file** — 防御性处理，不 raise，因为 inspection 数据本身不是关键路径

---

## Step 2 — 4 份 SKILL.md 统一更新

所有 4 个 SKILL.md 内容完全相同，均修改 `# Staging output format contract` 部分。

**当前 line 45-49：**

```markdown
**file_change_delta.json:**
- Option A: Flat object `{file: data}` where data contains edits, change_summary, etc.
- Option B: Wrapper object `{file_changes: [{file, summary, linked_issues, ...}]}`

Keep field names stable and deterministic. Each edit must include `edit_id`, `summary`, `chunk_index`, and `related_issue_keys`.
```

**替换为：**

```markdown
**file_change_delta.json:**
- Option A: Flat object `{file_path: {edits: [...], change_summary: "..."}}` where each key is an actual file path
- Option B: Wrapper array `{file_changes: [{file, summary, linked_issues, edits: [...]}]}` — for chunks with code edits
- Option C: Inspection-only `{files_inspected: [{file, change_summary}]}` — for chunks where NO edits were applied (e.g. manual review)

⚠️ Use ONLY the key names above. Do NOT invent alternative key names (e.g. `changed_files`, `file_edits`).

Keep field names stable and deterministic. Each edit must include `edit_id`, `summary`, `chunk_index`, and `related_issue_keys`.
```

**需要修改的 4 个文件：**
- [.agents/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0)
- [.agents/compat/.claude/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/compat/.claude/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0)
- [.agents/compat/.codex/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/compat/.codex/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0)
- [.claude/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.claude/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0)
- [.codex/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.codex/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0)

（共 5 个副本，内容相同）

---

## Step 3 — [test_agent_staging.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_staging.py:0:0-0:0)：新增测试

在 [test_import_chunk_staging_artifacts_accepts_wrapped_agent_schema](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_staging.py:136:4-205:9) 之后（line 206），`if __name__` 之前，追加：

```python
    def test_import_accepts_files_inspected_schema(self) -> None:
        """Test that files_inspected format is treated as inspection-only (no edits)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / ".agents" / "runtime"
            results_dir = runtime_dir / "results"
            staging_dir = root / ".agents" / "staging" / "chunk_011"
            results_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            common.save_json(
                runtime_dir / "issue_status.json",
                {
                    "misra_advisory.c:11:misra-c2012-8.4:4a2c80d8": {
                        "status": "pending",
                    }
                },
            )
            common.save_json(runtime_dir / "file_change_index.json", {})
            common.save_json(
                staging_dir / "issue_status_delta.json",
                {
                    "misra_advisory.c:11:misra-c2012-8.4:4a2c80d8": {
                        "new_status": "needs_manual_review",
                        "risk_level": "high",
                        "risk_reason": "No rule-specific auto-fix policy is configured.",
                        "requires_review_after_fix": False,
                        "chunk_index": 11,
                        "edit_id": None,
                        "related_issue_keys": [],
                        "blocker": None,
                    }
                },
            )
            # Agent used files_inspected instead of file_changes — inspection-only
            common.save_json(
                staging_dir / "file_change_delta.json",
                {
                    "files_inspected": [
                        {
                            "file": "misra_advisory.c",
                            "linked_issues": ["misra_advisory.c:11:misra-c2012-8.4:4a2c80d8"],
                            "change_summary": "No changes applied - issue marked for manual review",
                            "edits": [],
                        }
                    ],
                    "chunk_index": 11,
                },
            )
            common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 11})
            (staging_dir / "chunk_result.md").write_text("# chunk 11\n", encoding="utf-8")

            common.import_chunk_staging_artifacts(
                staging_dir,
                11,
                runtime_dir=runtime_dir,
                results_dir=results_dir,
            )

            issue_status = common.load_json(runtime_dir / "issue_status.json", {})
            file_change_index = common.load_json(runtime_dir / "file_change_index.json", {})

        # Issue should be updated to needs_manual_review
        issue = issue_status["misra_advisory.c:11:misra-c2012-8.4:4a2c80d8"]
        self.assertEqual(issue["new_status"], "needs_manual_review")

        # File should appear in file_change_index with empty edits (no fake edit_ids)
        self.assertIn("misra_advisory.c", file_change_index)
        self.assertEqual(file_change_index["misra_advisory.c"]["edits"], [])
        self.assertEqual(
            file_change_index["misra_advisory.c"]["change_summary"],
            "No changes applied - issue marked for manual review",
        )
```

---

## 验证命令

```bash
# 运行 staging 相关测试
pytest -xvs tests/test_agent_staging.py

# 运行全部测试确认无回归
pytest -q tests/

# 重跑 chunk 011 验证修复
python3 .agents/tools/run_fix_pipeline.py --chunks 11
```

---

## 修改总量

| 文件 | 新增行 | 修改行 | 删除行 |
|------|--------|--------|--------|
| [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) | 16 | 0 | 0 |
| 5 × [SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.codex/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0) | 5×3=15 | 5×2=10 | 0 |
| [test_agent_staging.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_staging.py:0:0-0:0) | 60 | 0 | 0 |
| **合计** | **91** | **10** | **0** |

切到 Code mode 即可执行。
