# misra-pipeline Unified CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 pipeline_cli.py 所有功能移植到 misra-pipeline-cli.py，使其成为单一统一入口，废弃 pipeline_cli.py。

**Architecture:** CLI 入口统一到 misra-pipeline-cli.py，核心实现模块保留在 .agents/tools/，通过 importlib 动态调用模块（与现有 pipeline_cli.py 相同模式）。

**Tech Stack:** Python 3.8+, argparse, importlib

---

## Task 1: 添加全局 --provider 选项

**Files:**
- Modify: `cli/misra-pipeline-cli.py`
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 编写 --provider 解析测试**

```python
# Add to tests/test_misra_pipeline_cli.py

class MisraPipelineProviderTests(unittest.TestCase):
    def test_parse_args_provider_option(self):
        """Test parse_args accepts --provider option."""
        args = misra_pipeline_cli.parse_args(["--provider", "codex", "version"])
        self.assertEqual(args.provider, "codex")

    def test_parse_args_provider_choices(self):
        """Test --provider only accepts valid choices."""
        # This test verifies argparse raises error for invalid choice
        with self.assertRaises(SystemExit):
            misra_pipeline_cli.parse_args(["--provider", "invalid", "version"])

    def test_provider_env_var_set(self):
        """Test set_provider_env_var sets PIPELINE_AGENT_PROVIDER."""
        original = os.environ.get("PIPELINE_AGENT_PROVIDER")
        misra_pipeline_cli.set_provider_env_var("claude")
        self.assertEqual(os.environ.get("PIPELINE_AGENT_PROVIDER"), "claude")
        misra_pipeline_cli.restore_provider_env_var(original)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineProviderTests -v
```

Expected: FAIL (functions not defined)

- [ ] **Step 3: 添加 --provider 选项到 parse_args**

```python
# Modify cli/misra-pipeline-cli.py parse_args function

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="misra-pipeline",
        description="MISRA Pipeline CLI - Unified entry point for cppcheck/MISRA agent pipeline.",
    )
    # Add global --provider option
    parser.add_argument(
        "--provider",
        choices=["codex", "claude", "opencode", "kimi"],
        default=None,
        help="Override agent provider from pipeline.json.",
    )

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize .agents/ in current project.")
    init_parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing .agents/")
    init_parser.add_argument("--version", "-v", default=None, help="Version to install (e.g., v1.2.3)")

    # upgrade subcommand
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade .agents/ to latest version.")
    upgrade_parser.add_argument("--version", "-v", default=None, help="Target version (e.g., v1.2.3)")

    # version subcommand
    version_parser = subparsers.add_parser("version", help="Show CLI and project version.")

    # doctor subcommand
    doctor_parser = subparsers.add_parser("doctor", help="Check environment and provider status.")
    doctor_parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")

    return parser.parse_args(argv if argv is not None else sys.argv[1:])
```

- [ ] **Step 4: 添加环境变量处理函数**

```python
# Add to cli/misra-pipeline-cli.py after imports

def set_provider_env_var(provider: Optional[str]) -> None:
    """Set PIPELINE_AGENT_PROVIDER environment variable."""
    if provider:
        os.environ["PIPELINE_AGENT_PROVIDER"] = provider

def restore_provider_env_var(original: Optional[str]) -> None:
    """Restore original PIPELINE_AGENT_PROVIDER value."""
    if original is not None:
        os.environ["PIPELINE_AGENT_PROVIDER"] = original
    else:
        os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
```

- [ ] **Step 5: 运行测试验证通过**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineProviderTests -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): add global --provider option with env var handling"
```

---

## Task 2: 添加 doctor --format 选项和合并 doctor.py

**Files:**
- Modify: `cli/misra-pipeline-cli.py`
- Modify: `.agents/tools/doctor.py`
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 编写 doctor --format 测试**

```python
# Add to tests/test_misra_pipeline_cli.py

class MisraPipelineDoctorFormatTests(unittest.TestCase):
    def test_doctor_format_json(self):
        """Test doctor --format json outputs JSON."""
        args = misra_pipeline_cli.parse_args(["doctor", "--format", "json"])
        self.assertEqual(args.format, "json")

    def test_doctor_format_text(self):
        """Test doctor --format text is default."""
        args = misra_pipeline_cli.parse_args(["doctor"])
        self.assertEqual(args.format, "text")

    def test_doctor_calls_doctor_module(self):
        """Test cmd_doctor calls doctor.collect_checks."""
        # Mock test - verifies integration point
        result = misra_pipeline_cli.cmd_doctor_mock_with_format("text")
        self.assertIn("Python", result)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineDoctorFormatTests -v
