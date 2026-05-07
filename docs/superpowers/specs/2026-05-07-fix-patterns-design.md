# Fix Patterns 设计文档

> 日期：2026-05-07
> 状态：待审核

## 目标

1. **约束 LLM 行为**：为每条规则提供规范化的修复模式，减少 LLM 臆造/创新修复方式
2. **控制 Token 消耗**：按 chunk 动态注入只涉及的规则 pattern，而非全量写入 SKILL.md
3. **覆盖所有规则**：为 templates 下所有去重后的 rule_id 推荐一套 fix pattern（包括 needs_manual_review 规则）

## Token 开销对比

| 方案 | 每 chunk 额外 token | 约束力 |
|------|---------------------|--------|
| 全量写入 SKILL.md | +5000~8000 | 强 |
| **按 chunk 预写入 + 去重**（本方案） | **+100~400** | **强** |
| 不注入，仅靠 SKILL.md 通用描述 | 0 | 弱 |

## 架构：分层 + 预写入

```
fix_patterns.json          ← 全量规则→修复模式映射（静态数据文件，不进 prompt）
    ↓ split_cppcheck_xml.py 分类阶段查找
chunk JSON                 ← 每个对象携带 fix_pattern 字段 + chunk 级去重锚点
    ↓ LLM 读取 chunk JSON 时自然获取
SKILL.md (不变)            ← 通用原则（不膨胀）
```

## Section 1：数据层 — fix_patterns.json

**位置**：`.agents/config/fix_patterns.json`

### Schema

```json
{
  "_meta": "Canonical fix patterns for cppcheck/MISRA rules. Injected into chunk JSON per-rule.",
  "risk_detail_levels": {
    "low": ["fix", "example"],
    "medium": ["fix", "example", "caution"],
    "high": ["fix", "example", "pitfalls", "context_notes"]
  },
  "patterns": {
    "<rule_id>": {
      "risk_level": "low|medium|high",
      "fix": "简要修复描述",
      "example": "代码示例 /* fix: rule_id — 修复说明 */",
      "caution": "中等风险注意事项（仅 medium+）",
      "pitfalls": "高风险常见陷阱（仅 high）",
      "context_notes": "高风险上下文提示（仅 high）"
    }
  }
}
```

### 分级详细度

| risk_level | 包含字段 | 预估 token/条 |
|---|---|---|
| low | `fix` + `example` | ~30-50 |
| medium | `fix` + `example` + `caution` | ~60-80 |
| high | `fix` + `example` + `pitfalls` + `context_notes` | ~100-120 |

### 覆盖范围

- 所有去重后的 rule_id（跨 `misra_c2012_conservative.json`、`misra_c2012_relaxed.json`、`cppcheck_common.json`、`autosar_baseline.json`、`rule_policy.json`）
- risk_level 来自 rule_policy（exact match → pattern match → default）
- pattern 与 policy 解耦：policy 管"能不能做"，pattern 管"怎么做"
- 对于 fix_patterns.json 中没有条目的 rule_id，LLM 回退到 SKILL.md 通用原则

### 示例

```json
{
  "unusedVariable": {
    "risk_level": "low",
    "fix": "Remove the unused variable declaration.",
    "example": "/* fix: unusedVariable — removed unused variable 'x' */"
  },
  "misra-c2012-8.13": {
    "risk_level": "medium",
    "fix": "Add const qualifier to pointer parameter where the pointed-to data is not modified.",
    "example": "void foo(uint8_t * const p); /* fix: misra-c2012-8.13 — added const qualifier */",
    "caution": "Verify that the function implementation does not modify the data through this pointer."
  },
  "misra-c2012-17.7": {
    "risk_level": "high",
    "fix": "Cast unused return value to void, or capture and check the return value.",
    "example": "(void)memset(buf, 0, sz); /* fix: misra-c2012-17.7 — discard unused return */",
    "pitfalls": "Silently discarding return values may hide errors. If the function can fail, prefer capturing and checking the return value.",
    "context_notes": "In safety-critical code, consider using the return value for error path handling rather than (void) cast."
  }
}
```

## Section 2：Chunk JSON 变更

### Issue 对象新增字段

每个 issue 对象增加 `fix_pattern` 字段：

