


Now let me check the CLI changes:

Now let me check the CLI test additions:

# 代码审核：✅ 通过

实现完全匹配 spec 和 plan。所有文件结构正确、逻辑与设计文档一致。

## 文件清单确认

| 文件 | 状态 | 与 plan 一致性 |
|------|------|----------------|
| [.agents/tools/export_chunks.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/export_chunks.py:0:0-0:0) (192 行) | ✅ 新建 | 完全一致 |
| [.agents/tools/collect_chunks.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/collect_chunks.py:0:0-0:0) (139 行) | ✅ 新建 | 完全一致 |
| [cli/misra-pipeline-cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:0:0-0:0) docstring L18-19 | ✅ 修改 | `export`/`collect` 已加入 Advanced |
| [cli/misra-pipeline-cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:0:0-0:0) PIPELINE_COMMANDS L70-71 | ✅ 修改 | 已注册 |
| [cli/misra-pipeline-cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:0:0-0:0) cmd_help L223-224 | ✅ 修改 | 已注册 |
| [tests/test_export_chunks.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_export_chunks.py:0:0-0:0) (164 行) | ✅ 新建 | 8 个测试 |
| [tests/test_collect_chunks.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_collect_chunks.py:0:0-0:0) (188 行) | ✅ 新建 | 6 个测试 |
| [tests/test_export_collect_integration.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_export_collect_integration.py:0:0-0:0) (82 行) | ✅ 新建 | 1 个端到端测试 |
| [tests/test_misra_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:0:0-0:0) L229-245 | ✅ 修改 | 3 个 CLI 测试 |

## 逻辑正确性确认

- **[resolve_host_id](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/export_chunks.py:23:0-29:5)**：三级优先级 `--host-id` > `PIPELINE_HOST_ID` > `socket.gethostname()` ✅
- **[try_generate_patch](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/export_chunks.py:32:0-48:100)**：捕获 `FileNotFoundError` + `TimeoutExpired` ✅
- **[build_manifest](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/export_chunks.py:51:0-71:5)**：`format_version: 1`，`source_patch_file` 条件设置 ✅
- **[create_bundle](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/export_chunks.py:90:0-111:65)**：staging 只打包 completed，logs 打包 all_ids ✅
- **`export main`**：[resolve_agent_staging_dir(config, root=ROOT)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:57:0-61:58) 传了 `root` 参数 ✅
- **[import_one_bundle](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/collect_chunks.py:30:0-96:5)**：format_version 校验 → run_id 校验 → 冲突检测 → patch apply → staging import → progress 更新 → logs 复制，顺序正确 ✅
- **`collect main`**：汇总输出 `done >= total and total > 0` 条件防除零 ✅
- **mock 断言**：`args_pos[1]` 检查位置参数 ✅（两处均正确）
- **CLI 转发**：`export`/`collect` 通过 `PIPELINE_COMMANDS` + `parse_known_args` → `args.args` 转发，无需额外 argparse 注册 ✅

## 无遗留问题

实现代码可运行测试验证。建议执行：

```bash
python3 -m pytest tests/test_export_chunks.py tests/test_collect_chunks.py tests/test_export_collect_integration.py tests/test_misra_pipeline_cli.py -v
```