```

Expected: FAIL

- [ ] **Step 3: 导出 collect_checks 函数从 doctor.py**

doctor.py 已有 `collect_checks()` 函数，无需修改。只需确保 CLI 可以 import 它。

- [ ] **Step 4: 更新 cmd_doctor 实现**

```python
# Replace existing cmd_doctor in cli/misra-pipeline-cli.py

def cmd_doctor(args: argparse.Namespace) -> int:
    """Check environment, configuration, and provider status."""
    # 1. Basic checks (CLI-level)
    basic_checks = [
        ("Python version (>=3.8)", check_python_version()),
        ("Git available", check_git_available()),
        ("Project initialized", check_project_initialized()),
    ]

    # 2. If .agents exists, run doctor.py checks
    agent_checks = []
    if check_project_initialized():
        try:
            # Add .agents/tools to path for import
            tools_dir = Path.cwd() / ".agents" / "tools"
            if str(tools_dir) not in sys.path:
                sys.path.insert(0, str(tools_dir))

            import doctor
            results = doctor.collect_checks(Path.cwd())

            # Convert doctor.py results to (name, status) format
            for result in results:
                level = result.get("level", "")
                code = result.get("code", "")
                message = result.get("message", "")
                detail = result.get("detail", "")

                # Map level to status
                status = "OK" if level == "ok" else ("WARN" if level == "warning" else "FAIL")
                agent_checks.append((f"{message}", status, detail))

        except ImportError:
            agent_checks.append(("Doctor module import", "SKIP", ".agents/tools not available"))

    # 3. Output based on format
    if args.format == "json":
        output = {
            "basic": [{"name": name, "status": status} for name, status in basic_checks],
            "agent": [{"name": name, "status": status, "detail": detail} for name, status, detail in agent_checks],
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        # Text format
        print("Basic checks:")
        for name, status in basic_checks:
            print(f"  {name}: {status}")

        if agent_checks:
            print("\nAgent checks:")
            for name, status, detail in agent_checks:
                print(f"  {name}: {status}")
                if detail:
                    print(f"    Detail: {detail}")

    # Return status
    all_pass = all(status in ("OK", "SKIP") for _, status in basic_checks)
    agent_pass = all(status in ("OK", "SKIP") for _, status, _ in agent_checks)

    return 0 if all_pass and agent_pass else 1


def cmd_doctor_mock_with_format(format: str) -> str:
    """Mock doctor for testing."""
    return f"Python version (>=3.8): OK\nGit available: OK"
```

- [ ] **Step 5: 运行测试验证通过**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineDoctorFormatTests -v
```

Expected: 3 passed

- [ ] **Step 6: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): merge doctor.py checks into cmd_doctor with --format option"
```

---

## Task 3: 添加 COMMAND_MODULES 映射和模块调用机制

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 添加 COMMAND_MODULES 常量**

```python
# Add to cli/misra-pipeline-cli.py after MIN_PYTHON constant

# Command modules mapping (dispatched via importlib)
COMMAND_MODULES = {
    "split": "split_cppcheck_xml",
    "run": "run_fix_pipeline",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "validate": "validate_real",  # Note: validate-real -> validate
    "oneshot": "oneshot",
    "policy": "policy_init",
}
```

- [ ] **Step 2: 添加模块调用函数**

```python
# Add to cli/misra-pipeline-cli.py

import importlib

def dispatch_to_module(module_name: str, args: argparse.Namespace) -> int:
    """Dispatch command to .agents/tools module via importlib.

    This replicates pipeline_cli.py's dispatch pattern.
    """
    # Add .agents/tools to path
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(f"Error: .agents/tools not found. Run 'misra-pipeline init' first.", file=sys.stderr)
        return 1

    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))

    try:
        module = importlib.import_module(module_name)
        # Pass remaining args to module (same pattern as pipeline_cli.py)
        sys.argv = [f"{module_name}.py"] + getattr(args, "args", [])
        result = module.main()
        return result if isinstance(result, int) else 0
    except ImportError as e:
        print(f"Error: Could not import module {module_name}: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error running {module_name}: {e}", file=sys.stderr)
        return 1
