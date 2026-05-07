




Now let me verify a few code details the plan references:







Good, I have a complete picture. Here's my review:

---

# 审核结果

## 设计文档（design v2）— ✅ 通过

v1 审核提出的 6 项修正全部已正确落实：

| 审核项 | 状态 |
|--------|------|
| [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 签名不变，独立 `lookup_fix_pattern()` | ✅ Section 3 |
| `risk_level` 单源头（来自 policy，fix_patterns.json 不存） | ✅ Section 1 + 加粗说明 |
| 只保留 chunk 级 `unique_fix_patterns`，issue 级不存 | ✅ Section 2 |
| prompt 引导语用 MUST + 禁止 | ✅ Section 4 |
| 降级/容错说明 | ✅ 架构节 + Section 3 |
| 测试规划 | ✅ Section 5 |

设计文档无遗留问题。

---

## 实施计划（plan）— ⚠️ 4 个问题需修正

### 问题 1：Task 1 插入位置描述不精确

Plan 写 "after line 18 (`PROMPTS_DIR`)"，但实际 `PROMPTS_DIR` 在 **line 18**，而 line 19-25 还有 `SKILLS_DIR`、`RUNTIME_DIR`、`CHUNKS_DIR` 等路径常量。

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:16-25
AGENTS_DIR = ROOT / ".agents"
CONFIG_DIR = AGENTS_DIR / "config"
PROMPTS_DIR = AGENTS_DIR / "prompts"
SKILLS_DIR = AGENTS_DIR / "skills"
RUNTIME_DIR = AGENTS_DIR / "runtime"
RUNS_DIR = AGENTS_DIR / "runs"
CHUNKS_DIR = RUNTIME_DIR / "chunks"
RESULTS_DIR = RUNTIME_DIR / "results"
LOGS_DIR = RUNTIME_DIR / "logs"
REPORTS_DIR = AGENTS_DIR / "reports"
```

**建议**：`FIX_PATTERNS_PATH` 应插在 line 25（`REPORTS_DIR`）之后，与其他路径常量放在一起，而不是 line 18 之后打断 SKILLS_DIR 等定义。

### 问题 2：Task 2 验证脚本中 `fix_patterns.json` 的 `patterns` key 下不应有 `risk_level`，但验证脚本未检查这一约束

Step 3 的验证脚本只检查 rule_id 覆盖率，没有验证 **patterns 中不含 `risk_level` 字段**（设计文档核心约束）。

**建议**：在 Step 3 验证脚本中增加：

```python
for rule_id, p in fp['patterns'].items():
    if 'risk_level' in p:
        print(f'ERROR: {rule_id} should not have risk_level in fix_patterns.json')
        sys.exit(1)
```

这已在 Task 7 的 `test_split_produces_unique_fix_patterns_in_chunks` 中测了，但 Task 2 的一次性验证脚本也应覆盖，因为生成 fix_patterns.json（~180 条）容易误加。

### 问题 3：Task 4 中 `_fix_pattern` 残留在 `issue_status.json`

Plan Task 4 Step 2 在 chunk 组装时 `issue.pop("_fix_pattern", None)` 清理临时字段。但注意 [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:221:0-321:12) 中 **line 256-278 先构建 `issue_status`，再构建 chunks**：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:256-279
    issue_status = {
        x["issue_key"]: {
            "status": "pending",
            "file": x["file"],
            "line": x["line"],
            "severity": x["severity"],
            "rule_id": x["rule_id"],
            "is_misra": x["is_misra"],
            "fix_strategy": x["fix_strategy"],
            "action": x["action"],
            "strategy_action": x["strategy_action"],
            "risk_level": x["risk_level"],
            "risk_tags": x["risk_tags"],
            "risk_reason": x["risk_reason"],
            "requires_review_after_fix": x["requires_review_after_fix"],
            "chunk_index": None,
            "edit_ids": [],
            "reason": "",
            "verified": False,
        }
        for x in issues
    }
    save_json(RUNTIME_DIR / "issue_status.json", issue_status)
    save_json(RUNTIME_DIR / "file_change_index.json", {})
```

`issue_status` 是白名单式构建（只取明确列出的字段），所以 `_fix_pattern` 不会泄漏到 `issue_status.json`。**这点没问题**，但 plan 没有说明为什么不需要担心这个——建议加一句注释说明安全性。

另外，**`issues_master.json`（line 254）会原样存储整个 issues 列表**：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:254
    save_json(RUNTIME_DIR / "issues_master.json", issues)
```

此时 `_fix_pattern` 还没有被 pop，会残留在 `issues_master.json` 中。虽然不影响功能，但这是一个内部临时字段泄漏到持久化文件的问题。

**建议**：在 [save_json(RUNTIME_DIR / "issues_master.json", issues)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:527:0-530:56) 之前不添加 `_fix_pattern`，或者调整顺序：先存 `issues_master.json`，再加 `_fix_pattern`。最简改法是把 `_fix_pattern` 的附加推迟到 chunk 组装阶段，而不是在 [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) 中。

### 问题 4：Task 7 集成测试用 `return` 跳过不够规范

```python
def test_split_produces_unique_fix_patterns_in_chunks():
    fp_path = ...
    if not fp_path.exists():
        return  # ← silent skip
```

**建议**：用 `pytest.skip("fix_patterns.json not yet populated")` 代替 `return`，这样测试报告中能看到 skip 原因而非静默通过。

---

## 总结

| 文件 | 判定 |
|------|------|
| **design v2** | ✅ 通过，无遗留问题 |
| **plan** | ⚠️ 需修正 4 处后可执行 |

关键修正优先级：
1. **问题 3**（`_fix_pattern` 泄漏到 `issues_master.json`）— **必须修**，否则运行时文件含内部字段
2. **问题 2**（验证脚本缺 `risk_level` 检查）— **应修**，防止生成时误加
3. **问题 1**（插入位置）— 建议修
4. **问题 4**（pytest.skip）— 建议修
