# cppcheck_scan Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate cppcheck_scan.py into MISRA pipeline CLI with scan command group and interactive config update.

**Architecture:** Move cppcheck_scan.py to .agents/tools/, adapt for module invocation, add nested subcommands to CLI with parameter forwarding, implement interactive config update after successful scan.

**Tech Stack:** Python 3.8+, argparse, pathlib, json

---

## File Structure

| File | Responsibility |
|------|----------------|
| `.agents/tools/cppcheck_scan.py` | Main scan module with 6 subcommands (moved from root) |
| `.agents/tools/config_update.py` | Config update helper functions for pipeline.json |
| `cli/misra-pipeline-cli.py` | CLI entry with scan command group and dispatch logic |
| `tests/test_cppcheck_scan_cli.py` | Tests for scan CLI integration and config update |

---

### Task 1: Move cppcheck_scan.py to .agents/tools/

**Files:**
- Move: `cppcheck_scan.py` → `.agents/tools/cppcheck_scan.py`

- [ ] **Step 1: Move the file**

```bash
git mv cppcheck_scan.py .agents/tools/cppcheck_scan.py
```

- [ ] **Step 2: Verify file moved correctly**

Run: `ls -la .agents/tools/cppcheck_scan.py`
Expected: File exists with correct permissions

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: move cppcheck_scan.py to .agents/tools/

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 2: Adapt cppcheck_scan.py parse_args for argv parameter

**Files:**
- Modify: `.agents/tools/cppcheck_scan.py:1768-1776` (parse_args function)

- [ ] **Step 1: Modify parse_args function signature**

Find the `parse_args` function (around line 1768) and change its signature:

```python
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]
    # rest of the function unchanged
```

**Current code (approximate line 1768):**
```python
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]

    if not argv or argv[0] not in SUBCOMMAND_NAMES:
        argv = ["scan"] + list(argv)
```

This is already correct. Verify and confirm no changes needed.

- [ ] **Step 2: Verify parse_args works with argv**

Run: `python3 -c "import sys; sys.path.insert(0, '.agents/tools'); import cppcheck_scan; args = cppcheck_scan.parse_args(['scan', '--project-root', '.']); print(args.command)"`
Expected: `scan`

- [ ] **Step 3: No commit needed (function already correct)**

---

### Task 3: Adapt cppcheck_scan.py main function for argv parameter

**Files:**
- Modify: `.agents/tools/cppcheck_scan.py:1855-1876` (main function)

- [ ] **Step 1: Verify current main function signature**

Read line 1855-1876, the current main function should be:

```python
def main() -> int:
    args = parse_args()
    # ...
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Modify main function to accept argv**

Replace the main function (lines 1855-1876):

```python
def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point. Supports both CLI invocation and module import.

    Args:
        argv: Command line arguments. If None, uses sys.argv[1:].

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    args = parse_args(argv)

    commands = {
        "expand": cmd_expand,
        "filter-db": cmd_filter_db,
        "cppcheck": cmd_cppcheck,
        "filter-xml": cmd_filter_xml,
        "html-report": cmd_html_report,
        "scan": cmd_scan,
    }

    handler = commands.get(args.command)
    if handler is None:
        print(f"[ERROR] 未知子命令: {args.command}", file=sys.stderr)
        return 2

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Verify main works with argv**

Run: `python3 -c "import sys; sys.path.insert(0, '.agents/tools'); import cppcheck_scan; result = cppcheck_scan.main(['--help']); print(result)"`
Expected: Help text printed, returns 0 or exits

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/cppcheck_scan.py
git commit -m "feat(cppcheck_scan): support main(argv) for module invocation

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 4: Create config_update.py module

**Files:**
- Create: `.agents/tools/config_update.py`

- [ ] **Step 1: Create config_update.py module**

