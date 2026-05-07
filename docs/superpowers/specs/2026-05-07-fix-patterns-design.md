# Fix Patterns 设计文档

> 日期：2026-05-07
> 状态：已审核修订 v2

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
    ↓ split_cppcheck_xml.py parse_xml() 阶段 lookup_fix_pattern() 查找
chunk JSON                 ← chunk 级 unique_fix_patterns 去重锚点（issue 级不存 fix_pattern）
    ↓ LLM 读取 chunk JSON 时自然获取
SKILL.md (不变)            ← 通用原则（不膨胀）
```

### 降级/容错

如果 `fix_patterns.json` 不存在或 `patterns` 为空，split 正常运行，`unique_fix_patterns` 为空对象 `{}`。LLM 回退到 SKILL.md 通用原则，不影响现有流程。

## Section 1：数据层 — fix_patterns.json

**位置**：`.agents/config/fix_patterns.json`

### Schema

```json
{
  "_meta": "Canonical fix patterns for cppcheck/MISRA rules. Injected into chunk JSON per-rule. risk_level comes from rule_policy, not from this file.",
  "risk_detail_levels": {
    "low": ["fix", "example"],
    "medium": ["fix", "example", "caution"],
    "high": ["fix", "example", "pitfalls", "context_notes"]
  },
  "patterns": {
    "<rule_id>": {
      "fix": "简要修复描述",
      "example": "代码示例 /* fix: rule_id — 修复说明 */",
      "caution": "中等风险注意事项（仅 medium+）",
      "pitfalls": "高风险常见陷阱（仅 high）",
      "context_notes": "高风险上下文提示（仅 high）"
    }
  }
}
```

**重要**：`fix_patterns.json` 中不存 `risk_level`。分级裁剪时使用 `classify_issue()` 返回的 `risk_level`（来自 rule_policy）作为唯一来源。pattern 与 policy 解耦：policy 管"能不能做 + 风险等级"，pattern 管"怎么做"。

### 分级详细度

risk_level 来自 rule_policy（`classify_issue()` 返回值），用于决定输出哪些字段：

| risk_level (from policy) | 包含字段 | 预估 token/条 |
|---|---|---|
| low | `fix` + `example` | ~30-50 |
| medium | `fix` + `example` + `caution` | ~60-80 |
| high | `fix` + `example` + `pitfalls` + `context_notes` | ~100-120 |

### 覆盖范围

- 所有去重后的 rule_id（跨 `misra_c2012_conservative.json`、`misra_c2012_relaxed.json`、`cppcheck_common.json`、`autosar_baseline.json`、`rule_policy.json`）
- risk_level 单一来源：由 `classify_issue()` 从 rule_policy 决定，不在 `fix_patterns.json` 中存储
- pattern 与 policy 解耦：policy 管"能不能做 + 风险等级"，pattern 管"怎么做"
- 对于 fix_patterns.json 中没有条目的 rule_id，LLM 回退到 SKILL.md 通用原则

### 示例

```json
{
  "unusedVariable": {
    "fix": "Remove the unused variable declaration.",
    "example": "/* fix: unusedVariable — removed unused variable 'x' */"
  },
  "misra-c2012-8.13": {
    "fix": "Add const qualifier to pointer parameter where the pointed-to data is not modified.",
    "example": "void foo(uint8_t * const p); /* fix: misra-c2012-8.13 — added const qualifier */",
    "caution": "Verify that the function implementation does not modify the data through this pointer."
  },
  "misra-c2012-17.7": {
    "fix": "Cast unused return value to void, or capture and check the return value.",
    "example": "(void)memset(buf, 0, sz); /* fix: misra-c2012-17.7 — discard unused return */",
    "pitfalls": "Silently discarding return values may hide errors. If the function can fail, prefer capturing and checking the return value.",
    "context_notes": "In safety-critical code, consider using the return value for error path handling rather than (void) cast."
  }
}
```

## Section 2：Chunk JSON 变更

### 设计决策：只保留 chunk 级 `unique_fix_patterns`

issue 级不存 `fix_pattern` 字段。LLM 通过 issue 的 `rule_id` 查阅 chunk 顶层的 `unique_fix_patterns`。

**理由**：避免冗余。典型 chunk 含 12 个 issue、3 个 unique rule_id。如果 issue 级也存 `fix_pattern`，同一 pattern 出现 3+12=15 次 vs 3 次。

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
  "issues": [
    {
      "issue_key": "cppcheck_error.c:3:misra-c2012-8.4:4a2c80d8",
      "file": "cppcheck_error.c",
      "line": 3,
      "rule_id": "misra-c2012-8.4",
      ...
    }
  ]
}
```

