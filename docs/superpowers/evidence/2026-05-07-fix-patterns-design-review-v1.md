

Now let me verify the existing code paths this design depends on:






Now let me check the existing test coverage for [classify_issue](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) and chunk building:







Good, I have a full picture. Here's my review:

---

# 审核：[2026-05-07-fix-patterns-design.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/specs/2026-05-07-fix-patterns-design.md:0:0-0:0)

## ✅ 设计正确的部分

1. **分层架构清晰**：`fix_patterns.json`（静态数据）→ split 时预写入 chunk → LLM 自行读取。正确地避免了 SKILL.md 膨胀和运行时额外 IO。

2. **risk-based 分级详细度是亮点**：low 只给 `fix`+`example`，high 额外给 `pitfalls`+`context_notes`，token 开销和信息密度成正比。

3. **双层注入（issue 级 + chunk 级去重）合理**：`unique_fix_patterns` 是给 LLM 的索引表，`fix_pattern` 在每个 issue 上便于逐条对照。

4. **不改 [base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0)/[build_chunk_prompt()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:97:0-108:5)**：LLM 直接从 chunk JSON 读 pattern，prompt 模板只加一句引导语，改动范围最小化。

---

## ⚠️ 需要修正或补充的问题

### 1. [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 签名改动与调用方不匹配

设计文档写的伪代码签名是 [classify_issue(issue, rule_policy, fix_patterns)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5)，但实际签名是：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:87-93
def classify_issue(
    rule_id: str,
    msg: str,
    policy: Dict[str, Any],
    strategy: str,
    strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
```

调用处在 [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) line 157：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:157
        issue_policy = classify_issue(rule_id, msg, policy, strategy, strategy_config)
```

**建议**：不要改 [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 的签名。fix_pattern 查找应该**单独做**，在 [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) 里 [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 返回后再附加：

```python
issue_policy = classify_issue(rule_id, msg, policy, strategy, strategy_config)
# fix_pattern 查找（新增）
fix_pattern = lookup_fix_pattern(rule_id, issue_policy.get("risk_level", "high"), fix_patterns)

dedup[key] = {
    ...
    **issue_policy,
    "fix_pattern": fix_pattern,  # 新增
}
```

这样 [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 保持纯策略逻辑，pattern 查找独立函数，职责清晰。

### 2. risk_level 来源冲突

设计文档说 `fix_patterns.json` 中每条 pattern 自带 `risk_level`，并用这个 level 决定输出哪些字段。但 **issue 的 `risk_level` 是由 [rule_policy.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/rule_policy.json:0:0-0:0) 通过 [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 决定的**，两者可能不同。

例如 [rule_policy.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/rule_policy.json:0:0-0:0) 对 `misra-c2012-17.7` 给 `risk_level: "high"`，但如果 `fix_patterns.json` 里写了 `risk_level: "medium"`，以哪个为准？

**建议**：`fix_patterns.json` 中**不存 `risk_level`**。分级裁剪时使用 [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 返回的 `risk_level`（来自 rule_policy）作为唯一来源：

```python
def lookup_fix_pattern(rule_id: str, risk_level: str, fix_patterns: Dict) -> Optional[Dict]:
    pattern = fix_patterns.get("patterns", {}).get(rule_id)
    if not pattern:
        return None
    fields = RISK_DETAIL_FIELDS.get(risk_level, RISK_DETAIL_FIELDS["high"])
    return {k: pattern[k] for k in fields if k in pattern}
```

这样 policy 管"能不能做 + 风险等级"，pattern 管"怎么做"，`risk_level` 单一来源于 policy。

### 3. `unique_fix_patterns` 与 `fix_pattern` 冗余度问题

每个 issue 已经有 `fix_pattern` 字段，chunk 顶层又有 `unique_fix_patterns`。对 LLM 来说这是**重复信息**——同一条 pattern 在 chunk JSON 中出现多次（一次在 unique 里，N 次在 issues 里）。

**建议二选一**：

- **方案 A（推荐）**：只保留 `unique_fix_patterns`，issue 级不存 `fix_pattern`。LLM 通过 `rule_id` 查 `unique_fix_patterns`。省 token。
- **方案 B**：只保留 issue 级 `fix_pattern`，不要 `unique_fix_patterns`。每个 issue 自包含。

如果选方案 A，chunk JSON 更紧凑：

```json
{
  "unique_fix_patterns": { "misra-c2012-11.3": {...}, ... },
  "issues": [
    { "rule_id": "misra-c2012-11.3", ... }   // 无 fix_pattern 字段
  ]
}
```

典型 chunk 12 个 issue 含 3 个 unique rule_id：方案 A 存 3 份 pattern，当前设计存 3+12=15 份。

### 4. prompt 引导语措辞可以更强约束

当前设计在 [fix_chunk_prompt.txt](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/prompts/fix_chunk_prompt.txt:0:0-0:0) 加的引导语：

> *"For each issue, follow the fix pattern specified in the chunk JSON's "unique_fix_patterns" field for that rule_id. If a pattern exists, use the exact approach described; if not, apply the general minimal-edit principle from the skill."*

建议改为更强的约束（减少 LLM 发挥空间）：

> *"For each issue whose rule_id appears in unique_fix_patterns, you MUST use the exact fix approach described there. Do NOT invent alternative fix methods when a pattern is provided."*

### 5. 缺少降级/容错说明

`fix_patterns.json` 不存在或为空时的行为没有说明。应在文档中明确：

> 如果 `fix_patterns.json` 不存在或 `patterns` 为空，split 正常运行，所有 issue 的 `fix_pattern` 为 null，`unique_fix_patterns` 为空对象。LLM 回退到 SKILL.md 通用原则。

### 6. 缺少测试规划

改动涉及 [split_cppcheck_xml.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:0:0-0:0) 核心路径，应补充测试用例：
- `test_classify_with_fix_pattern_low_risk`
- `test_classify_with_fix_pattern_high_risk_includes_pitfalls`
- `test_classify_with_missing_pattern_returns_null`
- `test_chunk_unique_fix_patterns_dedup`
- `test_split_without_fix_patterns_file_graceful_fallback`

---

## 修订建议清单

| # | 问题 | 修改 |
|---|------|------|
| 1 | [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 签名不应改变 | 新增独立 `lookup_fix_pattern()` 函数 |
| 2 | `risk_level` 双源头 | `fix_patterns.json` 中去掉 `risk_level`，裁剪时用 policy 的 |
| 3 | issue 级和 chunk 级 pattern 冗余 | 只保留 `unique_fix_patterns`，issue 级不存 `fix_pattern` |
| 4 | prompt 引导语约束力不够 | 用 MUST + 禁止替代措辞 |
| 5 | 缺容错说明 | 补充 `fix_patterns.json` 缺失时的降级行为 |
| 6 | 缺测试规划 | 补充 5 个测试用例 |
