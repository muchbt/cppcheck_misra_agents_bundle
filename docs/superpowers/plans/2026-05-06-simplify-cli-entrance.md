# CLI 入口简化 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify MISRA Pipeline CLI from 14 flat commands to a layered structure, making `run` the primary command with oneshot logic and first-class parameters.

**Architecture:** `cmd_run()` in CLI imports helper functions from oneshot.py via dynamic import (same `sys.path` mechanism as `_dispatch_pipeline_command`). oneshot.py stays in `.agents/tools/` but marked deprecated. `status` becomes a top-level command. `oneshot` gets a deprecated alias. policy_init.py gains interactive template selection.

**Tech Stack:** Python 3.8+, argparse, unittest

---

### Task 1: 修复 oneshot.py 旧引用 + 标记 deprecated

**Files:**
- Modify: `.agents/tools/oneshot.py:322,349,375,389`
- Modify: `.agents/tools/oneshot.py:1` (添加 deprecated 注释)

- [ ] **Step 1: 添加 deprecated 注释到文件头**

In `.agents/tools/oneshot.py`, add a deprecation notice at the top (after the `from __future__` line):

```python
"""DEPRECATED: Use 'misra-pipeline run' instead. This module is kept for backward compatibility."""
```

- [ ] **Step 2: 修复 4 处旧命令引用**

Replace all 4 occurrences of `python3 .agents/tools/pipeline_cli.py doctor` with `misra-pipeline doctor`:

- Line 322: `print("[oneshot] 预检查未通过。请先执行 `python3 .agents/tools/pipeline_cli.py doctor`。")` → `print("[run] 预检查未通过。请先执行 `misra-pipeline doctor`。")`
- Line 349: `print("[oneshot] 执行失败。建议先运行 `python3 .agents/tools/pipeline_cli.py doctor`。")` → `print("[run] 执行失败。建议先运行 `misra-pipeline doctor`。")`
- Line 375: same as line 349 → `print("[run] 执行失败。建议先运行 `misra-pipeline doctor`。")`
- Line 389: same pattern → `print("[run] 执行失败。建议先运行 `misra-pipeline doctor`。")`

Also change all `[oneshot]` prefixes in print statements to `[run]` for consistency (lines 260-399). This is a search-and-replace within this file.

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `python3 -m pytest tests/ -q`
Expected: All tests pass (240+)

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/oneshot.py
git commit -m "fix(oneshot): replace old pipeline_cli.py references with misra-pipeline, mark deprecated"
```

---

### Task 2: 修改 PIPELINE_COMMANDS 映射和 parse_args

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 从 PIPELINE_COMMANDS 移除 run 和 oneshot**

In `PIPELINE_COMMANDS` dict (around line 55-64), remove `"run"` and `"oneshot"` entries:

```python
PIPELINE_COMMANDS: Dict[str, str] = {
    "split": "split_cppcheck_xml",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "doctor": "doctor",
    "validate": "validate_real",
}
```

- [ ] **Step 2: 在 parse_args 中添加 run、status、oneshot 子命令定义**

After the `policy` parser block (around line 213), add three new subcommand parsers:

```python
    # run subcommand (absorbs oneshot functionality)
    run_parser = subparsers.add_parser("run", help="Run the MISRA fix pipeline (split→agent→merge)")
    run_parser.add_argument("--fresh", action="store_true", help="Force fresh start, ignore existing progress")
    run_parser.add_argument("--resume", action="store_true", help="Explicit resume mode")
    run_parser.add_argument("--dry-run", action="store_true", help="Preview mode: show chunk summary without starting agents")
    run_parser.add_argument("--status", action="store_true", help="Show current run progress and exit")
    run_parser.add_argument("--stage", choices=["split", "agent", "merge"], default=None, help="Run a single stage only")
    run_parser.add_argument("--strategy", choices=["conservative", "all_auto"], default=None, help="Fix strategy")
    run_parser.add_argument("--max-chunks", type=int, default=None, help="Maximum number of chunks")
    run_parser.add_argument("--retry-failed", type=int, default=None, help="Retry failed chunks N times")
    run_parser.add_argument("--rule-id", action="append", default=[], help="Rule ID filter (can be repeated)")
    run_parser.add_argument("--misra-only", action="store_true", help="Only process MISRA rules")
    run_parser.add_argument("--include-failed", action="store_true", help="Include previously failed chunks")
    run_parser.add_argument("--run-id", default=None, help="Specify run ID (format: YYYYMMDD-XXX)")
    run_parser.add_argument("--verbose", action="store_true", help="Print full stdout/stderr for each chunk")
    run_parser.add_argument(
        "--provider", "-P",
        choices=["codex", "claude", "opencode", "kimi"],
        default=None,
        help="Override agent provider",
    )

    # status subcommand
    subparsers.add_parser("status", help="Show current pipeline run progress")

    # oneshot deprecated alias
    oneshot_parser = subparsers.add_parser("oneshot", help="(deprecated) Use 'run' instead")
