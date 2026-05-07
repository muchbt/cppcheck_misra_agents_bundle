
# Spec 审核：✅ 通过

文档完整覆盖了 outline + 两轮澄清的所有决策点，结构清晰，可直接作为实现基础。

## 逐节确认

| 节 | 评估 |
|---|------|
| §1 背景 | ✅ 目标明确 |
| §2 架构图 | ✅ |
| §3 涉及文件 | ✅ 仅新增，不改现有模块 |
| §4.1 export | ✅ host-id 三级解析、patch 降级、staging 校验、completed/failed 分治 |
| §4.2 collect | ✅ run_id 校验、冲突检测、[import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 复用、progress 合并 |
| §4.3 CLI 注册 | ✅ |
| §5 设计决策表 | ✅ 7 条决策均有理由 |
| §6 操作流程 | ✅ 端到端示例 |
| §7 边界行为 | ✅ 7 个边界场景 |
| §8 测试策略 | ✅ 6 类测试 |
| §9 兼容性 | ✅ |
| §10 风险 | ✅ |
| §11-12 附录 | ✅ 可执行伪代码 |

## 3 条小建议（不阻塞）

### 1. `collect` 的幂等性实现细节需确认

§7 说"重复导入同一 bundle 不会破坏状态"，但 [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 内部做的是 `issue_status.update(delta)`（`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:966`）。如果重复导入同一 chunk：

- 第一次导入：chunk 3 加入 `completed_chunks` → 状态正确
- 第二次导入同一 bundle：chunk 3 已在 `completed_chunks` → 冲突检测跳过 → **幂等成立** ✅

这确实是幂等的，因为冲突检测在 [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 之前拦截。逻辑正确，只是建议在 spec 中明确："幂等性由 §4.2 Step 3 冲突检测保证，重复 bundle 中 completed chunk 全部被跳过，不会重入 [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5)。"

### 2. `format_version` 校验缺实现

§7 提到"collect 侧可据此拒绝或走兼容路径"，但 §4.2 的 `import_one_bundle` 中没有校验 `format_version`。建议在 Step 2（run_id 校验之前）加一行：

```python
if manifest.get("format_version", 0) != 1:
    raise SystemExit(f"不支持的 bundle 格式版本: {manifest.get('format_version')}")
```

### 3. `try_generate_patch` 漏了 `timeout` 异常

`subprocess.run(..., timeout=30)` 会抛 `subprocess.TimeoutExpired`，当前只 catch 了 `FileNotFoundError`。建议：

```python
except (FileNotFoundError, subprocess.TimeoutExpired):
    return None, "git 不可用或超时，跳过 source patch"
```

## 结论

Spec 质量高，覆盖完整，3 条建议均为补强细节，不影响整体设计。可进入实现阶段。