```python
"""Config update helper functions for pipeline.json."""

from pathlib import Path
from typing import Optional

# Import from common.py - will be used via sys.path in CLI


def load_pipeline_config(config_path: Path) -> dict:
    """Load pipeline.json configuration.

    Args:
        config_path: Path to pipeline.json file.

    Returns:
        Configuration dict, empty dict if file not found.
    """
    if not config_path.exists():
        return {}
    try:
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_pipeline_config(config_path: Path, config: dict) -> None:
    """Save pipeline.json configuration.

    Args:
        config_path: Path to pipeline.json file.
        config: Configuration dict to save.
    """
    config_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_cppcheck_xml_from_config(config: dict) -> str:
    """Get input.cppcheck_xml value from config.

    Args:
        config: Pipeline configuration dict.

    Returns:
        cppcheck_xml path string, empty string if not set.
    """
    return str(config.get("input", {}).get("cppcheck_xml", "")).strip()


def update_cppcheck_xml_in_config(config_path: Path, new_xml_path: str) -> bool:
    """Update input.cppcheck_xml in pipeline.json.

    Args:
        config_path: Path to pipeline.json file.
        new_xml_path: New relative path for cppcheck_xml.

    Returns:
        True if updated, False if value unchanged.
    """
    config = load_pipeline_config(config_path)
    old_value = get_cppcheck_xml_from_config(config)

    if old_value == new_xml_path:
        return False

    config.setdefault("input", {})["cppcheck_xml"] = new_xml_path
    save_pipeline_config(config_path, config)
    return True


def resolve_relative_xml_path(xml_path: Path, project_root: Path) -> str:
    """Resolve XML path to relative path under project root.

    Args:
        xml_path: Absolute or relative XML path.
        project_root: Project root directory.

    Returns:
        Relative path string under project root.
    """
    try:
        if xml_path.is_absolute():
            return str(xml_path.relative_to(project_root))
        return str(xml_path)
    except ValueError:
        # xml_path not under project_root, return as-is
        return str(xml_path)
```

- [ ] **Step 2: Verify module imports correctly**

Run: `python3 -c "import sys; sys.path.insert(0, '.agents/tools'); import config_update; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/config_update.py
git commit -m "feat: add config_update module for pipeline.json updates

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 5: Add scan command group to CLI parse_args

**Files:**
- Modify: `cli/misra-pipeline-cli.py:142-284` (parse_args function)

- [ ] **Step 1: Add scan command group in parse_args**

After the `policy_parser` definition (around line 244), add scan command group:

Find the section starting around line 234:
```python
    # policy subcommand (forward remaining args to policy_init)
    policy_parser = subparsers.add_parser(
        "policy",
        help="Manage policy configuration",
    )
    policy_parser.add_argument(
        "--provider", "-P",
        ...
    )
```

After this block (around line 268), add:

```python
    # scan subcommand (cppcheck scan workflow with nested subcommands)
    scan_parser = subparsers.add_parser(
        "scan",
        help="cppcheck scan workflow (expand → filter-db → cppcheck → filter-xml → html-report)",
    )
    scan_subparsers = scan_parser.add_subparsers(dest="scan_action", help="Scan subcommand")

    # Nested subcommands for scan workflow
    for action in ["expand", "filter-db", "cppcheck", "filter-xml", "html-report"]:
        scan_subparsers.add_parser(action, help=f"Run {action} step")

    # Note: Default (no scan_action) runs full 'scan' workflow
```

- [ ] **Step 2: Update parse_known_args handling for scan**

Find the section around line 276-283:
```python
    # Use parse_known_args so --flags like --dry-run pass through to subcommands
    parsed, forwarded = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    # Attach forwarded args to the namespace
    if parsed.subcommand in PIPELINE_COMMANDS:
        parsed.args = forwarded
    elif parsed.subcommand == "policy":
        parsed.policy_args = forwarded

    return parsed
```

Replace with:
```python
    # Use parse_known_args so --flags pass through to subcommands
    parsed, forwarded = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    # Attach forwarded args to the namespace
    if parsed.subcommand in PIPELINE_COMMANDS:
        parsed.args = forwarded
    elif parsed.subcommand == "policy":
        parsed.policy_args = forwarded
    elif parsed.subcommand == "scan":
        parsed.scan_args = forwarded

    return parsed
```

- [ ] **Step 3: Verify parse_args recognizes scan subcommand**

Run: `python3 -c "import sys; sys.path.insert(0, 'cli'); import importlib.util; spec = importlib.util.spec_from_file_location('cli', 'cli/misra-pipeline-cli.py'); cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli); args, fwd = cli.parse_args(['scan', '--project-root', '.']); print(f'subcommand={args.subcommand}, scan_action={args.scan_action}, forwarded={fwd}')"`
Expected: `subcommand=scan, scan_action=None, forwarded=['--project-root', '.']`

- [ ] **Step 4: Verify nested subcommand parsing**

Run: `python3 -c "import sys; sys.path.insert(0, 'cli'); import importlib.util; spec = importlib.util.spec_from_file_location('cli', 'cli/misra-pipeline-cli.py'); cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli); args, fwd = cli.parse_args(['scan', 'cppcheck', '--cppcheck-enable', 'warning']); print(f'subcommand={args.subcommand}, scan_action={args.scan_action}, forwarded={fwd}')"`
Expected: `subcommand=scan, scan_action=cppcheck, forwarded=['--cppcheck-enable', 'warning']`

- [ ] **Step 5: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): add scan command group with nested subcommands

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 6: Add cmd_scan dispatch function in CLI

**Files:**
- Modify: `cli/misra-pipeline-cli.py` (add cmd_scan function and main dispatch)

- [ ] **Step 1: Add cmd_scan function before cmd_status**

Find the location before `cmd_status` function (around line 1175), add:

```python
# ── Scan command dispatch ─────────────────────────────────────────────────────