典型 chunk 有 3~8 个 unique rule_id，注入量约 **100~400 token**。

如果 rule_id 在 `fix_patterns.json` 中无条目，该 rule_id 不出现在 `unique_fix_patterns` 中（LLM 回退到 SKILL.md 通用原则）。

## Section 3：代码变更 — split_cppcheck_xml.py

### 变更点

1. **脚本启动时**：加载 `fix_patterns.json`（一次性读入）
2. **新增独立函数 `lookup_fix_pattern()`**：不修改 `classify_issue()` 签名，pattern 查找作为独立步骤
   ```python
   RISK_DETAIL_FIELDS = {
       "low": ["fix", "example"],
       "medium": ["fix", "example", "caution"],
       "high": ["fix", "example", "pitfalls", "context_notes"],
   }

   def lookup_fix_pattern(rule_id: str, risk_level: str, fix_patterns: Dict) -> Optional[Dict]:
       pattern = fix_patterns.get("patterns", {}).get(rule_id)
       if not pattern:
           return None
       fields = RISK_DETAIL_FIELDS.get(risk_level, RISK_DETAIL_FIELDS["high"])
       return {k: pattern[k] for k in fields if k in pattern}
   ```
3. **在 `parse_xml()` 中 `classify_issue()` 返回后附加 pattern 查找**：
   ```python
   # 现有逻辑
   issue_policy = classify_issue(rule_id, msg, policy, strategy, strategy_config)
   
   # 新增：fix_pattern 查找（独立于 classify_issue）
   fix_pattern = lookup_fix_pattern(rule_id, issue_policy.get("risk_level", "high"), fix_patterns)
   
   dedup[key] = {
       ...,
       **issue_policy,
       # fix_pattern 暂存在 issue 对象，chunk 组装时提取到 unique_fix_patterns 后删除
       "_fix_pattern": fix_pattern,
   }
   ```
4. **Chunk 组装后计算 `unique_fix_patterns`，然后从 issue 对象中删除临时字段**：
   ```python
   seen = {}
   for issue in chunk["issues"]:
       rid = issue["rule_id"]
       fp = issue.pop("_fix_pattern", None)
       if fp and rid not in seen:
           seen[rid] = fp
   chunk["unique_fix_patterns"] = seen
   ```

### 改动范围

- `split_cppcheck_xml.py`：新增 `lookup_fix_pattern()` 函数 + `parse_xml()` 中附加查找 + chunk 组装后去重
- `common.py`：可选增加 `FIX_PATTERNS_PATH` 常量或加载辅助函数
- **不改** `classify_issue()` 签名
- **不改** `base.py` / `build_chunk_prompt()`

### 降级/容错

- 如果 `fix_patterns.json` 不存在或 `patterns` 为空，`lookup_fix_pattern()` 返回 `None`
- `parse_xml()` 中 `fix_patterns` 参数默认为 `None`，此时跳过 pattern 查找
- 所有 issue 无 `_fix_pattern`，`unique_fix_patterns` 为空对象 `{}`
- 不影响现有 `classify_issue()` 和 chunk 生成逻辑

## Section 4：Prompt 模板 + SKILL.md

### fix_chunk_prompt.txt

仅在 `{strategy_instructions}` 后新增一行：

```
For each issue whose rule_id appears in unique_fix_patterns, you MUST use the exact fix approach described there. Do NOT invent alternative fix methods when a pattern is provided.
```

### SKILL.md

**不变**。通用原则已在 SKILL.md 中，具体 pattern 不应膨胀到 SKILL.md。

### base.py / build_chunk_prompt()

**不变**。fix_pattern 已经预写入 chunk JSON，LLM 自行读取。

## Section 5：测试规划

改动涉及 `split_cppcheck_xml.py` 核心路径，应补充以下测试用例：

| 测试用例 | 验证点 |
|---|---|
| `test_lookup_fix_pattern_low_risk` | low risk_level 只输出 `fix` + `example` |
| `test_lookup_fix_pattern_high_risk_includes_pitfalls` | high risk_level 输出 `fix` + `example` + `pitfalls` + `context_notes` |
| `test_lookup_fix_pattern_missing_returns_none` | rule_id 在 `fix_patterns.json` 中无条目时返回 `None` |
| `test_chunk_unique_fix_patterns_dedup` | chunk 中同 rule_id 多条 issue 时 `unique_fix_patterns` 只出现一次 |
| `test_split_without_fix_patterns_file_graceful_fallback` | `fix_patterns.json` 不存在时，`unique_fix_patterns` 为空对象，现有流程不受影响 |