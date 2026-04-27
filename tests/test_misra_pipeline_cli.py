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


class MisraPipelineInitTests(unittest.TestCase):
    def test_init_checks_target_exists(self):
        """Test init fails when .agents/ already exists without --force."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ".agents"
            target.mkdir()

            # Mock cwd to tmp
            args = misra_pipeline_cli.parse_args(["init"])
            result = misra_pipeline_cli.cmd_init_mock(args, Path(tmp))
            self.assertEqual(result, 1)  # Should fail

    def test_init_force_overwrites(self):
        """Test init --force succeeds when .agents/ exists."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / ".agents"
            target.mkdir()

            args = misra_pipeline_cli.parse_args(["init", "--force"])
            result = misra_pipeline_cli.cmd_init_mock(args, Path(tmp))
            self.assertEqual(result, 0)  # Should succeed

    def test_init_creates_version_file(self):
        """Test init creates .agents-version file."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            args = misra_pipeline_cli.parse_args(["init"])
            result = misra_pipeline_cli.cmd_init_mock(args, Path(tmp))
            self.assertEqual(result, 0)

            version_file = Path(tmp) / ".agents" / ".agents-version"
            self.assertTrue(version_file.exists())

            version_info = misra_pipeline_cli.read_version_file(version_file)
            self.assertIn("tag", version_info)
            self.assertIn("installed_at", version_info)


class MisraPipelineUpgradeTests(unittest.TestCase):
    def test_upgrade_fails_without_agents(self):
        """Test upgrade fails when .agents/ not found."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            args = misra_pipeline_cli.parse_args(["upgrade"])
            result = misra_pipeline_cli.cmd_upgrade_mock(args, Path(tmp))
            self.assertEqual(result, 1)

    def test_upgrade_detects_local_modifications(self):
        """Test upgrade fails when local modifications detected."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # Create .agents with version file
            agents_dir = Path(tmp) / ".agents"
            agents_dir.mkdir()
            (agents_dir / "tools").mkdir()
            # Create a modified file
            modified_file = agents_dir / "tools" / "modified.py"
            modified_file.write_text("modified content")

            version_file = agents_dir / ".agents-version"
            misra_pipeline_cli.write_version_file(version_file, "v1.0.0", "original-commit")

            # Simulate modification by checking file hash mismatch
            args = misra_pipeline_cli.parse_args(["upgrade"])
            result = misra_pipeline_cli.cmd_upgrade_mock(args, Path(tmp))
            # Should fail because we detect modifications
            self.assertEqual(result, 1)

    def test_upgrade_updates_version_file(self):
        """Test upgrade updates .agents-version to new version."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            # Create clean .agents
            agents_dir = Path(tmp) / ".agents"
            agents_dir.mkdir()
            (agents_dir / "tools").mkdir()
            (agents_dir / "config").mkdir()
            (agents_dir / "config" / "templates").mkdir()

            version_file = agents_dir / ".agents-version"
            misra_pipeline_cli.write_version_file(version_file, "v1.0.0", "commit-1")

            args = misra_pipeline_cli.parse_args(["upgrade", "--version", "v1.1.0"])
            result = misra_pipeline_cli.cmd_upgrade_mock_clean(args, Path(tmp))
            self.assertEqual(result, 0)

            new_version = misra_pipeline_cli.read_version_file(version_file)
            self.assertEqual(new_version.get("tag"), "v1.1.0")