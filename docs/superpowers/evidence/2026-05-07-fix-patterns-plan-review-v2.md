

# 审核结果

## 设计文档 v2 — ✅ 通过

v1 审核的 4 项修正全部正确落实，且新增了关键改进：

| 修正项 | 状态 | 验证点 |
|--------|------|--------|
| [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) 签名不变 | ✅ | Section 3 line 193-194 |
| `risk_level` 单源头 | ✅ | Section 1 line 60 + Section 3 line 178 |
| 只保留 chunk 级 `unique_fix_patterns` | ✅ | Section 2 line 103-107 |
| prompt 用 MUST + 禁止 | ✅ | Section 4 line 211 |
| 降级/容错 | ✅ | line 30-32 + Section 3 line 197-202 |
| 测试规划 | ✅ | Section 5 |
| **新增**：[parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) 完全不修改 | ✅ | Section 3 line 187, 194 |
| **新增**：chunk 组装时直接调 `lookup_fix_pattern()` | ✅ | Section 3 line 170-186 |

设计文档无遗留问题。

---

## 实施计划 — ⚠️ 1 个结构性问题

### 问题：Task 4 内部自相矛盾

Task 4 同时保留了**旧方案**和**新方案**的指令，一个 agentic worker 按步骤执行会陷入混乱。

**Step 1（line 335-366）** 指示修改 [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31)：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/plans/2026-05-07-fix-patterns.md:335-366
- [ ] **Step 1: Modify parse_xml() to accept fix_patterns parameter and attach _fix_pattern**

Change the [parse_xml](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) function signature to accept `fix_patterns`:

```python
def parse_xml(xml_file: Path, config: Dict[str, Any], policy: Dict[str, Any], strategy: str, fix_patterns: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
```

After the [classify_issue()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:86:0-118:5) call on line 157, add:

```python
        issue_policy = classify_issue(rule_id, msg, policy, strategy, strategy_config)

        # Lookup fix pattern (independent of classify_issue)
        fix_pattern = lookup_fix_pattern(rule_id, issue_policy.get("risk_level", "high"), fix_patterns)
```

In the `dedup[key]` dict (line 163), add `_fix_pattern`:

```python
        dedup[key] = {
            "issue_key": build_issue_key(file_path, line, rule_id, msg),
            "file": file_path,
            "line": line,
            "severity": severity,
            "rule_id": rule_id,
            "msg": msg,
            "is_misra": is_misra_rule(rule_id, detect_prefixes),
            "fix_strategy": strategy,
            **issue_policy,
            "_fix_pattern": fix_pattern,
        }
```
```

然后 **Step 2 末尾（line 427-429）** 又说完全不改 [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31)：

```@//wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/plans/2026-05-07-fix-patterns.md:427-429
So the final [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) change is: **no change to parse_xml() at all**. The `lookup_fix_pattern()` function added in Task 3 is used only in [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:221:0-321:12) during chunk assembly.
```

执行者会先做 Step 1（改 [parse_xml](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31)），然后读到 Step 2 末尾发现要撤销。

**具体矛盾链**：

| 位置 | 说的是 | 与设计文档一致？ |
|------|--------|------------------|
| Step 1 标题 | "Modify parse_xml()" | ❌ 设计文档 Section 3 line 194 明确说不改 |
| Step 1 内容 | 改签名、加 `_fix_pattern` | ❌ |
| Step 2 line 380-381 | [parse_xml(…, fix_patterns)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) | ❌ parse_xml 不接受此参数 |
| Step 2 line 384-393 | 在 save issues_master.json 后 strip `_fix_pattern` | ❌ 不存在此字段 |
| Step 2 line 395-429 | "Revised approach… no change to parse_xml()" | ✅ 但与上面矛盾 |

**连带影响**：

- **Task 4 标题**（line 329）："Integrate fix_pattern lookup into parse_xml() and chunk assembly" — [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) 不改
- **Task 4 commit message**（line 521）："integrate fix_pattern lookup into parse_xml and chunk assembly" — 同上
- **Task 5 Step 1**（line 534）："In [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31), the default `fix_patterns=None` means…" — [parse_xml()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:120:0-174:31) 没有此参数
- **Plan header**（line 7）："attaches pattern data to issues via…" — 不再 attach 到 issues

### 建议修改

**Task 4 应重写为只包含最终方案**：

1. **删除 Step 1 整体**（line 335-366）
2. **Step 2 重写**：只保留 line 400-422 的 chunk assembly 代码 + `fix_patterns = load_json(FIX_PATTERNS_PATH, {})` 的加载逻辑。移除 line 369-398 所有涉及 parse_xml 修改和 _fix_pattern stripping 的内容
3. **修改标题**为 "Integrate fix_pattern lookup into chunk assembly"
4. **修改 commit message** 为 `"feat: compute unique_fix_patterns during chunk assembly"`
5. **Task 5 Step 1**：删除对 parse_xml 接受 fix_patterns 参数的引用
6. **Plan header line 7**：改 "attaches pattern data to issues" 为 "computes unique_fix_patterns at chunk assembly time"

---

## 总结

| 文件 | 判定 |
|------|------|
| **design v2** | ✅ 通过 |
| **plan v2** | ⚠️ Task 4 需清理旧方案残留，涉及 6 处修改 |

核心原因：plan 保留了思考过程（旧方案→新方案的推导），但 agentic worker 需要的是**最终指令**，不是推导过程。设计文档已经是对的，plan 只需要与之对齐即可。
