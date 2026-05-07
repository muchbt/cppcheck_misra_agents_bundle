

Let me verify the plan's assumptions about the current CLI structure.


Now let me check the `import_one_bundle` call signature to verify how [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) is called in tests vs actual code.

# Plan 审核：✅ 通过（附 2 条小修）

## 整体评估

计划结构清晰，严格遵循 TDD RED→GREEN 节奏，8 个 Task 按依赖序排列，每步有完整代码 + exact command + expected output。Self-Review 的 spec 覆盖表和 placeholder scan 都做了。

## 逐 Task 确认

| Task | 内容 | 评估 |
|------|------|------|
| 1 | `resolve_host_id` + `try_generate_patch` 工具函数 | ✅ |
| 2 | `build_manifest` + `create_bundle` | ✅ |
| 3 | [export_chunks.parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:99:0-161:34) + [main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1174:0-1201:12) | ✅ |
| 4 | `collect_chunks` 骨架 + `CollectResult` + `import_one_bundle` | ✅ |
| 5 | [collect_chunks.parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:99:0-161:34) + [main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1174:0-1201:12) + 冲突/幂等测试 | ✅ |
| 6 | CLI 注册 | ✅ |
| 7 | 端到端集成测试 | ✅ |
| 8 | 全量回归 | ✅ |

## 2 条需修正的问题

### 1. [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 调用方式不一致

`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:940-944` 签名为位置参数 `staging_dir, chunk_index`，但 Task 4 Step 4.3 中的实现（L701）和 Task 5 冲突测试（L800）使用了不同的调用风格：

- **实现（L701）**：[import_chunk_staging_artifacts(src_staging, idx, runtime_dir=..., results_dir=...)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) — 位置参数 ✅
- **测试断言（L800）**：`assert kwargs["chunk_index"] == 4` — 期望 keyword arg

问题：因为 `idx` 是作为**第二个位置参数**传入的，`mock_import.call_args` 中 `chunk_index` 会在 `args[1]` 而非 `kwargs["chunk_index"]`。

**修正**：测试断言应改为：

```python
args_pos, kwargs = mock_import.call_args
assert args_pos[1] == 4  # chunk_index is positional
```

同样，Task 7 集成测试 L1104-1105 也需修正：

```python
args_pos, kwargs = mock_import.call_args
assert args_pos[1] == 3
```

### 2. CLI docstring 修改描述与实际位置偏差

Task 6 Step 6.1 修改 1 说"在 `Deprecated:` 之前插入两行"，但给出的代码块是**替换整个 Advanced commands 段**（加了 `export` 和 `collect` 两行）。当前 docstring（`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:12-18`）的 Advanced commands 块不包含 `doctor`（doctor 在 Primary commands 里），但计划给出的替换代码块把 `doctor` 移到了 Advanced 里。

**建议**：保持 `doctor` 在 Primary commands 不动，只在 Advanced commands 段末尾追加 `export` 和 `collect`：

```
Advanced commands:
  split         Split cppcheck XML (use 'run --stage split')
  merge         Merge results (use 'run --stage merge')
  verify        Verify one chunk result
  bootstrap     Generate agent compatibility files
  validate      Provider validation test
  export        Export processed chunk results to a bundle
  collect       Import chunk results from remote workers
  config        Manage CLI configuration
```

## 结论

计划质量高，覆盖完整。**2 条修正**均为局部细节（mock 断言写法 + docstring 不改变已有分类），不影响整体架构和执行顺序。修正后可直接执行。
