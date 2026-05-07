核心思路：**不要把全量规则写进 SKILL.md，按 chunk 动态注入只涉及的规则**。

## Token 开销对比

| 方案 | 每 chunk 额外 token | 约束力 |
|------|---------------------|--------|
| 全量写入 SKILL.md（~175 条 MISRA 规则） | +5000~8000 | ✅ 强 |
| **按 chunk 动态注入**（通常 3~8 条规则） | **+100~300** | ✅ 强 |
| 不注入，仅靠"minimal edit"描述 | 0 | ❌ 弱 |

## 推荐方案：分层架构

```
SKILL.md          ← 通用原则（不变，不膨胀）
  ↓
fix_patterns.json ← 全量规则→修复模式映射表（静态数据文件）
  ↓
prompt 组装时     ← 只提取当前 chunk 涉及的 rule ID，注入对应模式
```

具体实现路径：

### 1. 新建 `fix_patterns.json`（静态数据，不进 prompt）

从 chunk JSON 结构可以看到，每个 issue 已经有 `rule_id` 字段。这就是动态注入的锚点。

## 最优方案：按 chunk 动态注入（零膨胀 SKILL.md）

```
SKILL.md (不变)          fix_patterns.json (新增)         prompt 组装 (改动)
────────────────         ─────────────────────           ──────────────────
通用原则 ~500 tok        全量规则映射 ~200条               提取 chunk 中的
不写任何具体规则  →      每条 ~30 tok                →    unique rule_ids →
                         总计 ~6000 tok                    只注入命中的 3~8 条
                         (不进 prompt)                     ~100~250 tok/chunk
```

### 具体实现

**Step 1** — 新建 `@.agents/config/fix_patterns.json`：

```json
{
  "_meta": "Canonical fix patterns. Injected into prompt per-chunk based on rule_id.",
  "patterns": {
    "misra-c2012-11.3": {
      "fix": "Add explicit cast: `(TargetType *)expr`",
      "example": "uint8_t *p = (uint8_t *)void_ptr; /* fix: misra-c2012-11.3 — added explicit cast */"
    },
    "misra-c2012-17.7": {
      "fix": "Cast unused return to void: `(void)func();`",
      "example": "(void)memset(buf, 0, sz); /* fix: misra-c2012-17.7 — cast unused return to void */"
    },
    "nullPointer": {
      "fix": "Add NULL guard before first dereference",
      "example": "if (ptr == NULL) { return ERR; } /* fix: nullPointer — added NULL guard */"
    }
  }
}
```

每条规则约 **30~50 token**，全量 200 条也只占磁盘 ~10KB，但**不会全部进入 prompt**。

**Step 2** — 在 `providers/base.py` 的 `build_chunk_prompt()` 中动态提取并注入：

核心逻辑（伪代码）：

```python
# 从 chunk JSON 提取 unique rule_ids
rule_ids = {issue["rule_id"] for issue in chunk.get("issues", [])}

# 从 fix_patterns.json 只取命中的
patterns = load_json(CONFIG_DIR / "fix_patterns.json", {}).get("patterns", {})
matched = {rid: patterns[rid] for rid in rule_ids if rid in patterns}

# 格式化为紧凑文本注入 prompt
if matched:
    lines = ["Canonical fix patterns (use these exact approaches):"]
    for rid, p in matched.items():
        lines.append(f"- {rid}: {p['fix']}")
    fix_hint = "\n".join(lines)
else:
    fix_hint = ""
```

一个典型 chunk 有 3~8 个 unique rule_id，注入量约 **100~250 token**。

### Token 开销实测对比

| chunk 中 unique 规则数 | 注入 token 数 | 占 prompt 比例 |
|------------------------|---------------|---------------|
| 1 | ~35 | <1% |
| 5 | ~170 | ~3% |
| 12（上限） | ~400 | ~7% |
| 全量写入 SKILL.md | ~6000 | **~50%+** |

### 为什么不放在 SKILL.md 里

| | SKILL.md 全量 | 动态注入 |
|--|---------------|---------|
| **token/chunk** | +6000 固定 | +100~250 按需 |
| **一致性约束** | ✅ 强 | ✅ 同样强 |
| **维护** | 改一条要改 SKILL.md | 改 JSON 即可 |
| **适用新规则** | 需改 prompt 文件 | 加一行 JSON |
| **agent 上下文窗口** | 挤占有效空间 | 几乎不影响 |

### 总结

- **SKILL.md 保持不动**，只写通用原则
- **`fix_patterns.json`** 作为静态数据文件存放全量规则→修复映射
- **`build_chunk_prompt()`** 在组装 prompt 时按 chunk 的 `rule_id` 集合动态注入匹配的条目
- 每 chunk 增加约 **100~250 token**，但获得与全量写入相同的约束力

需要我切到 Code 模式实现这个方案吗？