```json
{
  "issue_key": "cppcheck_error.c:3:misra-c2012-8.4:4a2c80d8",
  "file": "cppcheck_error.c",
  "line": 3,
  "severity": "style",
  "rule_id": "misra-c2012-8.4",
  "msg": "misra violation (use --rule-texts=<file> to get proper output)",
  "is_misra": true,
  "fix_strategy": "all_auto",
  "action": "needs_manual_review",
  "strategy_action": "careful_fix",
  "risk_level": "high",
  "risk_tags": ["unknown_rule"],
  "risk_reason": "No rule-specific auto-fix policy is configured.",
  "requires_review_after_fix": true,
  "fix_pattern": {
    "fix": "Add or reconcile forward declaration to match definition.",
    "example": "extern uint8_t foo(void); /* fix: misra-c2012-8.4 — reconciled declaration */",
    "pitfalls": "Mismatch between declaration and definition can indicate link-time errors or subtle type differences.",
    "context_notes": "Verify that declaration, definition, and all call sites agree on return type and parameter types."
  }
}
```

如果 rule_id 在 fix_patterns.json 中无条目，`fix_pattern` 为 `null`。

### Chunk 级别新增 `unique_fix_patterns` 字段

去重后的 pattern 集合，按 `rule_id` 索引，每条 pattern 在 chunk 内只出现一次：

```json
{
  "chunk_index": 1,
  "chunk_total": 2,
  "issue_count": 11,
  "files": ["cppcheck_error.c", "..."],
  "fix_strategy": "all_auto",
  "contains_high_risk": true,
  "unique_fix_patterns": {
    "misra-c2012-8.4": {
      "fix": "Add or reconcile forward declaration to match definition.",
      "example": "extern uint8_t foo(void); /* fix: misra-c2012-8.4 — reconciled declaration */",
      "pitfalls": "...",
      "context_notes": "..."
    },
    "misra-c2012-11.3": {
      "fix": "Add explicit cast from void/object pointer to target pointer type.",
      "example": "uint8_t *p = (uint8_t *)void_ptr; /* fix: misra-c2012-11.3 — explicit cast */",
      "caution": "Verify target type alignment."
    }
  },
  "issues": [ ... ]
}
```

典型 chunk 有 3~8 个 unique rule_id，注入量约 **100~400 token**。

## Section 3：代码变更 — split_cppcheck_xml.py

### 变更点

1. **脚本启动时**：加载 `fix_patterns.json`（一次性读入，传给 `classify_issue()`）
2. **`classify_issue()` 扩展**：
   ```python
   RISK_DETAIL_FIELDS = {
       "low": ["fix", "example"],
       "medium": ["fix", "example", "caution"],
       "high": ["fix", "example", "pitfalls", "context_notes"],
   }

   def classify_issue(issue, rule_policy, fix_patterns):
       ...  # 现有 policy 查找逻辑
       
       rule_id = issue.get("rule_id", "")
       pattern_data = fix_patterns.get("patterns", {}).get(rule_id)
       if pattern_data:
           detail_fields = RISK_DETAIL_FIELDS.get(
               pattern_data.get("risk_level", "high"),
               RISK_DETAIL_FIELDS["high"]
           )
           issue["fix_pattern"] = {k: pattern_data[k] for k in detail_fields if k in pattern_data}
       else:
           issue["fix_pattern"] = None
   ```
3. **Chunk 组装后**：计算 `unique_fix_patterns`
   ```python
   seen = {}
   for issue in chunk["issues"]:
       rid = issue["rule_id"]
       fp = issue.get("fix_pattern")
       if fp and rid not in seen:
           seen[rid] = fp
   chunk["unique_fix_patterns"] = seen
   ```

### 改动范围

- `split_cppcheck_xml.py`：修改 `classify_issue()` 签名和逻辑 + 新增 chunk 去重逻辑
- `common.py`：可选增加 `FIX_PATTERNS_PATH` 常量或加载辅助函数
- **不改** `base.py` / `build_chunk_prompt()`

## Section 4：Prompt 模板 + SKILL.md

### fix_chunk_prompt.txt

仅在 `{strategy_instructions}` 后新增一行：

```
For each issue, follow the fix pattern specified in the chunk JSON's "unique_fix_patterns" field for that rule_id. If a pattern exists, use the exact approach described; if not, apply the general minimal-edit principle from the skill.
```

### SKILL.md

**不变**。通用原则已在 SKILL.md 中，具体 pattern 不应膨胀到 SKILL.md。

### base.py / build_chunk_prompt()

**不变**。fix_pattern 已经预写入 chunk JSON，LLM 自行读取。