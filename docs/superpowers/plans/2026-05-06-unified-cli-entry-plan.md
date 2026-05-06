# misra-pipeline 统一 CLI 入口实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `cli/misra-pipeline-cli.py` 打造为唯一 CLI 入口，废弃 `.agents/tools/pipeline_cli.py`，doctor 改名为 env-check，新增 split/run/merge/verify/bootstrap/doctor/validate/oneshot/policy 命令，迁移 --provider 功能。

**Architecture:** 内置命令（init/upgrade/version/env-check/config）保持完整参数定义；pipeline 命令采用极简 parser + 剩余参数转发模式，运行时动态将 `.agents/tools/` 加入 `sys.path` 后通过 `importlib` 导入目标模块；使用 `inspect.signature` 适配 `main()` 有参数/无参数两种签名；policy 采用 REMAINDER 转发避免双重解析；`--provider` 全局参数在各 pipeline 命令中支持。

**Tech Stack:** Python 3.8+, argparse, importlib, inspect, unittest

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `cli/misra-pipeline-cli.py` | 统一 CLI 入口（修改）：添加 pipeline 命令映射、转发逻辑、--provider 支持、env-check 改名、importlib/inspect import |
| `tests/test_misra_pipeline_cli.py` | 测试文件（修改）：添加新命令的 parse_args 测试、转发逻辑测试（含签名适配）、--provider 测试、env-check 测试、旧测试迁移 |
| `.agents/tools/pipeline_cli.py` | 旧分发器（删除）：废弃并移除 |
| `tests/test_pipeline_cli.py` | 旧测试（迁移/删除）：有价值的测试迁移到 test_misra_pipeline_cli.py，然后删除 |

---

### Task 1: 重命名 doctor → env-check + 更新 docstring + 添加 importlib/inspect

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 在文件顶部添加 `import importlib` 和 `import inspect`**

在 `import sys` 之后、`from typing import Any, Dict, Optional` 之前添加：

```python
import importlib
import inspect
```

- [ ] **Step 2: 更新文件头部 docstring**

```python
"""MISRA Pipeline CLI - Distribution and project initialization tool.

Commands:
  init         Initialize .agents/ directory in current project
  upgrade      Upgrade installed .agents/ to latest version
  version      Show CLI and project version
  env-check    Check CLI installation and environment
  config       Manage CLI configuration
  split        Split cppcheck XML into runtime chunks
  run          Run the agent fixing pipeline
  merge        Merge runtime results into reports
  verify       Verify one chunk result
  bootstrap    Generate agent compatibility files
  doctor       Run pipeline diagnostics
  validate     Run provider validation test
  oneshot      Run the one-shot agent entrypoint
  policy       Manage policy configuration
"""
```

- [ ] **Step 3: 修改 parse_args 中 doctor → env-check**

```python
# 原代码:
    # doctor subcommand
    subparsers.add_parser("doctor", help="Check installation and environment.")

# 改为:
    # env-check subcommand
    subparsers.add_parser("env-check", help="Check CLI installation and environment.")
```

- [ ] **Step 4: 重命名 cmd_doctor → cmd_env_check**

```python
# 原代码:
def cmd_doctor(args: argparse.Namespace) -> int:

# 改为:
def cmd_env_check(args: argparse.Namespace) -> int:
    """Check CLI installation and environment."""
```

- [ ] **Step 5: 修改 main() 中的分发**

```python
# 原代码:
    elif args.subcommand == "doctor":
        return cmd_doctor(args)

# 改为:
    elif args.subcommand == "env-check":
        return cmd_env_check(args)
```

- [ ] **Step 6: 更新测试中的 doctor 引用**

修改 `tests/test_misra_pipeline_cli.py`：

```python
# 原:
    def test_parse_args_doctor_subcommand(self):
        """Test parse_args for 'doctor' subcommand."""
        args = misra_pipeline_cli.parse_args(["doctor"])
        self.assertEqual(args.subcommand, "doctor")

# 改为:
    def test_parse_args_env_check_subcommand(self):
        """Test parse_args for 'env-check' subcommand."""
        args = misra_pipeline_cli.parse_args(["env-check"])
        self.assertEqual(args.subcommand, "env-check")
```

