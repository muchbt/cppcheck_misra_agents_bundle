"""Unit tests for misra_pipeline_cli.py module."""

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
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
        self.assertIn("v0.8.1", result)

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

    def test_parse_args_env_check_subcommand(self):
        """Test parse_args for 'env-check' subcommand."""
        args = misra_pipeline_cli.parse_args(["env-check"])
        self.assertEqual(args.subcommand, "env-check")

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

    def test_parse_args_split_subcommand(self):
        """Test parse_args for 'split' subcommand with forwarded args."""
        args = misra_pipeline_cli.parse_args(["split", "--input", "cppcheck.xml"])
        self.assertEqual(args.subcommand, "split")
        self.assertEqual(args.args, ["--input", "cppcheck.xml"])

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

    def test_parse_args_merge_subcommand(self):
        """Test parse_args for 'merge' subcommand."""
        args = misra_pipeline_cli.parse_args(["merge"])
        self.assertEqual(args.subcommand, "merge")

    def test_parse_args_verify_subcommand(self):
        """Test parse_args for 'verify' subcommand with positional args."""
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

    def test_parse_args_oneshot_deprecated(self):
        """Test parse_args for deprecated 'oneshot' subcommand."""
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
        """Test parse_args for 'policy' with forwarded args."""
        args = misra_pipeline_cli.parse_args(["policy", "init", "--template", "misra_c2012_relaxed"])
        self.assertEqual(args.subcommand, "policy")
        self.assertEqual(args.policy_args, ["init", "--template", "misra_c2012_relaxed"])

    def test_parse_args_rejects_invalid_subcommand(self):
        """Test that invalid subcommands are rejected."""
        with self.assertRaises(SystemExit):
            misra_pipeline_cli.parse_args(["invalid_command"])

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


class MisraPipelineEnvCheckTests(unittest.TestCase):
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


class MisraPipelineDispatchTests(unittest.TestCase):
    def test_dispatch_strips_leading_double_dash(self):
        """Test that _dispatch_pipeline_command handles forwarded args correctly."""
        seen = {}

        class FakeModuleWithArgs:
            def main(self, argv=None):
                seen["argv"] = argv
                seen["sys_argv"] = list(sys.argv)
                return 0

        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp) / ".agents" / "tools"
            tools_dir.mkdir(parents=True)
            with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleWithArgs()):
                    result = misra_pipeline_cli._dispatch_pipeline_command(
                        "split", ["--input", "test.xml"]
                    )

        self.assertEqual(result, 0)
        self.assertEqual(seen["argv"], ["--input", "test.xml"])
        self.assertEqual(seen["sys_argv"], ["split_cppcheck_xml.py", "--input", "test.xml"])

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
                        result = misra_pipeline_cli._dispatch_pipeline_command("split", [], provider="claude")

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

            with tempfile.TemporaryDirectory() as tmp:
                tools_dir = Path(tmp) / ".agents" / "tools"
                tools_dir.mkdir(parents=True)
                with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                    with patch.object(misra_pipeline_cli.importlib, "import_module", return_value=FakeModuleWithArgs()):
                        misra_pipeline_cli._dispatch_pipeline_command("split", [], provider="codex")

            self.assertEqual(os.environ.get("PIPELINE_AGENT_PROVIDER"), original)
        finally:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)


class MisraPipelineRunTests(unittest.TestCase):
    def setUp(self):
        self._cached_modules = {
            k: sys.modules[k]
            for k in list(sys.modules)
            if k in ("oneshot", "common", "doctor")
        }
        for k in self._cached_modules:
            sys.modules.pop(k, None)

    def tearDown(self):
        for k in ("oneshot", "common", "doctor"):
            sys.modules.pop(k, None)
        sys.modules.update(self._cached_modules)

    def test_run_fresh_resume_conflict(self):
        """Test that --fresh and --resume together returns error code 2."""
        args = misra_pipeline_cli.parse_args(["run", "--fresh", "--resume"])
        result = misra_pipeline_cli.cmd_run(args)
        self.assertEqual(result, 2)

    def test_run_stage_split_dispatches(self):
        """Test that --stage split dispatches to split_cppcheck_xml module."""
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp) / ".agents" / "tools"
            tools_dir.mkdir(parents=True)
            (tools_dir / "split_cppcheck_xml.py").write_text(
                "def main(argv=None):\n    return 0\n"
            )
            with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                args = misra_pipeline_cli.parse_args(["run", "--stage", "split", "--strategy", "conservative"])
                with patch.object(misra_pipeline_cli, "_call_module_main", return_value=0) as mock_call:
                    result = misra_pipeline_cli.cmd_run(args)
                    self.assertEqual(result, 0)
                    self.assertEqual(mock_call.call_args[0][1], ["--strategy", "conservative"])

    def test_cmd_status(self):
        """Test that cmd_status delegates to oneshot.print_status_summary."""
        with tempfile.TemporaryDirectory() as tmp:
            tools_dir = Path(tmp) / ".agents" / "tools"
            tools_dir.mkdir(parents=True)
            (tools_dir / "oneshot.py").write_text(
                "def print_status_summary(*a, **kw):\n    return 0\n"
                "def main(*a, **kw):\n    return 0\n"
            )
            (tools_dir / "common.py").write_text(
                "RUNTIME_DIR = None\nROOT = None\ndef load_json(*a, **kw): return {}\n"
                "def append_pipeline_event(*a, **kw): pass\n"
            )
            with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
                args = misra_pipeline_cli.parse_args(["status"])
                result = misra_pipeline_cli.cmd_status(args)
                self.assertEqual(result, 0)

    def test_oneshot_deprecated_message(self):
        """Test that 'oneshot' subcommand prints deprecation and returns 1."""
        result = misra_pipeline_cli.main(["oneshot"])
        self.assertEqual(result, 1)