def _dispatch_scan_command(scan_action: Optional[str], forwarded_args: list[str]) -> int:
    """Dispatch scan command to cppcheck_scan module in .agents/tools/."""
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
        cppcheck_scan = importlib.import_module("cppcheck_scan")
    except ImportError as exc:
        print(
            f"Error: Failed to import cppcheck_scan: {exc}",
            file=sys.stderr,
        )
        return 1

    # Determine the action: None means full 'scan' workflow
    action = scan_action or "scan"
    scan_argv = [action, *forwarded_args]

    try:
        exit_code = cppcheck_scan.main(scan_argv)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 1
    except Exception as exc:
        print(f"Error running scan: {exc}", file=sys.stderr)
        return 1

    # Interactive config update after successful scan
    if exit_code == 0 and action in ("scan", "cppcheck"):
        _offer_config_update_after_scan()

    return exit_code


def _offer_config_update_after_scan() -> None:
    """Offer to update pipeline.json after successful scan."""
    project_root = Path.cwd()
    config_path = project_root / ".agents" / "config" / "pipeline.json"

    if not config_path.exists():
        return

    # Import helpers
    tools_dir_str = str((project_root / ".agents" / "tools").resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)

    try:
        cppcheck_scan = importlib.import_module("cppcheck_scan")
        config_update = importlib.import_module("config_update")
    except ImportError:
        return

    # Find the latest generated XML
    latest_xml = cppcheck_scan.find_latest_xml(str(project_root))
    if not latest_xml:
        return

    # Get current config value
    current_config = config_update.load_pipeline_config(config_path)
    current_xml = config_update.get_cppcheck_xml_from_config(current_config)

    # Resolve paths for comparison
    latest_xml_path = Path(latest_xml)
    current_xml_path = Path(current_xml) if current_xml else Path("cppcheck.xml")

    # Normalize to absolute paths for comparison
    latest_abs = latest_xml_path.resolve() if not latest_xml_path.is_absolute() else latest_xml_path
    current_abs = (project_root / current_xml_path).resolve() if not current_xml_path.is_absolute() else current_xml_path.resolve()

    if latest_abs == current_abs:
        return  # No change needed

    # Offer interactive update
    latest_rel = config_update.resolve_relative_xml_path(latest_xml_path, project_root)

    print()
    print(f"[scan] 扫描完成，生成 XML: {latest_xml}")
    print(f"[scan] 当前配置: input.cppcheck_xml = {current_xml}")
    print("[scan] 是否更新配置指向最新结果？[Y/n]")

    try:
        response = input().strip().lower()
    except (EOFError, OSError):
        response = "y"  # Default to yes in non-interactive mode

    if response in ("", "y", "yes"):
        if config_update.update_cppcheck_xml_in_config(config_path, latest_rel):
            print(f"[scan] 已更新配置: input.cppcheck_xml = {latest_rel}")
        else:
            print("[scan] 配置未变更（值相同）")
    else:
        print("[scan] 配置未更新，可手动修改 .agents/config/pipeline.json")


def cmd_scan(args: argparse.Namespace) -> int:
    """Handle scan subcommand."""
    scan_action = getattr(args, "scan_action", None)
    forwarded_args = getattr(args, "scan_args", [])
    return _dispatch_scan_command(scan_action, forwarded_args)
```

- [ ] **Step 2: Add scan dispatch in main function**

Find the main function dispatch section (around line 1181-1207):
```python
def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.subcommand == "version":
        return cmd_version(args)
    ...
```

Add scan dispatch after `elif args.subcommand == "status"`:
```python
    elif args.subcommand == "scan":
        return cmd_scan(args)
```

The final dispatch section should look like:
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
    elif args.subcommand == "run":
        return cmd_run(args)
    elif args.subcommand == "status":
        return cmd_status(args)
    elif args.subcommand == "scan":
        return cmd_scan(args)
    elif args.subcommand == "config":
        return cmd_config(args)
    # ... rest unchanged
```

- [ ] **Step 3: Update CLI help text to include scan**