更新 `MisraPipelineDoctorTests` 类名改为 `MisraPipelineEnvCheckTests`，所有方法中 `doctor` 改为 `env-check`。

- [ ] **Step 7: 运行测试确认通过**

```bash
cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2
python -m pytest tests/test_misra_pipeline_cli.py -v
```
Expected: 所有测试 PASS

- [ ] **Step 8: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "refactor(cli): rename doctor to env-check, add importlib/inspect imports, update docstring"
```

---

### Task 2: 添加 pipeline 命令映射和转发逻辑（含签名适配和 --provider）

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 在 `if sys.version_info < MIN_PYTHON:` 之后添加 PIPELINE_COMMANDS 映射**

```python
# Pipeline command mapping: subcommand -> module_name in .agents/tools/
PIPELINE_COMMANDS: Dict[str, str] = {
    "split": "split_cppcheck_xml",
    "run": "run_fix_pipeline",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "doctor": "doctor",
    "validate": "validate_real",
    "oneshot": "oneshot",
}
```

- [ ] **Step 2: 添加 _call_module_main 和 _dispatch_pipeline_command 函数**

在 `cmd_env_check` 函数之后、`main()` 之前添加：

```python
def _call_module_main(module, args: list[str]) -> int:
    """Call module.main() with or without argv depending on its signature.

    merge_results, bootstrap_agents, verify_chunk have main() with no args.
    All other modules have main(argv=None).
    """
    sig = inspect.signature(module.main)
    if len(sig.parameters) > 0:
        result = module.main(args)
    else:
        result = module.main()
    return result if isinstance(result, int) else 0