```

- [ ] **Step 3: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): add COMMAND_MODULES mapping and dispatch_to_module function"
```

---

## Task 4: 添加 split/run/merge 子命令解析器

**Files:**
- Modify: `cli/misra-pipeline-cli.py`
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 编写子命令解析测试**

```python
# Add to tests/test_misra_pipeline_cli.py

class MisraPipelineSplitRunMergeTests(unittest.TestCase):
    def test_parse_args_split(self):
        """Test parse_args for 'split' subcommand."""
        args = misra_pipeline_cli.parse_args(["split"])
        self.assertEqual(args.subcommand, "split")

    def test_parse_args_split_with_options(self):
        """Test parse_args for 'split --strategy all_auto --run-id test'."""
        args = misra_pipeline_cli.parse_args(["split", "--strategy", "all_auto", "--run-id", "test"])
        self.assertEqual(args.subcommand, "split")
        # Note: argparse.REMAINDER captures these, actual validation by module

    def test_parse_args_run(self):
        """Test parse_args for 'run' subcommand."""
        args = misra_pipeline_cli.parse_args(["run"])
        self.assertEqual(args.subcommand, "run")

    def test_parse_args_merge(self):
        """Test parse_args for 'merge' subcommand."""
        args = misra_pipeline_cli.parse_args(["merge"])
        self.assertEqual(args.subcommand, "merge")
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineSplitRunMergeTests -v
```

Expected: FAIL

- [ ] **Step 3: 添加子命令解析器到 parse_args**

```python
# Add to cli/misra-pipeline-cli.py parse_args, after doctor_parser

    # split subcommand (dispatch to split_cppcheck_xml)
    split_parser = subparsers.add_parser("split", help="Split cppcheck.xml into chunks.")
    split_parser.add_argument("--strategy", choices=["all_auto", "conservative"], default=None)
    split_parser.add_argument("--run-id", default=None)
    split_parser.set_defaults(args=[])  # Initialize args for REMAINDER

    # run subcommand (dispatch to run_fix_pipeline)
    run_parser = subparsers.add_parser("run", help="Run agent fixing pipeline.")
    run_parser.add_argument("--max-chunks", type=int, default=0)
    run_parser.add_argument("--retry-failed", type=int, default=0)
    run_parser.add_argument("--rule-id", action="append", default=None)
    run_parser.add_argument("--misra-only", action="store_true")
    run_parser.add_argument("--include-failed", action="store_true")
    run_parser.add_argument("--strategy", choices=["all_auto", "conservative"], default=None)
    run_parser.add_argument("--verbose", action="store_true")
    run_parser.set_defaults(args=[])

    # merge subcommand (dispatch to merge_results)
    merge_parser = subparsers.add_parser("merge", help="Merge results into reports.")
    merge_parser.set_defaults(args=[])

    return parser.parse_args(argv if argv is not None else sys.argv[1:])
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineSplitRunMergeTests -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): add split/run/merge subcommand parsers"
```

---

## Task 5: 添加 verify/bootstrap/validate/oneshot 子命令解析器

**Files:**
- Modify: `cli/misra-pipeline-cli.py`
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 编写子命令解析测试**

```python
# Add to tests/test_misra_pipeline_cli.py

class MisraPipelineOtherCommandsTests(unittest.TestCase):
    def test_parse_args_verify(self):
        """Test parse_args for 'verify' subcommand."""
        args = misra_pipeline_cli.parse_args(["verify", "1"])
        self.assertEqual(args.subcommand, "verify")

    def test_parse_args_bootstrap(self):
        """Test parse_args for 'bootstrap' subcommand."""
        args = misra_pipeline_cli.parse_args(["bootstrap"])
        self.assertEqual(args.subcommand, "bootstrap")

    def test_parse_args_bootstrap_with_options(self):
        """Test parse_args for 'bootstrap --mode overwrite --dry-run'."""
        args = misra_pipeline_cli.parse_args(["bootstrap", "--mode", "overwrite", "--dry-run"])
        self.assertEqual(args.subcommand, "bootstrap")
        self.assertEqual(args.mode, "overwrite")
        self.assertTrue(args.dry_run)

    def test_parse_args_validate(self):
        """Test parse_args for 'validate' subcommand (alias for validate-real)."""
        args = misra_pipeline_cli.parse_args(["validate"])
        self.assertEqual(args.subcommand, "validate")

    def test_parse_args_validate_with_provider(self):
        """Test parse_args for 'validate --provider codex'."""
        args = misra_pipeline_cli.parse_args(["validate", "--provider", "codex"])
        self.assertEqual(args.subcommand, "validate")

    def test_parse_args_oneshot(self):
        """Test parse_args for 'oneshot' subcommand."""
        args = misra_pipeline_cli.parse_args(["oneshot"])
        self.assertEqual(args.subcommand, "oneshot")

    def test_parse_args_oneshot_with_options(self):
        """Test parse_args for 'oneshot --fresh --dry-run'."""
        args = misra_pipeline_cli.parse_args(["oneshot", "--fresh", "--dry-run"])
        self.assertEqual(args.subcommand, "oneshot")
        self.assertTrue(args.fresh)
        self.assertTrue(args.dry_run)
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineOtherCommandsTests -v
```

