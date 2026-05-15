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
        args = misra_pipeline_cli.parse_args(["scan"])
        self.assertEqual(args.subcommand, "scan")
        self.assertIsNone(args.scan_action)
        self.assertEqual(args.scan_args, [])

    def test_parse_args_scan_with_forwarded_args(self):
        """Test parse_args forwards unknown args to scan subcommand."""
        args = misra_pipeline_cli.parse_args(["scan", "cppcheck", "--project-root", "."])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "cppcheck")
        self.assertEqual(args.scan_args, ["cppcheck", "--project-root", "."])

    def test_parse_args_scan_expand_subcommand(self):
        """Test parse_args for 'scan expand'."""
        args = misra_pipeline_cli.parse_args(["scan", "expand"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "expand")
        self.assertEqual(args.scan_args, ["expand"])

    def test_parse_args_scan_cppcheck_with_args(self):
        """Test parse_args for 'scan cppcheck --cppcheck-enable warning'."""
        args = misra_pipeline_cli.parse_args(
            ["scan", "cppcheck", "--cppcheck-enable", "warning"]
        )
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "cppcheck")
        self.assertEqual(args.scan_args, ["cppcheck", "--cppcheck-enable", "warning"])

    def test_parse_args_scan_filter_db(self):
        """Test parse_args for 'scan filter-db'."""
        args = misra_pipeline_cli.parse_args(["scan", "filter-db"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "filter-db")
        self.assertEqual(args.scan_args, ["filter-db"])

    def test_parse_args_scan_filter_xml(self):
        """Test parse_args for 'scan filter-xml'."""
        args = misra_pipeline_cli.parse_args(["scan", "filter-xml"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "filter-xml")
        self.assertEqual(args.scan_args, ["filter-xml"])

    def test_parse_args_scan_html_report(self):
        """Test parse_args for 'scan html-report'."""
        args = misra_pipeline_cli.parse_args(["scan", "html-report"])
        self.assertEqual(args.subcommand, "scan")
        self.assertEqual(args.scan_action, "html-report")
        self.assertEqual(args.scan_args, ["html-report"])


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

        result = misra_pipeline_cli._dispatch_scan_command([])
        self.assertEqual(result, 1)


if __name__ == "__main__":
    unittest.main()