Let me read all the modified files identified in the plan.




Now let me check the policy_init.py for the interactive template selection:





All files reviewed. Here's my assessment:

# 代码审核报告

## 计划一致性对照

| 计划要求 | 实现 | 状态 |
|----------|------|------|
| Task 1 Step 1: deprecated 注释 | `@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:3` | ✅ |
| Task 1 Step 2: `--verbose` 加入 parse_args + build_run_args | 第44行、第202-203行 | ✅ |
| Task 1 Step 3: 修复4处旧引用 + `[oneshot]`→`[run]` | 第99,112,169,227,261,262,273,284,292,304,312,327,354,380,394,404行 | ✅ |
| Task 2 Step 1: PIPELINE_COMMANDS 移除 run/oneshot | 第61-68行 | ✅ |
| Task 2 Step 2: run/status/oneshot 子命令定义 | 第240-266行 | ✅ |
| Task 2 Step 3: parse_known_args 逻辑 | 第268-276行，无变动（正确） | ✅ |
| Task 2 Step 4: 文件头 docstring | 第2-24行 | ✅ |
| Task 3 Step 1: [_import_oneshot_helpers](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1022:0-1034:45) + [cmd_run](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1037:0-1159:59) + [cmd_status](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1162:0-1165:41) | 第1023-1166行 | ✅ |
| Task 3 Step 2: main() 分发逻辑 | 第1168-1195行 | ✅ |
| Task 4: 测试更新 | 第106-134行（parse tests）、第657-701行（MisraPipelineRunTests） | ✅ |
| Task 5: policy init 交互式 | `@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\policy_init.py:436-462` | ✅ |
| Help 分层格式 | 第140-165行 `RawDescriptionHelpFormatter` + 分层描述 | ✅ |
| cmd_run 逻辑顺序：校验→stage→import→status→全流程 | 第1041→1046→1117→1120→1124 | ✅ |

**全部 Task 1-5 的计划要求均已正确实现。**

---

## 代码质量问题

### 🟡 P2: docstring 位置不规范

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:1-3
from __future__ import annotations

"""DEPRECATED: Use 'misra-pipeline run' instead. This module is kept for backward compatibility."""
```

Python 模块 docstring 必须在文件最开头（`from __future__` 之前）才能被 `__doc__` 属性捕获。当前放在 `from __future__` 之后，它变成了一个孤立字符串表达式，不是模块 docstring。

**修复**：调换顺序，docstring 放第一行，`from __future__` 放其后：
```python
"""DEPRECATED: Use 'misra-pipeline run' instead. This module is kept for backward compatibility."""
from __future__ import annotations
```

### 🟡 P2: [cmd_status](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1162:0-1165:41) 和 [main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1167:0-1194:12) 之间缺少空行

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:1163-1168
def cmd_status(args: argparse.Namespace) -> int:
    """Show current pipeline run progress."""
    oneshot = _import_oneshot_helpers()
    return oneshot.print_status_summary()

def main(argv: Optional[list[str]] = None) -> int:
```

PEP 8 要求顶级函数之间有两个空行，这里只有一个。

### 🟡 P2: docstring 中 `merge` 缩进不一致

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:14
  merge         Merge results (use 'run --stage merge')
```

对比第13行 `split` 用了两个空格缩进，`merge` 多了一个空格（3 个空格缩进），导致对齐不一致。

### 🟡 P2: [test_cmd_status](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:678:4-694:43) 测试中 stub oneshot.py 缺少 doctor import

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:684-686
            (tools_dir / "oneshot.py").write_text(
                "def print_status_summary(*a, **kw):\n    return 0\n"
                "def main(*a, **kw):\n    return 0\n"
            )
```

这个 stub 仅在 `sys.modules` 中没有缓存 `oneshot` 时生效。如果实际 oneshot.py 已被其他测试加载到 `sys.modules`，`importlib.import_module("oneshot")` 会返回缓存版本而不是 stub。建议在测试 tearDown 中清理 `sys.modules`：

```python
def setUp(self):
    self._cached_modules = {k: sys.modules[k] for k in list(sys.modules) if k in ('oneshot', 'common', 'doctor')}
    for k in self._cached_modules:
        sys.modules.pop(k, None)

def tearDown(self):
    for k in ('oneshot', 'common', 'doctor'):
        sys.modules.pop(k, None)
    sys.modules.update(self._cached_modules)
```

这不会导致当前测试失败（stub 文件没被真正 import），但如果测试顺序变化或并行运行可能出问题。

### 🟢 P3: oneshot.py 内部事件日志仍用 `"stage": "oneshot"` 和 `event: "oneshot_*"`

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:319-325
        append_pipeline_event(
            RUNTIME_DIR,
            event="oneshot_precheck_failed",
            stage="oneshot",
            level="error",
            message="oneshot 预检查失败。",
            data={"mode": mode, "blockers": [item.get("code", "") for item in blockers]},
        )
```

用户可见的 print 已改为 `[run]`，但内部事件日志（`event="oneshot_*"`、`stage="oneshot"`、`message="oneshot ..."` ）仍用旧名。这些日志写入 `pipeline_events.json`，不影响用户体验但语义不一致。可后续批量更新，不阻塞。

### 🟢 P3: [test_parse_args_oneshot_subcommand](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:160:4-163:52) 与 [test_parse_args_oneshot_deprecated](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:129:4-132:52) 重复

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:130-134
    def test_parse_args_oneshot_deprecated(self):
        """Test parse_args for deprecated 'oneshot' subcommand."""
        args = misra_pipeline_cli.parse_args(["oneshot"])
        self.assertEqual(args.subcommand, "oneshot")
```

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:161-164
    def test_parse_args_oneshot_subcommand(self):
        """Test parse_args for 'oneshot' subcommand."""
        args = misra_pipeline_cli.parse_args(["oneshot"])
        self.assertEqual(args.subcommand, "oneshot")
```

两个测试完全相同。建议删除 [test_parse_args_oneshot_subcommand](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:160:4-163:52)（旧测试），保留 [test_parse_args_oneshot_deprecated](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:129:4-132:52)（新测试，名称更准确）。

---

## 总结

| 优先级 | 问题 | 位置 |
|--------|------|------|
| **P2** | docstring 在 `from __future__` 之后，非真正模块 docstring | `oneshot.py:1-3` |
| **P2** | [cmd_status](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1162:0-1165:41) 和 [main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:1167:0-1194:12) 之间缺一个空行 | `misra-pipeline-cli.py:1166-1168` |
| **P2** | docstring 中 `merge` 多一个空格 | `misra-pipeline-cli.py:14` |
| **P2** | 测试中 `sys.modules` 缓存可能导致 stub 不生效 | `test_misra_pipeline_cli.py:679-695` |
| **P3** | 内部事件日志仍用 `oneshot_*` 名称 | [oneshot.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:0:0-0:0) 多处 |
| **P3** | 重复测试 [test_parse_args_oneshot_subcommand](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:160:4-163:52) | `test_misra_pipeline_cli.py:161-164` |

**代码与计划完全一致，无功能性问题。** 上述均为代码质量/风格问题，P2 建议修复，P3 可后续处理。