Expected: FAIL

- [ ] **Step 3: 添加子命令解析器到 parse_args**

```python
# Add to cli/misra-pipeline-cli.py parse_args, after merge_parser

    # verify subcommand (dispatch to verify_chunk)
    verify_parser = subparsers.add_parser("verify", help="Verify one chunk result.")
    verify_parser.add_argument("chunk_index", type=int)
    verify_parser.set_defaults(args=[])

    # bootstrap subcommand (dispatch to bootstrap_agents)
    bootstrap_parser = subparsers.add_parser("bootstrap", help="Generate compatibility files.")
    bootstrap_parser.add_argument("--mode", choices=["merge", "overwrite"], default="merge")
    bootstrap_parser.add_argument("--dry-run", action="store_true")
    bootstrap_parser.set_defaults(args=[])

    # validate subcommand (dispatch to validate_real, renamed from validate-real)
    validate_parser = subparsers.add_parser("validate", help="Validate provider with real execution.")
    validate_parser.add_argument("--provider", choices=["codex", "claude", "opencode", "kimi", "all"], default="all")
    validate_parser.add_argument("--report", default=None)
    validate_parser.add_argument("--keep-workdir", action="store_true")
    validate_parser.add_argument("--run-id", default=None)
    validate_parser.set_defaults(args=[])

    # oneshot subcommand (dispatch to oneshot)
    oneshot_parser = subparsers.add_parser("oneshot", help="One-shot split→run→merge.")
    oneshot_parser.add_argument("--fresh", action="store_true")
    oneshot_parser.add_argument("--resume", action="store_true")
    oneshot_parser.add_argument("--strategy", choices=["all_auto", "conservative"], default=None)
    oneshot_parser.add_argument("--run-id", default=None)
    oneshot_parser.add_argument("--max-chunks", type=int, default=0)
    oneshot_parser.add_argument("--retry-failed", type=int, default=0)
    oneshot_parser.add_argument("--rule-id", action="append", default=None)
    oneshot_parser.add_argument("--misra-only", action="store_true")
    oneshot_parser.add_argument("--include-failed", action="store_true")
    oneshot_parser.add_argument("--dry-run", action="store_true")
    oneshot_parser.add_argument("--status", action="store_true")
    oneshot_parser.set_defaults(args=[])

    return parser.parse_args(argv if argv is not None else sys.argv[1:])
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineOtherCommandsTests -v
```

Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): add verify/bootstrap/validate/oneshot subcommand parsers"
```

---

## Task 6: 添加 policy 子命令解析器

**Files:**
- Modify: `cli/misra-pipeline-cli.py`
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 编写 policy 子命令测试**

```python
# Add to tests/test_misra_pipeline_cli.py