```

- [ ] **Step 3: 修改 parse_known_args 返回逻辑**

The `parse_known_args` return block currently attaches `args`/`policy_args` based on subcommand. Since `run` now has explicit args (no forwarding needed), remove `run` from the forwarding logic. Update the attachment block:

```python
    # Use parse_known_args so --flags like --dry-run pass through to subcommands
    parsed, forwarded = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    if parsed.subcommand in PIPELINE_COMMANDS:
        parsed.args = forwarded
    elif parsed.subcommand == "policy":
        parsed.policy_args = forwarded

    return parsed
```

No change needed here — `run` is no longer in `PIPELINE_COMMANDS`, so it won't get `args` attached. `oneshot` is also not in `PIPELINE_COMMANDS` so it also doesn't get forwarding. This is correct.

- [ ] **Step 4: 更新文件头 docstring**

Update the module docstring (lines 1-19) to reflect the new command structure. Change the `Commands:` section to:

```python
"""MISRA Pipeline CLI - Distribution and project initialization tool.

Primary commands:
  init         Initialize .agents/ directory
  run          Run the MISRA fix pipeline (split→agent→merge)
  status       Show current pipeline run progress
  policy       Manage rule policy configuration
  doctor       Diagnose pipeline environment
  env-check    Check CLI installation

Advanced commands:
  split        Split cppcheck XML (use 'run --stage split')
  merge        Merge results (use 'run --stage merge')
  verify       Verify one chunk result
  bootstrap    Generate agent compatibility files
  validate     Provider validation test
  config       Manage CLI configuration
  upgrade      Upgrade .agents/ to a new version
  version      Show CLI and project version

Deprecated:
  oneshot      Use 'run' instead
"""
```

- [ ] **Step 5: Run tests**

Run: `python3 -m pytest tests/test_misra_pipeline_cli.py -v`
Expected: Tests for `run` and `oneshot` as pipeline commands will FAIL (they're no longer in PIPELINE_COMMANDS). Other tests should pass. This is expected — we'll fix the tests in Task 4.

- [ ] **Step 6: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): add run, status, oneshot subcommand definitions; remove run/oneshot from PIPELINE_COMMANDS"
```

---

### Task 3: 实现 cmd_run() 和 cmd_status()

**Files:**
- Modify: `cli/misra-pipeline-cli.py`

- [ ] **Step 1: 添加 cmd_run() 函数**

Add `cmd_run()` after `cmd_env_check()`. This function implements the full oneshot flow by dynamically importing helper functions from `oneshot.py`:

```python
def _import_oneshot_helpers():
    """Import helper functions from oneshot module."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)
    oneshot = importlib.import_module("oneshot")
    return oneshot


def cmd_run(args: argparse.Namespace) -> int:
    """Run the MISRA fix pipeline (split→agent→merge or single stage)."""
    oneshot = _import_oneshot_helpers()

    # --status: print progress and exit
    if args.status:
        return oneshot.print_status_summary()

    # --fresh and --resume are mutually exclusive
    if args.fresh and args.resume:
        print("[run] --fresh and --resume cannot be used together.", file=sys.stderr)
        return 2

    # Single-stage mode: dispatch directly
    if args.stage:
        stage_map = {
            "split": "split_cppcheck_xml",
            "agent": "run_fix_pipeline",
            "merge": "merge_results",
        }
        module_name = stage_map[args.stage]
        stage_args = []
        if args.stage == "split":
            if args.strategy:
                stage_args.extend(["--strategy", args.strategy])
            if args.run_id:
                stage_args.extend(["--run-id", args.run_id])
        elif args.stage == "agent":
            if args.strategy:
                stage_args.extend(["--strategy", args.strategy])
            if args.max_chunks is not None:
                stage_args.extend(["--max-chunks", str(args.max_chunks)])
            if args.retry_failed is not None:
                stage_args.extend(["--retry-failed", str(args.retry_failed)])
            for rule_id in args.rule_id:
                stage_args.extend(["--rule-id", rule_id])
            if args.misra_only:
                stage_args.append("--misra-only")
            if args.include_failed:
                stage_args.append("--include-failed")
            if args.verbose:
                stage_args.append("--verbose")

        provider = getattr(args, "provider", None)
        return _dispatch_pipeline_command(args.stage, stage_args, provider=provider) if args.stage != "agent" else _dispatch_pipeline_command("agent_dispatch", stage_args, provider=provider)

    # Full-flow mode: delegate to oneshot logic
    # Build a Namespace that oneshot.parse_args would produce
    oneshot_argv = []
    if args.fresh:
        oneshot_argv.append("--fresh")
    if args.resume:
        oneshot_argv.append("--resume")
    if args.strategy:
        oneshot_argv.extend(["--strategy", args.strategy])
    if args.run_id:
        oneshot_argv.extend(["--run-id", args.run_id])
    if args.max_chunks is not None:
        oneshot_argv.extend(["--max-chunks", str(args.max_chunks)])
    if args.retry_failed is not None:
        oneshot_argv.extend(["--retry-failed", str(args.retry_failed)])
    for rule_id in args.rule_id:
        oneshot_argv.extend(["--rule-id", rule_id])
    if args.misra_only:
        oneshot_argv.append("--misra-only")
    if args.include_failed:
        oneshot_argv.append("--include-failed")
    if args.dry_run:
        oneshot_argv.append("--dry-run")

    # Set provider env var if specified
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
    try:
        if getattr(args, "provider", None):
            os.environ["PIPELINE_AGENT_PROVIDER"] = args.provider
        elif original_provider is not None:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
        return oneshot.main(oneshot_argv)
    finally:
        if original_provider is not None:
            os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
        else:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
```

Wait — the above approach has an issue with `--stage agent` not being in `PIPELINE_COMMANDS`. Let me reconsider. Since `run` is no longer in `PIPELINE_COMMANDS`, `_dispatch_pipeline_command` won't handle `agent_dispatch`. Better approach: for single-stage mode, call the module directly via `_call_module_main`.

Revised `cmd_run()`:

```python
def _import_oneshot_helpers():
    """Import oneshot module for helper functions."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)
    return importlib.import_module("oneshot")


def cmd_run(args: argparse.Namespace) -> int:
    """Run the MISRA fix pipeline (split→agent→merge or single stage)."""
    oneshot = _import_oneshot_helpers()

    # --status: print progress and exit
    if args.status:
        return oneshot.print_status_summary()

    # --fresh and --resume are mutually exclusive
    if args.fresh and args.resume:
        print("[run] --fresh and --resume cannot be used together.", file=sys.stderr)
        return 2

    # Single-stage mode: dispatch to a specific module
    if args.stage:
        stage_module_map = {
            "split": "split_cppcheck_xml",
            "agent": "run_fix_pipeline",
            "merge": "merge_results",
        }
        module_name = stage_module_map[args.stage]
        stage_args = []
        if args.stage == "split":
            if args.strategy:
                stage_args.extend(["--strategy", args.strategy])
            if args.run_id:
                stage_args.extend(["--run-id", args.run_id])
        elif args.stage == "agent":
            if args.strategy:
                stage_args.extend(["--strategy", args.strategy])
            if args.max_chunks is not None:
                stage_args.extend(["--max-chunks", str(args.max_chunks)])
            if args.retry_failed is not None:
                stage_args.extend(["--retry-failed", str(args.retry_failed)])
            for rule_id in args.rule_id:
                stage_args.extend(["--rule-id", rule_id])
            if args.misra_only:
                stage_args.append("--misra-only")
            if args.include_failed:
                stage_args.append("--include-failed")
            if args.verbose:
                stage_args.append("--verbose")

        # Import and call the module
        tools_dir = Path.cwd() / ".agents" / "tools"
        tools_dir_str = str(tools_dir.resolve())
        if tools_dir_str not in sys.path:
            sys.path.insert(0, tools_dir_str)
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            print(f"Error: Failed to import module '{module_name}': {exc}", file=sys.stderr)
            return 1

        # Set provider env var
        provider = getattr(args, "provider", None)
        original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
        try:
            if provider:
                os.environ["PIPELINE_AGENT_PROVIDER"] = provider
            elif original_provider is not None:
                os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

            original_argv = sys.argv
            try:
                sys.argv = [f"{module_name}.py", *stage_args]
                return _call_module_main(module, stage_args)
            except Exception as exc:
                print(f"Error running {args.stage}: {exc}", file=sys.stderr)
                return 1
            finally:
                sys.argv = original_argv
        finally:
            if original_provider is not None:
                os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
            else:
                os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

    # Full-flow mode: delegate to oneshot
    oneshot_argv = []
    if args.fresh:
        oneshot_argv.append("--fresh")
    if args.resume:
        oneshot_argv.append("--resume")
    if args.strategy:
        oneshot_argv.extend(["--strategy", args.strategy])
    if args.run_id:
        oneshot_argv.extend(["--run-id", args.run_id])
    if args.max_chunks is not None:
        oneshot_argv.extend(["--max-chunks", str(args.max_chunks)])
    if args.retry_failed is not None:
        oneshot_argv.extend(["--retry-failed", str(args.retry_failed)])
    for rule_id in args.rule_id:
        oneshot_argv.extend(["--rule-id", rule_id])
    if args.misra_only:
        oneshot_argv.append("--misra-only")
    if args.include_failed:
        oneshot_argv.append("--include-failed")
    if args.dry_run:
        oneshot_argv.append("--dry-run")
    if getattr(args, "verbose", False):
        oneshot_argv.append("--verbose")

    provider = getattr(args, "provider", None)
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
    try:
        if provider:
            os.environ["PIPELINE_AGENT_PROVIDER"] = provider
        elif original_provider is not None:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
        return oneshot.main(oneshot_argv)
    finally:
        if original_provider is not None:
            os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
        else:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)


def cmd_status(args: argparse.Namespace) -> int:
    """Show current pipeline run progress."""
    oneshot = _import_oneshot_helpers()
    return oneshot.print_status_summary()
```

