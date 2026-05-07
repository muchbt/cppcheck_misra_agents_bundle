

# 实现计划审核：✅ 通过，附 3 条小建议

## 总评

计划清晰、步骤原子化、每步有验证命令和回归测试，commit 粒度合理。与 spec 完全对齐，无遗漏需求。

## 逐 Task 确认

| Task | 内容 | 评估 |
|------|------|------|
| 1 | `parse_chunk_id_specs` 函数 | ✅ 逻辑正确 |
| 2 | [next_chunk](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:190:0-203:15) 扩展 | ✅ 兼容旧签名 |
| 3 | [parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:137:0-275:17) 加参数 | ✅ |
| 4 | [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:225:0-441:42) 集成（6 步） | ✅ 覆盖全流程 |
| 5 | 单元/集成测试（13 个 case） | ✅ 覆盖面充分 |
| 6 | [oneshot.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:0:0-0:0) 转发 | ✅ |
| 7 | CLI 定义+转发+测试 | ✅ |
| 8 | 全量回归 | ✅ |

## ⚠️ 3 条待确认/建议

### 1. Failed chunk 提示会重复打印

[next_chunk](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:190:0-203:15) 在每次 while 循环被调用时重新遍历 `requested_ids`。若 chunk 5 failed、`requested_ids=[5, 7]`：
- 第一次调用：打印 hint for 5 → 返回 7
- 第二次调用（7 完成后）：**再次打印** hint for 5 → 返回 None

效果：用户看到同一条提示打两遍。

**建议**：在 [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:225:0-441:42) 预处理阶段一次性检查 `requested_ids ∩ failed_chunks`，打印提示后从 `requested_ids` 中剔除（或仅在 [next_chunk](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:190:0-203:15) 外部打印）。但这是 UX 细节，不阻塞实现。

### 2. 测试缺少 import 补充说明

Task 5 的测试代码使用了 `io`, `redirect_stdout`, `tempfile`, `Path`, `patch`，但计划未明确"在文件顶部确认已导入"。建议在 Step 1 开头加一句：

> 确认 `tests/test_run_pipeline.py` 顶部已有 `import io`, `from contextlib import redirect_stdout`, `import tempfile`, `from pathlib import Path`, `from unittest.mock import patch`；缺失则补上。

### 3. 负数输入的 warning 文案可更明确（可选）

`"-5"` 会触发 `"忽略无效 chunk-id 范围: '-5'"` —— 对用户可能困惑为何是"范围"。但由于 chunk ID 本身不可能为负数，这个边界极端罕见，不必改动。

## 结论

可直接按计划执行。如果想打磨体验，先处理建议 #1（重复 hint），但不阻塞功能交付。