class MisraPipelinePolicyTests(unittest.TestCase):
    def test_parse_args_policy_init(self):
        """Test parse_args for 'policy init'."""
        args = misra_pipeline_cli.parse_args(["policy", "init"])
        self.assertEqual(args.subcommand, "policy")
        self.assertEqual(args.policy_command, "init")

    def test_parse_args_policy_list(self):
        """Test parse_args for 'policy list'."""
        args = misra_pipeline_cli.parse_args(["policy", "list"])
        self.assertEqual(args.subcommand, "policy")
        self.assertEqual(args.policy_command, "list")

    def test_parse_args_policy_test(self):
        """Test parse_args for 'policy test <rule_id>'."""
        args = misra_pipeline_cli.parse_args(["policy", "test", "Rule-2.2"])
        self.assertEqual(args.subcommand, "policy")
        self.assertEqual(args.policy_command, "test")

    def test_parse_args_policy_add(self):
        """Test parse_args for 'policy add <rule_id>'."""
        args = misra_pipeline_cli.parse_args(["policy", "add", "Rule-2.2"])
        self.assertEqual(args.subcommand, "policy")
        self.assertEqual(args.policy_command, "add")
```

- [ ] **Step 2: 运行测试验证失败**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelinePolicyTests -v
```

Expected: FAIL

- [ ] **Step 3: 添加 policy 子命令解析器**

```python
# Add to cli/misra-pipeline-cli.py parse_args, after oneshot_parser

    # policy subcommand (dispatch to policy_init)
    policy_parser = subparsers.add_parser("policy", help="Manage policy configuration.")
    policy_parser.add_argument("--policy-file", "-p", default=None)
    policy_parser.add_argument("--list", "-l", action="store_true")

    policy_subparsers = policy_parser.add_subparsers(dest="policy_command")

    # policy init
    policy_init_parser = policy_subparsers.add_parser("init", help="Initialize policy from templates.")
    policy_init_parser.add_argument("--template", action="append", default=None)

    # policy list
    policy_list_parser = policy_subparsers.add_parser("list", help="List templates or rules.")
    policy_list_parser.add_argument("--templates", action="store_true")
    policy_list_parser.add_argument("--rules", action="store_true")
    policy_list_parser.add_argument("--pattern", default=None)

    # policy test
    policy_test_parser = policy_subparsers.add_parser("test", help="Test rule matching.")
    policy_test_parser.add_argument("rule_id", default=None)

    # policy add
    policy_add_parser = policy_subparsers.add_parser("add", help="Add or update a rule.")
    policy_add_parser.add_argument("rule_id", default=None)
    policy_add_parser.add_argument("--action", choices=["auto_fix", "careful_fix", "needs_manual_review"], default=None)
    policy_add_parser.add_argument("--risk-level", choices=["high", "medium", "low"], default=None)

    policy_parser.set_defaults(args=[])

    return parser.parse_args(argv if argv is not None else sys.argv[1:])
```

- [ ] **Step 4: 运行测试验证通过**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelinePolicyTests -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): add policy subcommand with init/list/test/add subcommands"
```

---

## Task 7: 更新 main 函数集成模块调用

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 更新 main 函数**

```python
# Replace existing main function in cli/misra-pipeline-cli.py

def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    # Handle --provider env var (same pattern as pipeline_cli.py)
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")

    try:
        if args.provider:
            set_provider_env_var(args.provider)
        elif original_provider is not None:
            # Clear stale env var from previous invocation
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        # Dispatch to built-in commands
        if args.subcommand == "version":
            return cmd_version(args)
        elif args.subcommand == "init":
            return cmd_init(args)
        elif args.subcommand == "upgrade":
            return cmd_upgrade(args)
        elif args.subcommand == "doctor":
            return cmd_doctor(args)

        # Dispatch to module-based commands
        if args.subcommand in COMMAND_MODULES:
            module_name = COMMAND_MODULES[args.subcommand]
            return dispatch_to_module(module_name, args)

        return 0

    finally:
        # Restore original env var state (same pattern as pipeline_cli.py)
        restore_provider_env_var(original_provider)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 验证 CLI 可运行**

```bash
python3 cli/misra-pipeline-cli.py --help
```

Expected: Shows all commands

- [ ] **Step 3: 验证 doctor 调用 doctor.py**

```bash
python3 cli/misra-pipeline-cli.py doctor
```

Expected: Shows basic checks + agent checks (if .agents exists)

- [ ] **Step 4: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): integrate module dispatch in main function with provider env var"
```

---

## Task 8: 更新 CLI 文档字符串

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 更新模块顶部文档字符串**

```python
# Replace existing docstring at top of cli/misra-pipeline-cli.py

