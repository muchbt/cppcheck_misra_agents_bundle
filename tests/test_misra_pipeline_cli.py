"""Unit tests for misra_pipeline_cli.py module."""

import importlib.util
import tempfile
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
        self.assertIn("v0.2.0", result)

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

    def test_parse_args_init_with_source(self):
        """Test parse_args for 'init --source release'."""
        args = misra_pipeline_cli.parse_args(["init", "--source", "release"])
        self.assertEqual(args.source, "release")

    def test_parse_args_init_with_url(self):
        """Test parse_args for 'init --url http://example.com/archive.tar.gz'."""
        args = misra_pipeline_cli.parse_args(["init", "--url", "http://example.com/archive.tar.gz"])
        self.assertEqual(args.url, "http://example.com/archive.tar.gz")

    def test_parse_args_upgrade_with_source_and_url(self):
        """Test parse_args for 'upgrade --source direct --url ...'."""
        args = misra_pipeline_cli.parse_args(["upgrade", "--source", "direct", "--url", "file:///tmp/agents.tar.gz"])
        self.assertEqual(args.source, "direct")
        self.assertEqual(args.url, "file:///tmp/agents.tar.gz")

    def test_parse_args_config_show(self):
        """Test parse_args for 'config show' subcommand."""
        args = misra_pipeline_cli.parse_args(["config", "show"])
        self.assertEqual(args.subcommand, "config")
        self.assertEqual(args.config_action, "show")

    def test_parse_args_config_set(self):
        """Test parse_args for 'config set mode release'."""
        args = misra_pipeline_cli.parse_args(["config", "set", "mode", "release"])
        self.assertEqual(args.config_action, "set")
        self.assertEqual(args.key, "mode")
        self.assertEqual(args.value, "release")

    def test_parse_args_config_reset(self):
        """Test parse_args for 'config reset'."""
        args = misra_pipeline_cli.parse_args(["config", "reset"])
        self.assertEqual(args.config_action, "reset")
        self.assertFalse(args.yes)

    def test_parse_args_config_reset_yes(self):
        """Test parse_args for 'config reset --yes'."""
        args = misra_pipeline_cli.parse_args(["config", "reset", "--yes"])
        self.assertTrue(args.yes)


class MisraPipelineConfigTests(unittest.TestCase):
    def test_user_config_defaults(self):
        """Test UserConfig has correct default values."""
        config = misra_pipeline_cli.UserConfig()
        self.assertEqual(config.download_mode, "release")
        self.assertEqual(config.fallback_mode, "git_clone")
        self.assertEqual(config.repo_url, misra_pipeline_cli.DEFAULT_REPO_URL)
        self.assertIn("{version}", config.url_template)

    def test_user_config_from_dict(self):
        """Test UserConfig loads from dictionary."""
        data = {
            "repo_url": "https://gitlab.com/example/repo",
            "download": {
                "mode": "direct",
                "url_template": "https://my-server.com/{version}.tar.gz",
                "fallback_mode": "local",
            },
        }
        config = misra_pipeline_cli.UserConfig(data)
        self.assertEqual(config.download_mode, "direct")
        self.assertEqual(config.repo_url, "https://gitlab.com/example/repo")
        self.assertEqual(config.url_template, "https://my-server.com/{version}.tar.gz")
        self.assertEqual(config.fallback_mode, "local")

    def test_user_config_resolve_url(self):
        """Test UserConfig.resolve_url substitutes version variable."""
        config = misra_pipeline_cli.UserConfig()
        url = config.resolve_url("v1.2.3")
        self.assertIn("v1.2.3", url)
        self.assertIn(misra_pipeline_cli.DEFAULT_REPO_URL, url)

    def test_user_config_to_dict_roundtrip(self):
        """Test UserConfig serializes and deserializes correctly."""
        original = misra_pipeline_cli.UserConfig({
            "repo_url": "https://example.com/repo",
            "download": {"mode": "local", "url_template": "/tmp/{version}.tar.gz", "fallback_mode": "git_archive"},
        })
        data = original.to_dict()
        restored = misra_pipeline_cli.UserConfig(data)
        self.assertEqual(original.download_mode, restored.download_mode)
        self.assertEqual(original.repo_url, restored.repo_url)
        self.assertEqual(original.url_template, restored.url_template)

    def test_load_user_config_missing_file(self):
        """Test load_user_config returns defaults when file missing."""
        original_config_file = misra_pipeline_cli.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            misra_pipeline_cli.CONFIG_FILE = Path(tmp) / "nonexistent.json"
            config = misra_pipeline_cli.load_user_config()
            self.assertEqual(config.download_mode, "release")
            misra_pipeline_cli.CONFIG_FILE = original_config_file

    def test_save_and_load_user_config(self):
        """Test save_user_config and load_user_config roundtrip."""
        original_config_file = misra_pipeline_cli.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            misra_pipeline_cli.CONFIG_FILE = Path(tmp) / "config.json"
            config = misra_pipeline_cli.UserConfig({
                "repo_url": "https://custom.example.com/repo",
                "download": {"mode": "direct", "url_template": "https://custom.example.com/{version}.zip"},
            })
            misra_pipeline_cli.save_user_config(config)
            loaded = misra_pipeline_cli.load_user_config()
            self.assertEqual(loaded.repo_url, "https://custom.example.com/repo")
            self.assertEqual(loaded.download_mode, "direct")
            misra_pipeline_cli.CONFIG_FILE = original_config_file

    def test_cmd_config_show(self):
        """Test config show command outputs valid JSON."""
        import json
        original_config_file = misra_pipeline_cli.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            misra_pipeline_cli.CONFIG_FILE = Path(tmp) / "config.json"
            args = misra_pipeline_cli.parse_args(["config", "show"])
            result = misra_pipeline_cli.cmd_config(args)
            self.assertEqual(result, 0)
            misra_pipeline_cli.CONFIG_FILE = original_config_file

    def test_cmd_config_set(self):
        """Test config set command updates configuration."""
        original_config_file = misra_pipeline_cli.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            misra_pipeline_cli.CONFIG_FILE = Path(tmp) / "config.json"
            args = misra_pipeline_cli.parse_args(["config", "set", "mode", "git_archive"])
            result = misra_pipeline_cli.cmd_config(args)
            self.assertEqual(result, 0)
            loaded = misra_pipeline_cli.load_user_config()
            self.assertEqual(loaded.download_mode, "git_archive")
            misra_pipeline_cli.CONFIG_FILE = original_config_file

    def test_cmd_config_reset(self):
        """Test config reset --yes command resets configuration."""
        original_config_file = misra_pipeline_cli.CONFIG_FILE
        with tempfile.TemporaryDirectory() as tmp:
            misra_pipeline_cli.CONFIG_FILE = Path(tmp) / "config.json"
            # First set a custom value
            misra_pipeline_cli.save_user_config(misra_pipeline_cli.UserConfig({
                "download": {"mode": "local"},
            }))
            args = misra_pipeline_cli.parse_args(["config", "reset", "--yes"])
            result = misra_pipeline_cli.cmd_config(args)
            self.assertEqual(result, 0)
            loaded = misra_pipeline_cli.load_user_config()
            self.assertEqual(loaded.download_mode, "release")
            misra_pipeline_cli.CONFIG_FILE = original_config_file