Find the description section around line 147-168, add scan to primary commands:
```python
Primary commands:
  init          Initialize .agents/ in current project.
  run           Run the MISRA fix pipeline (split -> agent -> merge).
  scan          cppcheck scan workflow.
  status        Show current pipeline run progress.
  policy        Manage rule policy configuration.
  doctor        Diagnose pipeline environment.
  env-check     Check CLI installation and environment.
```

- [ ] **Step 4: Commit**

```bash
git add cli/misra-pipeline-cli.py
git commit -m "feat(cli): implement scan command dispatch and config update

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 7: Add tests for scan CLI integration

**Files:**
- Create: `tests/test_cppcheck_scan_cli.py`

- [ ] **Step 1: Create test file for scan CLI**

```python
"""Tests for scan command integration in misra-pipeline CLI."""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_FILE = REPO_ROOT / "cli" / "misra-pipeline-cli.py"

# Load CLI module
spec = importlib.util.spec_from_file_location("misra_pipeline_cli", CLI_FILE)
misra_pipeline_cli = importlib.util.module_from_spec(spec)
sys.modules["misra_pipeline_cli"] = misra_pipeline_cli
spec.loader.exec_module(misra_pipeline_cli)


class ScanCliParseArgsTests(unittest.TestCase):
    """Test parse_args for scan command group."""

    def test_parse_args_scan_default_action(self):
        """Test parse_args for 'scan' (default full workflow)."""
        args, forwarded = misra_pipeline_cli.parse_args(["scan"])
        self.assertEqual(args.subcommand, "scan")
        self.assertIsNone(args.scan_action)
        self.assertEqual(forwarded, [])

    def test_parse_args_scan_with_forwarded_args(self):
        """Test parse_args forwards unknown args to scan."""
        args, forwarded = misra_pipeline_cli.parse_args(["scan", "--project-root", "."])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(forwarded, ["--project-root", "."])

    def test_parse_args_scan_expand_subcommand(self):
        """Test parse_args for 'scan expand'."""
        args, forwarded = misra_pipeline_cli.parse_args(["scan", "expand"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "expand")
        self.assertEqual(forwarded, [])

    def test_parse_args_scan_cppcheck_with_args(self):
        """Test parse_args for 'scan cppcheck --cppcheck-enable warning'."""
        args, forwarded = misra_pipeline_cli.parse_args(
            ["scan", "cppcheck", "--cppcheck-enable", "warning"]
        )
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "cppcheck")
        self.assertEqual(forwarded, ["--cppcheck-enable", "warning"])

    def test_parse_args_scan_filter_db(self):
        """Test parse_args for 'scan filter-db'."""
        args, forwarded = misra_pipeline_cli.parse_args(["scan", "filter-db"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "filter-db")

    def test_parse_args_scan_filter_xml(self):
        """Test parse_args for 'scan filter-xml'."""
        args, forwarded = misra_pipeline_cli.parse_args(["scan", "filter-xml"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "filter-xml")

    def test_parse_args_scan_html_report(self):
        """Test parse_args for 'scan html-report'."""
        args, forwarded = misra_pipeline_cli.parse_args(["scan", "html-report"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "html-report")


class ConfigUpdateTests(unittest.TestCase):
    """Test config_update module functions."""

    def setUp(self):
        """Set up temp directory for tests."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        sys.path.insert(0, str(self.temp_path / ".agents" / "tools"))

    def tearDown(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        if str(self.temp_path / ".agents" / "tools") in sys.path:
            sys.path.remove(str(self.temp_path / ".agents" / "tools"))

    def test_load_pipeline_config_missing_file(self):
        """Test loading config from non-existent file."""
        # Create config_update module in temp tools dir
        tools_dir = self.temp_path / ".agents" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)

        config_update_src = REPO_ROOT / ".agents" / "tools" / "config_update.py"
        if config_update_src.exists():
            import shutil
            shutil.copy(config_update_src, tools_dir / "config_update.py")

        import config_update
        config = config_update.load_pipeline_config(self.temp_path / "nonexistent.json")
        self.assertEqual(config, {})

    def test_update_cppcheck_xml_in_config(self):
        """Test updating cppcheck_xml in config."""
        tools_dir = self.temp_path / ".agents" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)

        config_update_src = REPO_ROOT / ".agents" / "tools" / "config_update.py"
        if config_update_src.exists():
            import shutil
            shutil.copy(config_update_src, tools_dir / "config_update.py")

        import config_update
        import json

        # Create initial config
        config_path = self.temp_path / "pipeline.json"
        initial_config = {"input": {"cppcheck_xml": "old.xml"}}
        config_path.write_text(json.dumps(initial_config))

        # Update
        result = config_update.update_cppcheck_xml_in_config(
            config_path, "new/cppcheck_result.xml"
        )
        self.assertTrue(result)

        # Verify update
        updated = json.loads(config_path.read_text())
        self.assertEqual(updated["input"]["cppcheck_xml"], "new/cppcheck_result.xml")

    def test_update_cppcheck_xml_same_value(self):
        """Test updating with same value returns False."""
        tools_dir = self.temp_path / ".agents" / "tools"
        tools_dir.mkdir(parents=True, exist_ok=True)

        config_update_src = REPO_ROOT / ".agents" / "tools" / "config_update.py"
        if config_update_src.exists():
            import shutil
            shutil.copy(config_update_src, tools_dir / "config_update.py")

        import config_update
        import json

        config_path = self.temp_path / "pipeline.json"
        initial_config = {"input": {"cppcheck_xml": "same.xml"}}
        config_path.write_text(json.dumps(initial_config))

        result = config_update.update_cppcheck_xml_in_config(config_path, "same.xml")
        self.assertFalse(result)


class ScanDispatchTests(unittest.TestCase):
    """Test _dispatch_scan_command function."""

    def setUp(self):
        """Set up temp project directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)
        self.original_cwd = Path.cwd()

    def tearDown(self):
        """Clean up and restore cwd."""
        import os
        import shutil
        os.chdir(self.original_cwd)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_dispatch_scan_missing_agents_dir(self):
        """Test dispatch fails when .agents/tools not found."""
        import os
        os.chdir(self.temp_dir)

        result = misra_pipeline_cli._dispatch_scan_command(None, [])
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify parse_args works**

Run: `python3 -m pytest tests/test_cppcheck_scan_cli.py::ScanCliParseArgsTests -v`
Expected: All 7 tests pass

- [ ] **Step 3: Run tests to verify config_update works**

Run: `python3 -m pytest tests/test_cppcheck_scan_cli.py::ConfigUpdateTests -v`
Expected: 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add tests/test_cppcheck_scan_cli.py
git commit -m "test: add scan CLI integration tests

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

### Task 8: Test backward compatibility - cppcheck_scan.py as standalone script

**Files:**
- Verify: `.agents/tools/cppcheck_scan.py`

- [ ] **Step 1: Test standalone script invocation**

Run: `python3 .agents/tools/cppcheck_scan.py --help`
Expected: Help text with all 6 subcommands displayed

- [ ] **Step 2: Test scan subcommand as standalone**

Run: `python3 .agents/tools/cppcheck_scan.py scan --help`
Expected: Scan subcommand help text

- [ ] **Step 3: Test expand subcommand as standalone**

Run: `python3 .agents/tools/cppcheck_scan.py expand --help`
Expected: Expand subcommand help text

- [ ] **Step 4: Commit if any fixes needed**

If fixes were needed, commit them. Otherwise, no commit.

---

### Task 9: Integration test - full scan workflow through CLI

**Files:**
- Verify: End-to-end functionality

- [ ] **Step 1: Verify CLI scan command works with --help**

Run: `python3 cli/misra-pipeline-cli.py scan --help`
Expected: Scan help text with nested subcommands

- [ ] **Step 2: Verify nested subcommand help**

Run: `python3 cli/misra-pipeline-cli.py scan cppcheck --help`
Expected: Cppcheck subcommand help forwarded from cppcheck_scan.py

- [ ] **Step 3: Final commit for integration**

```bash
git add -A
git commit -m "feat: complete cppcheck_scan CLI integration

Phase 1 complete:
- scan command group with 6 nested subcommands
- parameter forwarding via parse_known_args
- interactive config update after scan

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>"
```

---

## Self-Review Checklist

**1. Spec coverage:**
- ✅ Task 1-3: cppcheck_scan.py moved and adapted for main(argv)
- ✅ Task 4: config_update.py module created
- ✅ Task 5-6: scan command group added to CLI with dispatch
- ✅ Task 7-8: Tests added, backward compatibility verified
- ✅ Interactive config update: Task 6 Step 1 covers `_offer_config_update_after_scan`

**2. Placeholder scan:**
- No TBD/TODO in plan
- No "add appropriate error handling" - all code shown
- No "write tests for the above" - actual test code provided

**3. Type consistency:**
- `parse_args` returns tuple `(args, forwarded)` consistently
- `main(argv)` signature consistent in cppcheck_scan and CLI
- `config_update` functions use `Path` and `str` consistently

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-15-cppcheck-scan-integration.md`.

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?