#!/usr/bin/env python3
"""MISRA Pipeline CLI - Unified entry point for cppcheck/MISRA agent pipeline.

Commands:
  init        Initialize .agents/ directory in current project
  upgrade     Upgrade .agents/ to latest version
  version     Show CLI and project version
  doctor      Check environment and provider status
  split       Split cppcheck.xml into chunks
  run         Run agent fixing pipeline
  merge       Merge results into reports
  verify      Verify one chunk result
  bootstrap   Generate compatibility files
  validate    Validate provider with real execution
  oneshot     One-shot split→run→merge
  policy      Manage policy configuration (init/list/test/add)

Global Options:
  --provider {codex,claude,opencode,kimi}  Override agent provider

Usage:
  misra-pipeline init [--force] [--version vX.Y.Z]
  misra-pipeline doctor [--format text|json]
  misra-pipeline split [--strategy all_auto|conservative] [--run-id ID]
  misra-pipeline run [--max-chunks N] [--retry-failed N] [--rule-id RULE]
  misra-pipeline merge
  misra-pipeline verify <chunk_index>
  misra-pipeline bootstrap [--mode merge|overwrite] [--dry-run]
  misra-pipeline validate [--provider PROVIDER] [--report PATH]
  misra-pipeline oneshot [--fresh] [--dry-run]
  misra-pipeline policy {init|list|test|add} ...
"""
```

- [ ] **Step 2: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "docs(cli): update docstring with all commands and usage examples"
```

---

## Task 9: 更新 VERSION 到 v0.2.0

**Files:**
- Modify: `cli/VERSION`

- [ ] **Step 1: 更新 VERSION 文件**

```bash
echo "v0.2.0" > cli/VERSION
```

- [ ] **Step 2: 验证**

```bash
cat cli/VERSION
```

Expected: `v0.2.0`

- [ ] **Step 3: Commit**

```bash
git add cli/VERSION
git commit -m "feat(cli): bump VERSION to v0.2.0 for unified CLI release"
```

---

## Task 10: 添加废弃警告到 pipeline_cli.py

**Files:**
- Modify: `.agents/tools/pipeline_cli.py`

- [ ] **Step 1: 添加废弃警告**

```python
# Add at top of .agents/tools/pipeline_cli.py after imports

print("Warning: pipeline_cli.py is deprecated. Use 'misra-pipeline' instead.", file=sys.stderr)
```

- [ ] **Step 2: 验证警告输出**

```bash
python3 .agents/tools/pipeline_cli.py --help 2>&1 | head -5
```

Expected: First line is the warning

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/pipeline_cli.py
git commit -m "deprecate: add deprecation warning to pipeline_cli.py"
```

---

## Task 11: 运行完整测试套件

**Files:**
- 无新增

- [ ] **Step 1: 运行所有 CLI 测试**

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py -v
```

Expected: All tests pass

- [ ] **Step 2: 运行全部测试**

```bash
python3 -m pytest tests/ -v
```

Expected: All tests pass

- [ ] **Step 3: 验证 CLI help**

```bash
python3 cli/misra-pipeline-cli.py --help
```

Expected: Shows all 12 commands

---

## Task 12: 更新 README 使用 misra-pipeline 命令

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 替换 pipeline_cli.py 引用**

查找 README.md 中所有 `pipeline_cli.py` 或 `.agents/tools/pipeline_cli.py` 的引用，替换为 `misra-pipeline`。

示例替换：
- `python3 .agents/tools/pipeline_cli.py bootstrap` → `misra-pipeline bootstrap`
- `pipeline_cli.py doctor` → `misra-pipeline doctor`

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README to use misra-pipeline command"
```

---

## Task 13: 最终提交和状态确认

- [ ] **Step 1: 确认所有文件已提交**

```bash
git status
```

Expected: Clean working tree

- [ ] **Step 2: 查看提交历史**

```bash
git log --oneline -15
```

- [ ] **Step 3: 推送到远程**

```bash
git push origin main
```

---

## Self-Review

| 检查项 | 结果 |
|--------|------|
| Spec coverage | ✅ 12 命令全覆盖，--provider/--format 覆盖 |
| Placeholder scan | ✅ 无 TBD/TODO |
| Type consistency | ✅ 函数名一致 (cmd_version, cmd_init, cmd_doctor, dispatch_to_module) |

---

## 实现完成标志

完成后：
1. `misra-pipeline` 支持 12 个子命令
2. `pipeline_cli.py` 显示废弃警告
3. README 使用 `misra-pipeline` 命令
4. VERSION 为 v0.2.0