- [ ] **Step 2: 更新 main() 分发逻辑**

Update `main()` to route the new commands:

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
    elif args.subcommand == "run":
        return cmd_run(args)
    elif args.subcommand == "status":
        return cmd_status(args)
    elif args.subcommand == "oneshot":
        print("'oneshot' has been merged into 'run'. Use 'misra-pipeline run' instead.", file=sys.stderr)
        return 1
    elif args.subcommand in PIPELINE_COMMANDS:
        provider = getattr(args, "provider", None)
        return _dispatch_pipeline_command(args.subcommand, args.args, provider=provider)
    elif args.subcommand == "policy":
        return _dispatch_policy_command(args.policy_args)

    return 0
```

- [ ] **Step 3: Run tests to verify compilation**

Run: `python3 -c "import importlib.util; spec = importlib.util.spec_from_file_location('m', 'cli/misra-pipeline-cli.py'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('OK')"`
Expected: OK

- [ ] **Step 4: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): implement cmd_run() and cmd_status() with oneshot delegation"
```

---

### Task 4: 更新测试

**Files:**
- Modify: `tests/test_misra_pipeline_cli.py`

- [ ] **Step 1: 修复因 PIPELINE_COMMANDS 变动而失败的测试**

Remove or update tests that reference `run` or `oneshot` as PIPELINE_COMMANDS entries:
- `test_parse_args_run_subcommand` — now tests the explicit `run` subparser with its own args
- `test_parse_args_oneshot_subcommand` — update to test `oneshot` deprecated alias
- Remove `test_parse_args_split_subcommand` and `test_parse_args_merge_subcommand` args checks if they relied on REMAINDER forwarding for run/oneshot specifically (they should still work for split/merge/verify etc.)

Update `test_parse_args_run_subcommand` to verify the new explicit args:

```python
def test_parse_args_run_subcommand(self):
    """Test parse_args for 'run' subcommand with explicit args."""
    args = misra_pipeline_cli.parse_args(["run", "--dry-run"])
    self.assertEqual(args.subcommand, "run")
    self.assertTrue(args.dry_run)
    self.assertIsNone(args.stage)

def test_parse_args_run_with_stage(self):
    """Test parse_args for 'run --stage split'."""
    args = misra_pipeline_cli.parse_args(["run", "--stage", "split"])
    self.assertEqual(args.subcommand, "run")
    self.assertEqual(args.stage, "split")

def test_parse_args_run_with_strategy(self):
    """Test parse_args for 'run --strategy conservative'."""
    args = misra_pipeline_cli.parse_args(["run", "--strategy", "conservative"])
    self.assertEqual(args.subcommand, "run")
    self.assertEqual(args.strategy, "conservative")

def test_parse_args_status_subcommand(self):
    """Test parse_args for 'status' subcommand."""
    args = misra_pipeline_cli.parse_args(["status"])
    self.assertEqual(args.subcommand, "status")

def test_parse_args_oneshot_deprecated(self):
    """Test parse_args for deprecated 'oneshot' subcommand."""
    args = misra_pipeline_cli.parse_args(["oneshot"])
    self.assertEqual(args.subcommand, "oneshot")
```

