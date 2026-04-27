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


class MisraPipelineDoctorTests(unittest.TestCase):
    def test_check_python_version_passes_on_38(self):
        """Test check_python_version passes on Python 3.8+."""
        result = misra_pipeline_cli.check_python_version()
        self.assertTrue(result)

    def test_check_cli_installed_fails_when_not_installed(self):
        """Test check_cli_installed fails when CLI not in ~/.misra-pipeline."""
        # Mock CLI_DIR to non-existent path
        original_cli_dir = misra_pipeline_cli.CLI_DIR
        misra_pipeline_cli.CLI_DIR = Path("/nonexistent/cli")
        result = misra_pipeline_cli.check_cli_installed()
        misra_pipeline_cli.CLI_DIR = original_cli_dir
        self.assertFalse(result)

    def test_check_git_available(self):
        """Test check_git_available returns bool."""
        result = misra_pipeline_cli.check_git_available()
        self.assertIsInstance(result, bool)

    def test_check_project_initialized_fails_without_agents(self):
        """Test check_project_initialized fails when .agents/ missing."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            result = misra_pipeline_cli.check_project_initialized_mock(Path(tmp))
            self.assertFalse(result)

    def test_check_project_initialized_passes_with_agents(self):
        """Test check_project_initialized passes when .agents/ exists."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            agents_dir = Path(tmp) / ".agents"
            agents_dir.mkdir()
            result = misra_pipeline_cli.check_project_initialized_mock(Path(tmp))
            self.assertTrue(result)