## 审核结果

两份文档质量高，逻辑链完整，6 个问题全部覆盖。以下是发现的几个需要修正的点：

---

### 问题 1 — SKILL.md 路径错误

**Plan Step 6** 写的是 `.agents/skills/cppcheck-misra-fix/SKILL.md`，但这个路径不存在。实际的主文件是：

```
.claude/skills/cppcheck-misra-fix/SKILL.md
.codex/skills/cppcheck-misra-fix/SKILL.md
.opencode/skills/cppcheck-misra-fix/SKILL.md
```

Design 中也写了 "在 `.agents/skills/cppcheck-misra-fix/SKILL.md`"——应修正为 [.claude/skills/cppcheck-misra-fix/SKILL.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.claude/skills/cppcheck-misra-fix/SKILL.md:0:0-0:0)（主文件）+ 同步到 `.codex/` 和 `.opencode/`。

---

### 问题 2 — Step 7 测试文件并非"新增"

Plan Step 7 标题是"新增测试文件"，但 [tests/test_normalization.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_normalization.py:0:0-0:0) **已存在**（422 行），且已有 [TestFileChangeDeltaWrapperAliases](cci:2://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_normalization.py:181:0-206:34) 等测试类。应改为"在 [tests/test_normalization.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_normalization.py:0:0-0:0) 中追加测试类"。

---

### 问题 3 — Step 5 验证引用可能不存在的文件

Plan Step 5 验证写"运行 `tests/test_run_pipeline.py`"。让我确认一下：

[tests/test_run_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_run_pipeline.py:0:0-0:0) 存在，这个引用没问题。继续审核其余细节：

---

### 问题 4 — Step 2b 直接修改 patch 引用（代码风格问题）

Plan Step 2b 的逻辑是：

```python
for issue_key, patch in issue_status_delta.items():
    ...
    if "chunk_index" not in patch:
        patch["chunk_index"] = int(chunk_index)  # 修改了原始 dict 的引用
```

`patch` 是 `issue_status_delta` 中的原始 dict 引用，直接 mutate 会修改输入参数。虽然函数调用后 `issue_status_delta` 不再使用，但这是 defensive coding 的反模式。建议在遍历时 copy：

```python
    normalized_patch = dict(patch)
    if "chunk_index" not in normalized_patch:
        normalized_patch["chunk_index"] = int(chunk_index)
    ...
    normalized[issue_key] = normalized_patch
```

---

### 问题 5 — Step 1b 中 line 710 的 raise 也需处理

Design 只提到 line 707 的 `raise ValueError("file_changes entry must be an object")`，但 line 710 还有一个：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:709-710
            if not file_path:
                raise ValueError("file_changes entry must include file")
```

Plan Step 1 确实在条目 "2" 的末尾写了"`file_path` 为空时：从 `raise ValueError` 改为 `continue` skip"，设计覆盖到了。但 Design 中只描述了 string 降级和非 dict skip，**没有明确提到空 file_path 的处理**。建议 Design 1b 节补充这一点。

---

### 问题 6 — 缺少对 [merge_file_change_index](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:638:0-659:17) 中 raise 的考量

`@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:645-646`:

```python
        if not isinstance(delta_entry, dict):
            raise ValueError(f"file_change_index entry must be an object: {file_path}")
```

[import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 中的调用顺序是：
```
normalize_file_change_delta → merge_file_change_index → save
```

Step 3 的安全网只包裹了 `normalize_*` 调用。如果 normalize 成功返回但 [merge_file_change_index](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:638:0-659:17) 抛异常，仍会导致 import 失败。

**实际风险低**：因为 normalize 现在永远不返回非 dict value（全部 skip），所以 merge 不会遇到非 dict。但严谨做法是将安全网范围扩大到覆盖 merge：

```python
try:
    file_change_delta = normalize_file_change_delta(...)
    merged_file_change_index = merge_file_change_index(file_change_index, file_change_delta)
except Exception as exc:
    print(f"[import] WARNING: ...")
    file_change_delta = {}
    merged_file_change_index = dict(file_change_index)
```

或者更简洁：将 Step 3 的安全网范围描述为"包裹 normalize + merge 的整个 data transformation 块"，而不仅仅是 normalize 单个调用。

---

### 问题 7 — Design 兼容性声明遗漏新增状态值

Design "兼容性" 节声明"现有成功路径行为不变"，但 Step 5a 引入了新状态值 `"chunk_failed"`。如果下游有代码对 `status` 做白名单检查（如 `if status not in ("pending", "fixed", "needs_manual_review", "blocked", "skipped")`），会产生问题。

"风险评估"中提到了这一点（"`chunk_failed` 是新增状态值，不影响现有状态机"），但建议在 Design 中明确列出哪些代码会消费 `issue_status.json` 的 status 字段，确认无白名单冲突。快速检查一下：


关键发现：[merge_results.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/merge_results.py:0:0-0:0) 中（line 148）已有 `status_counts.get('failed', 0)` 的统计，line 211 中 `review_statuses = {"needs_manual_review", "failed"}`。

这说明下游代码使用的是 **`defaultdict` 式计数**（line 59: `status_counts[status] += 1`），不做白名单过滤。新增 `"chunk_failed"` 不会导致报错，只会在报告中多出一个计数项。

但注意：**现有代码用的是 `"failed"` 不是 `"chunk_failed"`**。建议 Step 5a 的新状态值统一为 `"failed"` 而非 `"chunk_failed"`——这样 merge_results.py 无需改动就能正确统计。或者如果确实想区分"agent 运行时失败"和"导入失败"，可以保持 `"chunk_failed"` 但需要在 [merge_results.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/merge_results.py:0:0-0:0) line 148 和 line 211 中加入对该状态的处理。

---

## 审核总结

| # | 类型 | 说明 | 建议 |
|---|---|---|---|
| 1 | **路径错误** | SKILL.md 路径写为 `.agents/skills/...`，实际是 `.claude/skills/...` | 修正 Design 和 Plan |
| 2 | **措辞不准** | Plan Step 7 说"新增测试文件"，实际是追加到已有文件 | 改为"追加测试类" |
| 3 | ~~验证引用~~ | [tests/test_run_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_run_pipeline.py:0:0-0:0) 确认存在 | 无需修改 |
| 4 | **代码风格** | Step 2b 直接 mutate 输入参数 patch | 加 `dict(patch)` copy |
| 5 | **遗漏说明** | Design 1b 未提及空 file_path 时 skip（Plan 有但 Design 没有） | Design 补充一句 |
| 6 | **安全网范围** | Step 3 只包裹 normalize，未包裹 [merge_file_change_index](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:638:0-659:17) | 扩大 try/except 范围 |
| 7 | **状态值兼容** | `"chunk_failed"` vs [merge_results.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/merge_results.py:0:0-0:0) 已有的 `"failed"` | 建议直接用 `"failed"`，或在 merge_results.py 补充处理 |

其中 **#1、#6、#7** 影响正确性，建议实施前修正。其余为质量改善建议。

整体评价：设计清晰，降级安全网的架构决策正确，优先级排列合理。修正以上 7 点后即可实施。
