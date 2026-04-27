"""Unit tests for misra_pipeline_cli.py module."""

import importlib.util
import unittest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
CLI_FILE = REPO_ROOT / "cli" / "misra-pipeline-cli.py"

# Load the module directly from file path
spec = importlib.util.spec_from_file_location("misra_pipeline_cli", CLI_FILE)
misra_pipeline_cli = importlib.util.module_from_spec(spec)
sys.modules["misra_pipeline_cli"] = misra_pipeline_cli
spec.loader.exec_module(misra_pipeline_cli)


class MisraPipelineCliTests(unittest.TestCase):
    def test_cmd_version_shows_cli_version(self):
        """Test version command shows CLI version from VERSION file."""
        result = misra_pipeline_cli.cmd_version_mock()
        self.assertIn("CLI version:", result)
        self.assertIn("v0.1.0", result)

    def test_parse_args_version_subcommand(self):
        """Test parse_args for 'version' subcommand."""
        args = misra_pipeline_cli.parse_args(["version"])
        self.assertEqual(args.subcommand, "version")

    def test_parse_args_init_subcommand(self):
        """Test parse_args for 'init' subcommand."""
        args = misra_pipeline_cli.parse_args(["init"])
        self.assertEqual(args.subcommand, "init")
        self.assertFalse(args.force)
        self.assertIsNone(args.version)

    def test_parse_args_init_with_force(self):
        """Test parse_args for 'init --force'."""
        args = misra_pipeline_cli.parse_args(["init", "--force"])
        self.assertTrue(args.force)

    def test_parse_args_init_with_version(self):
        """Test parse_args for 'init --version vX.Y.Z'."""
        args = misra_pipeline_cli.parse_args(["init", "--version", "v1.2.3"])
        self.assertEqual(args.version, "v1.2.3")

    def test_parse_args_upgrade_subcommand(self):
        """Test parse_args for 'upgrade' subcommand."""
        args = misra_pipeline_cli.parse_args(["upgrade"])
        self.assertEqual(args.subcommand, "upgrade")

    def test_parse_args_doctor_subcommand(self):
        """Test parse_args for 'doctor' subcommand."""
        args = misra_pipeline_cli.parse_args(["doctor"])
        self.assertEqual(args.subcommand, "doctor")