def _dispatch_pipeline_command(command: str, args: list[str], provider: Optional[str] = None) -> int:
    """Dispatch a pipeline command to its implementation module in .agents/tools/."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(
            f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.",
            file=sys.stderr,
        )
        return 1

    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)

    module_name = PIPELINE_COMMANDS[command]
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(
            f"Error: Failed to import module '{module_name}': {exc}",
            file=sys.stderr,
        )
        print("Check that .agents/ is properly installed.", file=sys.stderr)
        return 1

    # Set PIPELINE_AGENT_PROVIDER env var if --provider is specified
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
    try:
        if provider:
            os.environ["PIPELINE_AGENT_PROVIDER"] = provider
        elif original_provider is not None:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        original_argv = sys.argv
        try:
            sys.argv = [f"{module_name}.py", *args]
            return _call_module_main(module, args)
        except Exception as exc:
            print(f"Error running {command}: {exc}", file=sys.stderr)
            return 1
        finally:
            sys.argv = original_argv
    finally:
        # Restore original PIPELINE_AGENT_PROVIDER state
        if original_provider is not None:
            os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
        else:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
```

- [ ] **Step 3: 修改 parse_args 添加新子命令（含 --provider）**

在 `parse_args()` 的 `config_reset` parser 之后、`return parser.parse_args(...)` 之前添加：

```python
    # Pipeline commands (forward to .agents/tools/ modules)
    for cmd_name, module_name in PIPELINE_COMMANDS.items():
        cmd_help = {
            "split": "Split cppcheck XML into runtime chunks",
            "run": "Run the agent fixing pipeline",
            "merge": "Merge runtime results into reports",
            "verify": "Verify one chunk result",
            "bootstrap": "Generate agent compatibility files",
            "doctor": "Run pipeline diagnostics",
            "validate": "Provider validation test (formerly 'validate-real')",
            "oneshot": "Run the one-shot agent entrypoint",
        }.get(cmd_name, f"Run {module_name}")
        cmd_parser = subparsers.add_parser(cmd_name, help=cmd_help)
        cmd_parser.add_argument(
            "--provider", "-P",
            choices=["codex", "claude", "opencode", "kimi"],
            default=None,
            help="Override agent provider (sets PIPELINE_AGENT_PROVIDER env var)",
        )
        cmd_parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments passed to the command")

    # policy subcommand (REMAINDER forwarding, not dual-parsing)
    policy_parser = subparsers.add_parser(
        "policy",
        help="Manage policy configuration",
        epilog=(
            "Examples:\n"
            "  misra-pipeline policy init --template misra_c2012_relaxed\n"
            "  misra-pipeline policy list\n"
            "  misra-pipeline policy list --rule-id misra*\n"
            "  misra-pipeline policy test --rule-id R1.1 --file test.c\n"
            "  misra-pipeline policy add --rule-id R1.1 --action auto_fix\n"
            "\n"
            "Use 'misra-pipeline policy -- --help' to see policy_init's full help."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    policy_parser.add_argument("policy_args", nargs=argparse.REMAINDER, help="Arguments passed to policy_init")
```

- [ ] **Step 4: 修改 main() 添加新分发逻辑**

将 `main()` 函数改为：

```python
def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.subcommand == "version":
        return cmd_version(args)
    elif args.subcommand == "init":
        return cmd_init(args)
    elif args.subcommand == "upgrade":
        return cmd_upgrade(args)
    elif args.subcommand == "env-check":
        return cmd_env_check(args)
    elif args.subcommand == "config":
        return cmd_config(args)
    elif args.subcommand in PIPELINE_COMMANDS:
        provider = getattr(args, "provider", None)
        return _dispatch_pipeline_command(args.subcommand, args.args, provider=provider)
    elif args.subcommand == "policy":
        return _dispatch_policy_command(args.policy_args)

    return 0
```

- [ ] **Step 5: 添加 _dispatch_policy_command 函数**

在 `_dispatch_pipeline_command` 之后添加：

```python
def _dispatch_policy_command(policy_args: list[str]) -> int:
    """Dispatch policy command to policy_init module using REMAINDER forwarding."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(
            f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.",
            file=sys.stderr,
        )
        return 1

    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)

    try:
        policy_init = importlib.import_module("policy_init")
    except ImportError as exc:
        print(
            f"Error: Failed to import policy_init: {exc}",
            file=sys.stderr,
        )
        return 1

    original_argv = sys.argv
    try:
        sys.argv = ["policy_init.py", *policy_args]
        return _call_module_main(policy_init, policy_args)
    except Exception as exc:
        print(f"Error running policy: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.argv = original_argv
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2
python -m pytest tests/test_misra_pipeline_cli.py -v
```
Expected: 所有原有测试 PASS（新命令还没加测试）

- [ ] **Step 7: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): add pipeline commands with dispatch, provider support, and policy forwarding"
```

---

### Task 3: 添加新命令的测试（含签名适配、provider 迁移、旧测试迁移）

**Files:**
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 添加 parse_args 测试**

在 `test_parse_args_config_reset_yes` 之后添加：

```python
    def test_parse_args_split_subcommand(self):
        """Test parse_args for 'split' subcommand."""
        args = misra_pipeline_cli.parse_args(["split", "--input", "cppcheck.xml"])
        self.assertEqual(args.subcommand, "split")
        self.assertEqual(args.args, ["--input", "cppcheck.xml"])

    def test_parse_args_run_subcommand(self):
        """Test parse_args for 'run' subcommand."""
        args = misra_pipeline_cli.parse_args(["run", "--dry-run"])
        self.assertEqual(args.subcommand, "run")
        self.assertEqual(args.args, ["--dry-run"])

    def test_parse_args_merge_subcommand(self):
        """Test parse_args for 'merge' subcommand."""
        args = misra_pipeline_cli.parse_args(["merge"])
        self.assertEqual(args.subcommand, "merge")

    def test_parse_args_verify_subcommand(self):
        """Test parse_args for 'verify' subcommand."""
        args = misra_pipeline_cli.parse_args(["verify", "chunk_001"])
        self.assertEqual(args.subcommand, "verify")
        self.assertEqual(args.args, ["chunk_001"])

    def test_parse_args_bootstrap_subcommand(self):
        """Test parse_args for 'bootstrap' subcommand."""
        args = misra_pipeline_cli.parse_args(["bootstrap"])
        self.assertEqual(args.subcommand, "bootstrap")

    def test_parse_args_doctor_pipeline_subcommand(self):
        """Test parse_args for 'doctor' (pipeline) subcommand."""
        args = misra_pipeline_cli.parse_args(["doctor"])
        self.assertEqual(args.subcommand, "doctor")

    def test_parse_args_validate_subcommand(self):
        """Test parse_args for 'validate' subcommand."""
        args = misra_pipeline_cli.parse_args(["validate"])
        self.assertEqual(args.subcommand, "validate")

    def test_parse_args_oneshot_subcommand(self):
        """Test parse_args for 'oneshot' subcommand."""
        args = misra_pipeline_cli.parse_args(["oneshot"])
        self.assertEqual(args.subcommand, "oneshot")

    def test_parse_args_provider_flag(self):
        """Test --provider flag for pipeline commands."""
        args = misra_pipeline_cli.parse_args(["run", "--provider", "claude"])
        self.assertEqual(args.provider, "claude")

    def test_parse_args_provider_flag_invalid(self):
        """Test --provider rejects invalid values."""
        with self.assertRaises(SystemExit):
            misra_pipeline_cli.parse_args(["run", "--provider", "invalid"])

    def test_parse_args_policy_subcommand(self):
        """Test parse_args for 'policy' with REMAINDER args."""
        args = misra_pipeline_cli.parse_args(["policy", "init", "--template", "misra_c2012_relaxed"])
        self.assertEqual(args.subcommand, "policy")
        self.assertEqual(args.policy_args, ["init", "--template", "misra_c2012_relaxed"])
```

- [ ] **Step 2: 添加转发逻辑测试（含签名适配）**

在文件末尾添加新测试类：

```python
class MisraPipelineDispatchTests(unittest.TestCase):
    def test_dispatch_sets_sys_argv(self):
        """Test that _dispatch_pipeline_command sets sys.argv correctly."""
        seen = {}

        class FakeModuleWithArgs:
            def main(self, argv=None):
                seen["argv"] = list(sys.argv)
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp) / ".agents" / "tools"
            tools_dir.mkdir(parents=True)
            with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleWithArgs()):
                    result = misra_pipeline_cli._dispatch_pipeline_command("split", ["--input", "test.xml"])

        self.assertEqual(result, 0)
        self.assertEqual(seen["argv"], ["split_cppcheck_xml.py", "--input", "test.xml"])

    def test_dispatch_calls_main_without_args(self):
        """Test that _call_module_main handles modules with main() taking no args."""
        seen = {}

        class FakeModuleNoArgs:
            def main(self):
                seen["called"] = True
                return 42

        result = misra_pipeline_cli._call_module_main(FakeModuleNoArgs(), ["--unused"])

        self.assertEqual(result, 42)
        self.assertTrue(seen["called"])

    def test_dispatch_calls_main_with_args(self):
        """Test that _call_module_main handles modules with main(argv=None)."""
        seen = {}

        class FakeModuleWithArgs:
            def main(self, argv=None):
                seen["argv"] = argv
                return 0

        result = misra_pipeline_cli._call_module_main(FakeModuleWithArgs(), ["--input", "test.xml"])

        self.assertEqual(result, 0)
        self.assertEqual(seen["argv"], ["--input", "test.xml"])

    def test_dispatch_missing_tools_dir(self):
        """Test that _dispatch_pipeline_command fails when .agents/tools/ missing."""
        with tempfile.TemporaryDirectory() as tmp:
            # tmp does NOT contain .agents/tools/, so dispatch should return 1
            with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                result = misra_pipeline_cli._dispatch_pipeline_command("split", [])

        self.assertEqual(result, 1)

    def test_dispatch_provider_sets_env(self):
        """Test that --provider sets PIPELINE_AGENT_PROVIDER env var."""
        seen_env = {}
        original = os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        try:
            class FakeModuleWithArgs:
                def main(self, argv=None):
                    seen_env["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                    return 0

            with tempfile.TemporaryDirectory() as tmp:
                tools_dir = Path(tmp) / ".agents" / "tools"
                tools_dir.mkdir(parents=True)
                with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                    with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleWithArgs()):
                        result = misra_pipeline_cli._dispatch_pipeline_command("run", [], provider="claude")

            self.assertEqual(result, 0)
            self.assertEqual(seen_env["provider"], "claude")
        finally:
            if original is not None:
                os.environ["PIPELINE_AGENT_PROVIDER"] = original

    def test_dispatch_provider_restores_env(self):
        """Test that PIPELINE_AGENT_PROVIDER is restored after dispatch."""
        original = "original_value"
        os.environ["PIPELINE_AGENT_PROVIDER"] = original

        try:
            class FakeModuleWithArgs:
                def main(self, argv=None):
                    return 0

            with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleWithArgs()):
                with tempfile.TemporaryDirectory() as tmp:
                    tools_dir = Path(tmp) / ".agents" / "tools"
                    tools_dir.mkdir(parents=True)
                    with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                        misra_pipeline_cli._dispatch_pipeline_command("split", [], provider="codex")

            self.assertEqual(os.environ.get("PIPELINE_AGENT_PROVIDER"), original)
        finally:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
```

注意：需要在文件顶部确保以下导入存在（检查现有导入并补齐缺失项）：

```python
import os
import tempfile
from pathlib import Path
from unittest.mock import patch
```

`os`、`Path` 和 `patch` 在现有测试中已有局部导入，但应统一为顶部导入。`tempfile` 是新增依赖（用于临时目录创建），必须添加到顶部 import 区。注意：所有测试改用 `tempfile.TemporaryDirectory` + `patch` 方案后不再需要 `MagicMock`，因此无需导入。

- [ ] **Step 3: 迁移旧测试中有价值的测试**

从 `tests/test_pipeline_cli.py` 迁移以下测试逻辑到 `tests/test_misra_pipeline_cli.py`：

```python
    # From test_pipeline_cli.py: invalid command rejection
    def test_parse_args_rejects_invalid_subcommand(self):
        """Test that invalid subcommands are rejected."""
        with self.assertRaises(SystemExit):
            misra_pipeline_cli.parse_args(["invalid_command"])

    # Provider environment variable management (adapted from test_pipeline_cli.py lines 92-173)
    def test_dispatch_provider_clears_stale_env(self):
        """Test that second call without --provider clears stale env."""
        seen_first = {}
        seen_second = {}

        class FakeModuleFirst:
            def main(self, argv=None):
                seen_first["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                return 0

        class FakeModuleSecond:
            def main(self, argv=None):
                seen_second["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                return 0

        original = os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tools_dir = Path(tmp) / ".agents" / "tools"
                tools_dir.mkdir(parents=True)

                with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                    with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleFirst()):
                        misra_pipeline_cli._dispatch_pipeline_command("split", [], provider="codex")

                    with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleSecond()):
                        misra_pipeline_cli._dispatch_pipeline_command("split", [])

            self.assertEqual(seen_first["provider"], "codex")
            self.assertIsNone(seen_second["provider"])
            self.assertIsNone(os.environ.get("PIPELINE_AGENT_PROVIDER"))
        finally:
            if original is not None:
                os.environ["PIPELINE_AGENT_PROVIDER"] = original
```

- [ ] **Step 4: 运行所有测试**

```bash
cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2
python -m pytest tests/test_misra_pipeline_cli.py -v
```
Expected: 所有测试 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_misra_pipeline_cli.py
git commit -m "test(cli): add dispatch tests with signature adaptation, provider env tests, and legacy test migration"
```

---

### Task 4: 废弃并移除 pipeline_cli.py

**Files:**
- Delete: `.agents/tools/pipeline_cli.py`
- Delete: `tests/test_pipeline_cli.py`

- [ ] **Step 1: 删除 .agents/tools/pipeline_cli.py**

```bash
cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2
rm .agents/tools/pipeline_cli.py
```

- [ ] **Step 2: 删除 tests/test_pipeline_cli.py**

```bash
rm tests/test_pipeline_cli.py
```

- [ ] **Step 3: 验证删除后测试不受影响**

```bash
python -m pytest tests/test_misra_pipeline_cli.py -v
```
Expected: 所有测试 PASS（不再依赖 pipeline_cli.py）

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "refactor(cli): remove deprecated pipeline_cli.py dispatcher and its tests"
```

---

### Task 5: 更新 init 分发配置（确保 tools 目录仍被复制但不含 pipeline_cli.py）

**Files:**
- No changes needed

- [ ] **Step 1: 确认 AGENTS_DIRS_TO_COPY 已包含 tools**

检查现有代码确认 `tools` 已在列表中。由于 `pipeline_cli.py` 已在 Task 4 中从源仓库删除，新 init 的项目自然不会包含它。

无需修改，跳过 commit。

---

## Self-Review Checklist

### 1. Spec Coverage

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 统一入口在 misra-pipeline-cli.py | Task 2 |
| 废弃 pipeline_cli.py | Task 4 |
| doctor → env-check | Task 1 |
| 新增 split/run/merge/verify/bootstrap/doctor/validate/oneshot 命令 | Task 2 |
| policy 子命令（REMAINDER 转发 + epilog 示例） | Task 2 |
| 模块保留在 .agents/tools/ | Task 5（确认） |
| 转发逻辑（sys.path + importlib + sys.argv + inspect） | Task 2 |
| main() 签名适配（无参数模块） | Task 2, Task 3 |
| --provider 环境变量迁移 | Task 2, Task 3 |
| 测试覆盖（含签名适配和 provider） | Task 3 |
| 旧测试迁移 | Task 3 |
| 向后兼容（init 分发） | Task 5 |
| docstring 更新 | Task 1 |
| validate 改名兼容提示 | Task 2（help 文本） |
| import importlib/inspect | Task 1 |
| sys.path 不恢复（有意为之） | Task 2（注释说明） |

### 2. Placeholder Scan

- [x] 无 "TBD"、"TODO"、"implement later"
- [x] 无 "Add appropriate error handling" 等模糊描述
- [x] 所有代码步骤包含完整代码
- [x] 所有测试步骤包含完整测试代码
- [x] 所有命令包含预期输出

### 3. Type Consistency

- [x] `PIPELINE_COMMANDS` 类型 `Dict[str, str]` 一致
- [x] `_dispatch_pipeline_command` 签名 `(str, list[str], Optional[str]) -> int` 一致
- [x] `_call_module_main` 签名 `(module, list[str]) -> int` 一致
- [x] `_dispatch_policy_command` 签名 `(list[str]) -> int` 一致
- [x] `main()` 返回类型 `int` 一致
- [x] `_call_module_main` 使用 `inspect.signature` 适配有/无参数两种签名

### 4. v2 Review Fixes

- [x] `test_dispatch_provider_sets_env` 补齐临时目录创建和 Path.cwd mock
- [x] `test_dispatch_missing_tools_dir` 改用 `tempfile.TemporaryDirectory` 替代链式 MagicMock
- [x] `seen_second.get("provider")` 改为 `seen_second["provider"]`
- [x] 添加 `import tempfile` 和 `from unittest.mock import patch` 到 import 说明（移除未使用的 `MagicMock`）
- [x] `test_dispatch_sets_sys_argv` 补齐临时目录创建和 Path.cwd mock
- [x] policy parser 添加 epilog 示例（Task 2 Step 3 和 design §5.2）

### 5. v3 Review Fixes

- [x] 设计 §5.1 `_dispatch_pipeline_command` 签名加入 `provider` 参数，与 §6 和计划一致
- [x] 设计 §5.1 移除 `inserted` 局部变量，与计划实现风格统一
- [x] 移除未使用的 `MagicMock` import（所有测试改用 tempfile + patch 方案）

---

## 执行选项

Plan complete and saved to `docs/superpowers/plans/2026-05-06-unified-cli-entry-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?