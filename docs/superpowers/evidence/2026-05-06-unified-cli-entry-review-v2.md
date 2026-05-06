# 二次审核报告：统一 CLI 入口方案与计划 (v2)

## 一、上轮问题修复验证

| # | 原问题 | 修复状态 | 备注 |
|---|--------|----------|------|
| P0 | [main(args)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:43:0-68:59) 签名不匹配，3模块 TypeError | ✅ 已修复 | 新增 `_call_module_main` + `inspect.signature` 适配 |
| P0 | `--provider` 功能静默丢失 | ✅ 已修复 | 新增 §6，`_dispatch_pipeline_command` 增加 `provider` 参数 |
| P1 | 缺少 `import importlib` | ✅ 已修复 | Task 1 Step 1 明确添加 `import importlib` 和 `import inspect` |
| P1 | policy args→argv 回转脆弱 | ✅ 已修复 | 改为 REMAINDER 转发，消除双重解析 |
| P1 | 旧测试未实质迁移 | ✅ 已修复 | Task 3 Step 3 明确列出迁移的测试 |
| P2 | `sys.path` 不恢复 | ✅ 已修复 | 代码注释明确"有意为之"，风险表同步更新 |
| P2 | docstring / help text 未更新 | ✅ 已修复 | Task 1 Step 2 更新 docstring，Task 2 Step 3 添加 validate help 注明原名 |

**所有上轮问题均已解决。**

---

## 二、本轮新发现

### 🟡 中等问题

#### 1. `_dispatch_pipeline_command` 中 `provider` 参数未通过 `tools_dir` mock 路径

`@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-05-06-unified-cli-entry-plan.md:468-487` 中 `test_dispatch_provider_sets_env` 直接调用 `_dispatch_pipeline_command("run", [], provider="claude")`，但没有 mock `Path.cwd()` 或创建临时 `.agents/tools/` 目录。函数开头会检查 `tools_dir.exists()`，在测试环境下如果 CWD 恰好不含 `.agents/tools/`，测试会在 provider 逻辑执行前就返回 1。

对比同文件第 499-503 行的 `test_dispatch_provider_restores_env`，那里正确地创建了临时目录并 mock 了 `Path.cwd`。

**建议**：`test_dispatch_provider_sets_env` 也需要 mock `Path.cwd` 或创建临时 `.agents/tools/`。

#### 2. `test_dispatch_provider_restores_env` 中 mock 层级可能失效

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-05-06-unified-cli-entry-plan.md:502
                    with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
```

`Path.cwd()` 是一个 classmethod。`patch.object(misra_pipeline_cli.Path, "cwd", ...)` 会 patch 全局 `Path.cwd`（因为 `misra_pipeline_cli.Path` 就是 `pathlib.Path`）。这在功能上可行，但 patch 的是全局 `Path` 类，可能影响同进程中其他 Path.cwd 调用。更稳健的做法是 patch `misra_pipeline_cli` 模块内的 `Path` 引用本身，或者直接用 `os.chdir(tmp)` + fixture 恢复。

**影响**：测试可能偶发失败或产生副作用，但不是阻塞性问题。

#### 3. `test_dispatch_provider_clears_stale_env` 断言逻辑

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-05-06-unified-cli-entry-plan.md:554
            self.assertIsNone(seen_second.get("provider"))
```

这里用 `seen_second.get("provider")` 检查 `None`，但实际上 `_dispatch_pipeline_command` 在无 provider 时执行 `os.environ.pop("PIPELINE_AGENT_PROVIDER", None)`，所以 `os.environ.get(...)` 返回 `None`，`seen_second["provider"]` 的值确实是 `None`。使用 `.get("provider")` 而非 `["provider"]` 意味着如果 [FakeModuleSecond.main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:43:0-68:59) 根本没被调用（比如 import 失败），测试也会 pass 而不会报错。建议改为 `self.assertIsNone(seen_second["provider"])` 以严格验证回调确实执行了。

### 🟢 小问题

#### 4. `test_dispatch_missing_tools_dir` 的 MagicMock 链式调用较复杂

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-05-06-unified-cli-entry-plan.md:459-466
        with patch.object(misra_pipeline_cli, "Path") as mock_path:
            mock_cwd = MagicMock()
            mock_cwd.__truediv__ = MagicMock(return_value=MagicMock())
            mock_cwd.__truediv__.return_value.exists.return_value = False
            mock_path.cwd.return_value = mock_cwd
            result = misra_pipeline_cli._dispatch_pipeline_command("split", [])
```

`Path.cwd() / ".agents" / "tools"` 涉及两次 `__truediv__`，但这里只 mock 了一层。第一次 `/` 返回 mock 对象，第二次 `/` 也需要返回一个 `.exists()` 为 `False` 的 mock。由于 MagicMock 的默认行为，第二次 `__truediv__` 会返回另一个 MagicMock，其 `.exists()` 默认返回 MagicMock（truthy），测试可能不会按预期工作。

**建议**：改用 `tempfile.TemporaryDirectory` + 不创建 `.agents/tools/`，或用 `os.chdir` 到空目录，比链式 MagicMock 更可靠。

#### 5. Step 3 缺少 `import tempfile` 和 `from unittest.mock import MagicMock`

计划第510行提到"需要在文件顶部确保 `import os` 和 `from unittest.mock import MagicMock, patch` 已导入"。但没有提到 `import tempfile`，而 `test_dispatch_provider_restores_env` 和 `test_dispatch_provider_clears_stale_env` 都使用了 `tempfile.TemporaryDirectory`。

检查现有测试文件：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:300-301
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
```

现有代码在函数内部局部 import `tempfile`，但新测试在函数体内直接使用 `tempfile.TemporaryDirectory` 而没有局部 import。应统一为顶部 import 或保持局部 import 风格。

#### 6. policy `--help` 体验降级

设计方案 §5.2 最终选择了纯 REMAINDER 转发，这意味着 `misra-pipeline policy --help` 只显示 `"Manage policy configuration (use 'policy -- --help' for subcommands)"`，不再展示 init/list/test/add 的参数结构。相比旧方案的完整子命令帮助，用户体验有所下降。

这是设计取舍而非 bug，但建议在 `policy_parser` 上添加 `epilog` 展示常用用法示例：

```python
policy_parser = subparsers.add_parser(
    "policy",
    help="Manage policy configuration",
    epilog="Examples:\n  misra-pipeline policy init --template misra_c2012_relaxed\n  misra-pipeline policy list\n  misra-pipeline policy test --rule-id R1.1 --file test.c",
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
```

---

## 三、总结

| 优先级 | 问题 | 建议 |
|---|---|---|
| **P1** | `test_dispatch_provider_sets_env` 缺少 tools_dir mock，测试会误报失败 | 补齐临时目录或 mock |
| **P2** | `test_dispatch_missing_tools_dir` 链式 MagicMock 可能不生效 | 改用临时空目录 |
| **P2** | `seen_second.get("provider")` 应改为 `seen_second["provider"]` | 严格验证回调执行 |
| **P2** | 缺少 `import tempfile` / `MagicMock` 的顶部 import 说明 | 补齐 import 步骤 |
| **P3** | policy `--help` 体验降级 | 可选添加 epilog 示例 |

**结论**：所有上轮 P0/P1 问题已修复，方案和计划整体可执行。本轮发现的问题集中在**测试 mock 不完整**（P1×1, P2×3），不影响生产代码正确性，但会导致部分测试在 CI 中失败。建议修复 P1 后即可启动实施。