class MisraPipelineDownloadTests(unittest.TestCase):
    def test_download_from_local_directory(self):
        """Test download_from_local with a directory source."""
        with tempfile.TemporaryDirectory() as src_tmp:
            with tempfile.TemporaryDirectory() as dst_tmp:
                source_dir = Path(src_tmp) / ".agents"
                source_dir.mkdir()
                (source_dir / "tools").mkdir()
                (source_dir / "tools" / "test.py").write_text("test")

                target = Path(dst_tmp) / ".agents"
                result = misra_pipeline_cli.download_from_local(src_tmp, target, ".agents")
                self.assertTrue(result)
                self.assertTrue((target / "tools" / "test.py").exists())

    def test_download_from_local_archive(self):
        """Test download_from_local with a tar.gz archive."""
        import tarfile
        with tempfile.TemporaryDirectory() as src_tmp:
            with tempfile.TemporaryDirectory() as dst_tmp:
                # Create source directory structure inside a nested folder
                # to simulate release archive layout: agents-v1.0.0/.agents/...
                source_dir = Path(src_tmp) / "agents-v1.0.0" / ".agents"
                source_dir.mkdir(parents=True)
                (source_dir / "config").mkdir()
                (source_dir / "config" / "pipeline.json").write_text('{}')

                # Create tar.gz archive with nested folder
                archive_path = Path(src_tmp) / "agents.tar.gz"
                with tarfile.open(archive_path, "w:gz") as tar:
                    tar.add(Path(src_tmp) / "agents-v1.0.0", arcname="agents-v1.0.0")

                target = Path(dst_tmp) / ".agents"
                result = misra_pipeline_cli.download_from_local(str(archive_path), target, ".agents")
                self.assertTrue(result)
                self.assertTrue((target / "config" / "pipeline.json").exists())

    def test_download_from_local_missing_path(self):
        """Test download_from_local fails with non-existent path."""
        with tempfile.TemporaryDirectory() as dst_tmp:
            target = Path(dst_tmp) / ".agents"
            result = misra_pipeline_cli.download_from_local("/nonexistent/path", target)
            self.assertFalse(result)

    def test_download_from_local_unsupported_file(self):
        """Test download_from_local fails with unsupported file type."""
        with tempfile.TemporaryDirectory() as src_tmp:
            with tempfile.TemporaryDirectory() as dst_tmp:
                txt_file = Path(src_tmp) / "file.txt"
                txt_file.write_text("not an archive")
                target = Path(dst_tmp) / ".agents"
                result = misra_pipeline_cli.download_from_local(str(txt_file), target)
                self.assertFalse(result)

    def test_download_agents_with_local_mode(self):
        """Test download_agents with local mode and explicit path."""
        with tempfile.TemporaryDirectory() as src_tmp:
            with tempfile.TemporaryDirectory() as dst_tmp:
                source_dir = Path(src_tmp) / ".agents"
                source_dir.mkdir()
                (source_dir / "tools").mkdir()
                (source_dir / "tools" / "tool.py").write_text("tool")

                target = Path(dst_tmp) / ".agents"
                result = misra_pipeline_cli.download_agents(
                    target, "v1.0.0", ".agents", mode="local", url=src_tmp
                )
                self.assertTrue(result)
                self.assertTrue((target / "tools" / "tool.py").exists())


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
