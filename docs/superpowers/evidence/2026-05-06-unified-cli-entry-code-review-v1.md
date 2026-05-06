Let me read the implementation files.






Now let me read the remaining key parts of the CLI file — the dispatch functions and [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:951:0-971:12):

Now let me verify the old files were removed:

Good, both [pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:0:0-0:0) and [test_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:0:0-0:0) are deleted. Let me do a final check on import ordering and the `REMAINDER` behavior:


# 实施代码审核报告

## 一、与计划对照检查

### 已实现项

| 计划要求 | 实现状态 | 验证行号 |
|----------|----------|----------|
| `import importlib` / `import inspect` | ✅ | CLI 第31-32行 |
| 更新 docstring | ✅ | CLI 第2-19行 |
| `doctor` → `env-check` 改名 | ✅ | CLI 第170-171, 827, 962-963行 |
| `PIPELINE_COMMANDS` 映射 | ✅ | CLI 第54-64行 |
| [_call_module_main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:851:0-862:51) 签名适配 | ✅ | CLI 第852-863行 |
| [_dispatch_pipeline_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:865:0-912:59) 含 provider | ✅ | CLI 第866-913行 |
| [_dispatch_policy_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:915:0-946:32) REMAINDER 转发 | ✅ | CLI 第916-947行 |
| pipeline 命令 parse_args + `--provider` | ✅ | CLI 第183-202行 |
| policy parser + epilog | ✅ | CLI 第204-220行 |
| [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:951:0-971:12) 分发逻辑 | ✅ | CLI 第952-972行 |
| 删除 [pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:0:0-0:0) | ✅ | 已确认不存在 |
| 删除 [test_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:0:0-0:0) | ✅ | 已确认不存在 |
| 测试: parse_args 新命令 | ✅ | 测试第100-162行 |
| 测试: dispatch 签名适配 | ✅ | 测试第529-555行 |
| 测试: dispatch missing tools | ✅ | 测试第557-563行 |
| 测试: provider 环境变量 | ✅ | 测试第565-608行 |
| 测试: provider stale env 清理 | ✅ | 测试第164-198行 |
| 测试: invalid subcommand rejection | ✅ | 测试第159-162行 |
| 测试: env-check 更名 | ✅ | 测试第55-58, 380行 |

---

## 二、发现的问题

### 🔴 P0: `argparse.REMAINDER` 捕获的 `--` 被原样转发给目标模块

测试从计划的写法做了改动 — 加入了 `--` 分隔符：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:100-104
    def test_parse_args_split_subcommand(self):
        """Test parse_args for 'split' subcommand."""
        args = misra_pipeline_cli.parse_args(["split", "--", "--input", "cppcheck.xml"])
        self.assertEqual(args.subcommand, "split")
        self.assertEqual(args.args, ["--", "--input", "cppcheck.xml"])
```

**计划原本写的是**（不带 `--`）：
```python
args = misra_pipeline_cli.parse_args(["split", "--input", "cppcheck.xml"])
self.assertEqual(args.args, ["--input", "cppcheck.xml"])
```

实现者改为使用 `--` 说明不带 `--` 时 argparse 报错（因为 `--provider` 选项在同一个子 parser 中，argparse 尝试将 `--input` 匹配为选项后失败）。这本身是合理的 workaround，但 **`--` 被包含在 `args.args` 中并原样转发给目标模块**。

转发链路：
1. [parse_args(["split", "--", "--input", "cppcheck.xml"])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:133:0-221:72) → `args.args = ["--", "--input", "cppcheck.xml"]`
2. [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:951:0-971:12) 调用 [_dispatch_pipeline_command("split", ["--", "--input", "cppcheck.xml"])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:865:0-912:59)
3. `sys.argv = ["split_cppcheck_xml.py", "--", "--input", "cppcheck.xml"]`
4. [module.main(["--", "--input", "cppcheck.xml"])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:951:0-971:12)

**后果**：目标模块的 argparse 将 `--` 视为选项终止符，`--input` 被当作**位置参数**而非命名选项 `--input`，导致目标模块参数解析失败。

**修复**：在 [_dispatch_pipeline_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:865:0-912:59) 和 [_dispatch_policy_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:915:0-946:32) 中，转发前去除前导 `--`：

```python
# Strip leading '--' argparse REMAINDER separator before forwarding
if args and args[0] == "--":
    args = args[1:]
```

添加位置：`@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:899` 之前（`original_argv = sys.argv` 之前），以及 `@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:939` 之前。

同时 [test_parse_args_run_subcommand](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_misra_pipeline_cli.py:105:4-109:56) 也有同样的问题：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:106-110
    def test_parse_args_run_subcommand(self):
        """Test parse_args for 'run' subcommand."""
        args = misra_pipeline_cli.parse_args(["run", "--", "--dry-run"])
        self.assertEqual(args.subcommand, "run")
        self.assertEqual(args.args, ["--", "--dry-run"])
```

### 🟡 P2: `import` 排序不符合 PEP 8

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:23-34
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import importlib
import inspect
import urllib.error
import urllib.request
```

`importlib` 和 `inspect` 应按字母序插入到 `hashlib` 之前/之后，而非追加在 `tempfile` 之后。应为：

```python
import argparse
import hashlib
import importlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
```

### 🟢 P3: dispatch 测试 `sys.argv` 断言与真实调用路径不一致

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\tests\test_misra_pipeline_cli.py:524
                    result = misra_pipeline_cli._dispatch_pipeline_command("split", ["--input", "test.xml"])
```

测试直接传 `["--input", "test.xml"]`（不带 `--`），但通过 [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:951:0-971:12) → [parse_args()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:133:0-221:72) → `args.args` 实际路径，args 会包含 `["--", "--input", "test.xml"]`。测试覆盖的不是真实的调用场景。修复 P0 后（添加 `--` 剥离逻辑），这个测试就会与真实路径一致。

---

## 三、总结

| 优先级 | 问题 | 影响 | 修复方式 |
|--------|------|------|----------|
| **P0** | `--` 被原样转发给目标模块 | 所有带 `--option` 参数的 pipeline 命令在实际使用中会解析失败 | 转发前 `args = args[1:]` 去除前导 `--` |
| **P2** | import 排序 | 风格问题 | 按字母序重排 |
| **P3** | dispatch 测试参数与真实路径不一致 | 测试未覆盖真实路径 | 修复 P0 后自然一致 |

**结论**：实现整体忠实于计划，代码结构和逻辑正确。**P0 的 `--` 转发问题**是必须修复的阻塞性 bug — 在 [_dispatch_pipeline_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:865:0-912:59) 和 [_dispatch_policy_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:915:0-946:32) 各加一行 `--` 剥离即可。