- [ ] **Step 2: 更新 dispatch 测试中引用 run/oneshot 的部分**

Since `run` is no longer in `PIPELINE_COMMANDS`, the `test_dispatch_calls_main_with_args` test that uses `"run"` needs adjustment. Change it to use `"split"` or `"doctor"` which remain in `PIPELINE_COMMANDS`.

- [ ] **Step 3: 添加 cmd_run 和 cmd_status 测试**

Add new test class `MisraPipelineRunTests` with tests for:
- `cmd_run --status` calls oneshot.print_status_summary
- `cmd_run --fresh --resume` returns error code 2
- `cmd_run --stage split` dispatches to split module
- `cmd_run --stage agent` dispatches to run_fix_pipeline module
- `cmd_run --dry-run` delegates to oneshot.main
- `cmd_status` calls oneshot.print_status_summary

All tests should use mock to avoid actually calling oneshot modules.

- [ ] **Step 4: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_misra_pipeline_cli.py
git commit -m "test(cli): update tests for run/status/oneshot subcommand changes"
```

---

### Task 5: 实现 policy init 交互式

**Files:**
- Modify: `.agents/tools/policy_init.py`

- [ ] **Step 1: 修改 init_policy() 添加交互式模板选择**

Modify the `init_policy()` function to add interactive selection when `templates` is empty and running in a TTY:

```python
def _select_template_interactive() -> List[str]:
    """Interactively select a template when none specified."""
    template_list = list(AVAILABLE_TEMPLATES.items())
    if not sys.stdin.isatty():
        default = template_list[0][0]
        print(f"Warning: No --template specified and not running in a terminal. Using default: '{default}'", file=sys.stderr)
        return [default]

    print("Available templates:\n")
    for i, (name, description) in enumerate(template_list, 1):
        print(f"  [{i}] {name:30s} - {description}")
    print()

    default_choice = "2"  # misra_c2012_relaxed
    while True:
        choice = input(f"Select template number [{default_choice}]: ").strip()
        if not choice:
            choice = default_choice
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(template_list):
                selected = template_list[idx][0]
                print(f"\nSelected: {selected}")
                return [selected]
        except ValueError:
            pass
        print(f"Invalid choice. Enter a number between 1 and {len(template_list)}.", file=sys.stderr)
```

Update the beginning of `init_policy()`:

```python
def init_policy(templates: List[str], output_path: Path, force: bool) -> int:
    """Initialize policy from one or more templates (merged)."""
    if not templates:
        templates = _select_template_interactive()
    # ... rest of function unchanged
```

- [ ] **Step 2: Run existing policy tests**

Run: `python3 -m pytest tests/ -q`
Expected: All tests pass (interactive selection only triggers when templates is empty and TTY)

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/policy_init.py
git commit -m "feat(policy): add interactive template selection for 'policy init'"
```

---

### Task 6: 集成测试和最终验证

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `python3 -m pytest tests/ -v`
Expected: All tests pass (240+)

- [ ] **Step 2: Verify CLI help output shows layered commands**

Run: `python3 cli/misra-pipeline-cli.py --help`
Expected: Output shows Primary and Advanced command sections

- [ ] **Step 3: Verify new commands parse correctly**

```bash
python3 cli/misra-pipeline-cli.py run --dry-run --strategy conservative --help
python3 cli/misra-pipeline-cli.py status --help
python3 cli/misra-pipeline-cli.py oneshot --help
```

Expected: `run` and `status` show proper help; `oneshot` shows deprecated message

- [ ] **Step 4: Verify oneshot deprecated alias**

Run: `python3 -c "import importlib.util; spec=importlib.util.spec_from_file_location('m','cli/misra-pipeline-cli.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(m.main(['oneshot']))"`
Expected: Prints deprecation message and returns 1

- [ ] **Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "test: final integration verification fixes"
```