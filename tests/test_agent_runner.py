from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402


class AgentConfigValidationTests(unittest.TestCase):
    def test_validate_pipeline_config_rejects_legacy_agent_command(self) -> None:
        config = {
            "project": {
                "runtime_dir": ".agents/runtime",
                "reports_dir": ".agents/reports",
                "chunks_dir": ".agents/runtime/chunks",
                "results_dir": ".agents/runtime/results",
            },
            "input": {"cppcheck_xml": "cppcheck.xml"},
            "chunking": {
                "max_issues_per_chunk": 12,
                "max_files_per_chunk": 3,
                "prefer_group_by_file": True,
                "split_high_risk_alone": True,
            },
            "filter": {
                "include_severity": ["error", "warning", "style"],
                "exclude_information": True,
            },
            "misra": {"enabled": True, "detect_prefixes": ["misra"]},
            "fix_strategy": {
                "mode": "conservative",
                "mark_high_risk_in_all_auto": True,
                "require_review_after_high_risk_fix": True,
            },
            "verification": {
                "mode": "light",
                "rerun_cppcheck_for_touched_files": False,
                "custom_command": "",
            },
            "agent": {"type": "codex", "command": "codex", "auto_bootstrap_compat": True},
        }

        errors, warnings = common.validate_pipeline_config(config)

        self.assertIn("agent.provider must be a non-empty string", errors)
        self.assertIn("agent.staging_dir must be a non-empty string", errors)
        self.assertIn("agent.launch.argv must be a non-empty list of strings", errors)
        self.assertEqual(warnings, [])

    def test_validate_pipeline_config_accepts_structured_agent(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})

        self.assertEqual(config["agent"]["provider"], "opencode")
        self.assertIn("opencode", config["agent"]["providers"])
        self.assertEqual(
            config["agent"]["providers"]["opencode"]["launch"]["argv"],
            ["opencode", "run", "--dangerously-skip-permissions"],
        )

        errors, warnings = common.validate_pipeline_config(config)

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


class CodexProviderTests(unittest.TestCase):
    def test_codex_provider_builds_non_interactive_launch_spec(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        config["agent"]["provider"] = "codex"
        chunk = {
            "chunk_index": 1,
            "fix_strategy": "conservative",
            "contains_high_risk": False,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            prompts_dir = root / "prompts"
            chunks_dir = runtime_dir / "chunks"
            staging_dir = root / ".agents" / "staging"
            runtime_dir.mkdir(parents=True)
            prompts_dir.mkdir(parents=True)
            chunks_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            (prompts_dir / "fix_chunk_prompt.txt").write_text(
                (
                    "Read chunk {chunk_index}\n"
                    "{issue_status_delta_path}\n"
                    "{file_change_delta_path}\n"
                    "{chunk_result_json_path}\n"
                    "{chunk_result_md_path}\n"
                    "{strategy_instructions}\n"
                ),
                encoding="utf-8",
            )
            (chunks_dir / "chunk_001.json").write_text(
                json.dumps(chunk),
                encoding="utf-8",
            )

            codex_provider = importlib.import_module("providers.codex")
            provider_base = importlib.import_module("providers.base")

            with patch.object(codex_provider, "RUNTIME_DIR", runtime_dir), patch.object(
                provider_base, "PROMPTS_DIR", prompts_dir
            ), patch.object(
                provider_base, "resolve_agent_staging_dir", return_value=staging_dir
            ):
                spec = codex_provider.build_launch_spec(config, chunk)

        self.assertEqual(spec["argv"][:3], ["codex", "exec", "--full-auto"])
        self.assertIn("--skip-git-repo-check", spec["argv"])
        add_dir_index = spec["argv"].index("--add-dir")
        self.assertEqual(spec["argv"][add_dir_index : add_dir_index + 2], ["--add-dir", str(staging_dir / "chunk_001")])
        self.assertEqual(spec["prompt_via"], "stdin")
        self.assertEqual(spec["cwd_mode"], "project_root")
        self.assertFalse(spec["requires_tty"])
        self.assertEqual(spec["output_mode"], "exit_code")
        self.assertIn("Read chunk 1", spec["prompt"])
        self.assertIn("Fix strategy: conservative.", spec["prompt"])
        self.assertIn(".agents/staging/chunk_001/issue_status_delta.json", spec["prompt"])
        self.assertIn(".agents/staging/chunk_001/file_change_delta.json", spec["prompt"])
        self.assertIn(".agents/staging/chunk_001/chunk_result.json", spec["prompt"])
        self.assertIn(".agents/staging/chunk_001/chunk_result.md", spec["prompt"])
        self.assertNotIn(".agents/runtime/results/chunk_001_result.json", spec["prompt"])
        self.assertEqual(spec["staging_dir"], str(staging_dir / "chunk_001"))


class ClaudeProviderTests(unittest.TestCase):
    def test_claude_provider_builds_non_interactive_launch_spec(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        config["agent"]["provider"] = "claude"
        config["agent"]["providers"]["claude"]["launch"]["argv"] = [
            "claude",
            "-p",
            "--output-format",
            "text",
            "--permission-mode",
            "acceptEdits",
        ]
        config["agent"]["providers"]["claude"]["launch"]["env"] = {}
        chunk = {
            "chunk_index": 1,
            "fix_strategy": "conservative",
            "contains_high_risk": False,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            prompts_dir = root / "prompts"
            chunks_dir = runtime_dir / "chunks"
            staging_dir = root / ".agents" / "staging"
            runtime_dir.mkdir(parents=True)
            prompts_dir.mkdir(parents=True)
            chunks_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            (prompts_dir / "fix_chunk_prompt.txt").write_text(
                "Read chunk {chunk_index}\n{chunk_result_json_path}\n{strategy_instructions}\n",
                encoding="utf-8",
            )
            (chunks_dir / "chunk_001.json").write_text(json.dumps(chunk), encoding="utf-8")

            claude_provider = importlib.import_module("providers.claude")
            provider_base = importlib.import_module("providers.base")
            with patch.object(claude_provider, "RUNTIME_DIR", runtime_dir), patch.object(
                provider_base, "PROMPTS_DIR", prompts_dir
            ), patch.object(
                provider_base, "resolve_agent_staging_dir", return_value=staging_dir
            ):
                spec = claude_provider.build_launch_spec(config, chunk)

        self.assertEqual(spec["argv"][0], "claude")
        self.assertEqual(spec["argv"][-1], "-p")
        self.assertIn("--add-dir", spec["argv"])
        self.assertIn(str(staging_dir / "chunk_001"), spec["argv"])
        self.assertIn("--append-system-prompt", spec["argv"])
        self.assertEqual(spec["prompt_via"], "arg")
        self.assertIn(".agents/staging/chunk_001/chunk_result.json", spec["prompt"])
        self.assertEqual(spec["staging_dir"], str(staging_dir / "chunk_001"))


class OpenCodeProviderTests(unittest.TestCase):
    def test_opencode_provider_import(self) -> None:
        """Test that opencode provider can be imported and has required attributes."""
        from providers import get_provider
        provider = get_provider("opencode")
        assert provider is not None
        assert hasattr(provider, "PROVIDER_NAME")
        assert provider.PROVIDER_NAME == "opencode"
        assert hasattr(provider, "SANITIZED_ENV_KEYS")
        assert hasattr(provider, "prepare_launch_env")
        assert hasattr(provider, "classify_runtime_error")
        assert hasattr(provider, "build_launch_spec")

    def test_opencode_classify_runtime_error(self) -> None:
        """Test opencode error classification."""
        from providers.opencode import classify_runtime_error
        # stderr only (old signature compatibility)
        assert classify_runtime_error("Authentication failed") == "auth_error"
        assert classify_runtime_error("Network timeout") == "network_error"
        assert classify_runtime_error("dial tcp: connect: connection refused") == "network_error"
        assert classify_runtime_error("POST https://opencode.ai/zen/v1/messages timed out") == "network_error"
        assert classify_runtime_error("Unknown error") == "runtime_error"
        # stdout + stderr combined (new signature)
        assert classify_runtime_error("", "POST https://opencode.ai/zen/v1/messages timed out") == "network_error"
        assert classify_runtime_error("stderr auth error", "stdout: credentials invalid") == "auth_error"

    def test_codex_classify_runtime_error(self) -> None:
        """Test codex error classification."""
        from providers.codex import classify_runtime_error
        # quota/usage limit errors
        assert classify_runtime_error("", "You've hit your usage limit") == "auth_error"
        assert classify_runtime_error("", "Please upgrade to Pro to continue") == "auth_error"
        assert classify_runtime_error("", "quota exceeded for this month") == "auth_error"
        # network errors
        assert classify_runtime_error("failed to connect to websocket") == "network_error"
        assert classify_runtime_error("", "stream disconnected before completion") == "network_error"
        # auth errors
        assert classify_runtime_error("auth: please login with codex auth login") == "auth_error"
        # runtime fallback
        assert classify_runtime_error("Unknown error") == "runtime_error"
        # stdout + stderr combined
        assert classify_runtime_error("stderr", "quota exceeded") == "auth_error"

    def test_claude_classify_runtime_error(self) -> None:
        """Test claude error classification."""
        from providers.claude import classify_runtime_error
        # auth errors
        assert classify_runtime_error("ANTHROPIC_API_KEY not set") == "auth_error"
        assert classify_runtime_error("authentication required") == "auth_error"
        assert classify_runtime_error("", "Please login with claude auth") == "auth_error"
        # rate limit
        assert classify_runtime_error("", "rate limit exceeded") == "auth_error"
        assert classify_runtime_error("", "HTTP 429 Too Many Requests") == "auth_error"
        # network errors
        assert classify_runtime_error("network error: connection refused") == "network_error"
        assert classify_runtime_error("", "operation timed out after 30s") == "network_error"
        # runtime fallback
        assert classify_runtime_error("Unknown error") == "runtime_error"
        # stdout + stderr combined
        assert classify_runtime_error("stderr", "ECONNREFUSED") == "network_error"

    def test_opencode_provider_builds_run_launch_spec(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        config["agent"]["provider"] = "opencode"
        chunk = {
            "chunk_index": 1,
            "fix_strategy": "conservative",
            "contains_high_risk": False,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            prompts_dir = root / "prompts"
            chunks_dir = runtime_dir / "chunks"
            staging_dir = root / ".agents" / "staging"
            runtime_dir.mkdir(parents=True)
            prompts_dir.mkdir(parents=True)
            chunks_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            (prompts_dir / "fix_chunk_prompt.txt").write_text(
                "Read chunk {chunk_index}\n{chunk_result_json_path}\n{strategy_instructions}\n",
                encoding="utf-8",
            )
            (chunks_dir / "chunk_001.json").write_text(json.dumps(chunk), encoding="utf-8")

            opencode_provider = importlib.import_module("providers.opencode")
            provider_base = importlib.import_module("providers.base")
            with patch.object(opencode_provider, "RUNTIME_DIR", runtime_dir), patch.object(
                provider_base, "PROMPTS_DIR", prompts_dir
            ), patch.object(
                provider_base, "resolve_agent_staging_dir", return_value=staging_dir
            ):
                spec = opencode_provider.build_launch_spec(config, chunk)

        self.assertEqual(spec["argv"][:2], ["opencode", "run"])
        self.assertNotIn("--add-dir", spec["argv"])
        self.assertEqual(spec["prompt_via"], "arg")
        self.assertEqual(spec["staging_dir"], str(staging_dir / "chunk_001"))


class AgentRunnerTests(unittest.TestCase):
    def test_run_chunk_agent_passes_prompt_via_stdin(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        chunk = {"chunk_index": 1}
        agent_runner = importlib.import_module("agent_runner")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging_dir = root / ".agents" / "staging" / "chunk_001"
            common.save_json(root / ".agents" / "runtime" / "issue_status.json", {})
            common.save_json(root / ".agents" / "runtime" / "file_change_index.json", {})

            def build_spec(current_config: dict, current_chunk: dict) -> dict:
                return {
                    "argv": ["codex", "exec", "--full-auto"],
                    "prompt_via": "stdin",
                    "cwd_mode": "project_root",
                    "env": {"CODEX_HOME": ".agents/runtime/agent-home"},
                    "requires_tty": False,
                    "output_mode": "exit_code",
                    "prompt": "prompt body",
                    "staging_dir": str(staging_dir),
                }

            def fake_run(*args, **kwargs):
                common.save_json(staging_dir / "issue_status_delta.json", {"issue-a": {"status": "fixed"}})
                common.save_json(staging_dir / "file_change_delta.json", {"src/a.c": {"edits": []}})
                common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 1})
                (staging_dir / "chunk_result.md").write_text("# chunk 1\n", encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="ok", stderr="")

            with patch.object(agent_runner, "ROOT", root), patch.object(
                agent_runner,
                "get_provider",
                return_value=SimpleNamespace(build_launch_spec=build_spec),
            ), patch.object(agent_runner.subprocess, "run", side_effect=fake_run) as run_mock:
                result = agent_runner.run_chunk_agent(config, chunk)
                kwargs = run_mock.call_args.kwargs
                imported_result = common.load_json(
                    root / ".agents" / "runtime" / "results" / "chunk_001_result.json",
                    {},
                )

            self.assertEqual(kwargs["input"], "prompt body")
            self.assertEqual(kwargs["text"], True)
            self.assertTrue(kwargs["capture_output"])
            self.assertEqual(kwargs["cwd"], str(root))
            self.assertEqual(
                kwargs["env"]["CODEX_HOME"],
                str(root / ".agents" / "runtime" / "agent-home"),
            )
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["error_kind"], "")
            self.assertEqual(imported_result, {"chunk_index": 1})
            self.assertEqual(
                result["imported_paths"]["chunk_result_json_path"],
                root / ".agents" / "runtime" / "results" / "chunk_001_result.json",
            )

    def test_run_chunk_agent_reports_import_error(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        chunk = {"chunk_index": 1}
        agent_runner = importlib.import_module("agent_runner")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging_dir = root / ".agents" / "staging" / "chunk_001"
            common.save_json(root / ".agents" / "runtime" / "issue_status.json", {})
            common.save_json(root / ".agents" / "runtime" / "file_change_index.json", {})

            with patch.object(
                agent_runner,
                "ROOT",
                root,
            ), patch.object(
                agent_runner,
                "get_provider",
                return_value=SimpleNamespace(
                    build_launch_spec=lambda current_config, current_chunk: {
                        "argv": ["codex", "exec", "--full-auto"],
                        "prompt_via": "stdin",
                        "cwd_mode": "project_root",
                        "env": {"CODEX_HOME": ".agents/runtime/agent-home"},
                        "requires_tty": False,
                        "output_mode": "exit_code",
                        "prompt": "prompt body",
                        "staging_dir": str(staging_dir),
                    }
                ),
            ), patch.object(agent_runner.subprocess, "run") as run_mock:
                run_mock.return_value = SimpleNamespace(returncode=0, stdout="ok", stderr="")
                result = agent_runner.run_chunk_agent(config, chunk)

        self.assertEqual(result["error_kind"], "import_error")
        self.assertIn("missing staging artifact", result["stderr"])

    def test_run_chunk_agent_reports_spawn_error(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        config["agent"]["provider"] = "codex"
        chunk = {"chunk_index": 1}
        agent_runner = importlib.import_module("agent_runner")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            staging_dir = root / ".agents" / "staging" / "chunk_001"

            with patch.object(
                agent_runner,
                "ROOT",
                root,
            ), patch.object(
                agent_runner,
                "get_provider",
                return_value=SimpleNamespace(
                    build_launch_spec=lambda current_config, current_chunk: {
                        "argv": ["codex", "exec", "--full-auto"],
                        "prompt_via": "stdin",
                        "cwd_mode": "project_root",
                        "env": {"CODEX_HOME": ".agents/runtime/agent-home"},
                        "requires_tty": False,
                        "output_mode": "exit_code",
                        "prompt": "prompt body",
                        "staging_dir": str(staging_dir),
                    }
                ),
            ), patch.object(agent_runner.subprocess, "run", side_effect=OSError("permission denied")):
                result = agent_runner.run_chunk_agent(config, chunk)

        self.assertEqual(result["error_kind"], "spawn_error")
        self.assertIn("permission denied", result["stderr"])

    def test_run_chunk_agent_bootstraps_codex_auth_into_workspace_home(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        chunk = {"chunk_index": 1}
        agent_runner = importlib.import_module("agent_runner")
        codex_provider = importlib.import_module("providers.codex")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fake_home = root / "home"
            shared_codex = fake_home / ".codex"
            workspace_codex = root / ".agents" / "runtime" / "agent-home"
            shared_codex.mkdir(parents=True)
            workspace_codex.mkdir(parents=True)
            (shared_codex / "auth.json").write_text('{"tokens": {}}', encoding="utf-8")
            (shared_codex / "config.toml").write_text("model = \"gpt-5.3-codex\"\n", encoding="utf-8")

            with patch.object(
                agent_runner,
                "ROOT",
                root,
            ), patch.object(
                agent_runner,
                "get_provider",
                return_value=codex_provider,
            ), patch.object(
                codex_provider.Path,
                "home",
                return_value=fake_home,
            ), patch.object(
                codex_provider,
                "build_launch_spec",
                return_value={
                    "argv": ["codex", "exec", "--full-auto"],
                    "prompt_via": "stdin",
                    "cwd_mode": "project_root",
                    "env": {"CODEX_HOME": ".agents/runtime/agent-home"},
                    "requires_tty": False,
                    "output_mode": "exit_code",
                    "prompt": "prompt body",
                    "staging_dir": str(root / ".agents" / "staging" / "chunk_001"),
                },
            ), patch.object(agent_runner.subprocess, "run") as run_mock:
                staging_dir = root / ".agents" / "staging" / "chunk_001"
                common.save_json(root / ".agents" / "runtime" / "issue_status.json", {})
                common.save_json(root / ".agents" / "runtime" / "file_change_index.json", {})

                def fake_run(*args, **kwargs):
                    common.save_json(staging_dir / "issue_status_delta.json", {})
                    common.save_json(staging_dir / "file_change_delta.json", {})
                    common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 1})
                    (staging_dir / "chunk_result.md").write_text("# chunk 1\n", encoding="utf-8")
                    return SimpleNamespace(returncode=0, stdout="ok", stderr="")

                run_mock.side_effect = fake_run
                result = agent_runner.run_chunk_agent(config, chunk)

            self.assertEqual(result["returncode"], 0)
            self.assertTrue((workspace_codex / "auth.json").exists())
            self.assertTrue((workspace_codex / "config.toml").exists())

    def test_build_launch_env_strips_inherited_network_disable_flag(self) -> None:
        agent_runner = importlib.import_module("agent_runner")
        codex_provider = importlib.import_module("providers.codex")

        with patch.dict(agent_runner.os.environ, {"CODEX_SANDBOX_NETWORK_DISABLED": "1"}, clear=False):
            env = agent_runner.build_launch_env({"CODEX_HOME": ".agents/runtime/agent-home"}, codex_provider)

        self.assertNotIn("CODEX_SANDBOX_NETWORK_DISABLED", env)

    def test_get_selected_agent_config_respects_env_provider(self) -> None:
        """Test that get_selected_agent_config respects env var override."""
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        original_provider = config["agent"]["provider"]

        # Use a different provider via env var
        different_provider = "codex" if original_provider != "codex" else "claude"

        with patch.dict(os.environ, {"PIPELINE_AGENT_PROVIDER": different_provider}, clear=False):
            reloaded_common = importlib.reload(common)
            result = reloaded_common.get_selected_agent_config(config)

        self.assertEqual(result["provider"], different_provider)
        # Verify the launch config comes from the correct provider
        expected_launch = config["agent"]["providers"][different_provider]["launch"]
        self.assertEqual(result["launch"], expected_launch)


class KimiProviderTests(unittest.TestCase):
    def test_kimi_provider_import(self) -> None:
        """Verify kimi provider can be imported and has required attributes."""
        from providers import get_provider, PROVIDERS
        provider = get_provider("kimi")
        self.assertIsNotNone(provider, "kimi provider should be discoverable")
        self.assertEqual(provider.PROVIDER_NAME, "kimi")
        self.assertIn("kimi", PROVIDERS, "kimi should be in PROVIDERS dict")
        self.assertTrue(hasattr(provider, "SANITIZED_ENV_KEYS"))
        self.assertTrue(hasattr(provider, "prepare_launch_env"))
        self.assertTrue(hasattr(provider, "classify_runtime_error"))
        self.assertTrue(hasattr(provider, "build_launch_spec"))

    def test_kimi_provider_builds_launch_spec(self) -> None:
        """Verify build_launch_spec produces correct argv with required flags."""
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        config["agent"]["provider"] = "kimi"
        chunk = {
            "chunk_index": 1,
            "fix_strategy": "conservative",
            "contains_high_risk": False,
        }

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            prompts_dir = root / "prompts"
            chunks_dir = runtime_dir / "chunks"
            staging_dir = root / ".agents" / "staging"
            runtime_dir.mkdir(parents=True)
            prompts_dir.mkdir(parents=True)
            chunks_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            (prompts_dir / "fix_chunk_prompt.txt").write_text(
                "Read chunk {chunk_index}\n{chunk_result_json_path}\n{strategy_instructions}\n",
                encoding="utf-8",
            )
            (chunks_dir / "chunk_001.json").write_text(json.dumps(chunk), encoding="utf-8")

            kimi_provider = importlib.import_module("providers.kimi")
            provider_base = importlib.import_module("providers.base")
            with patch.object(kimi_provider, "RUNTIME_DIR", runtime_dir), patch.object(
                provider_base, "PROMPTS_DIR", prompts_dir
            ), patch.object(
                provider_base, "resolve_agent_staging_dir", return_value=staging_dir
            ):
                spec = kimi_provider.build_launch_spec(config, chunk)

        self.assertEqual(spec["argv"][0], "kimi")
        self.assertIn("--print", spec["argv"])
        self.assertIn("--input-format", spec["argv"])
        self.assertIn("--output-format", spec["argv"])
        self.assertIn("--yolo", spec["argv"])
        self.assertEqual(spec["prompt_via"], "stdin")

    def test_kimi_classify_runtime_error_by_exit_code(self) -> None:
        """Verify classify_runtime_error uses exit codes correctly."""
        from providers.kimi import classify_runtime_error

        # Exit code 75 -> network_error
        assert classify_runtime_error("", "", returncode=75) == "network_error"

        # Exit code 1 + auth keywords -> auth_error
        assert classify_runtime_error("unauthorized access", "", returncode=1) == "auth_error"
        assert classify_runtime_error("", "login required", returncode=1) == "auth_error"
        assert classify_runtime_error("quota exhausted", "", returncode=1) == "auth_error"

        # Exit code 1 + no auth keywords -> runtime_error
        assert classify_runtime_error("some config error", "", returncode=1) == "runtime_error"

        # returncode=None -> text pattern fallback
        assert classify_runtime_error("auth error", "") == "auth_error"
        assert classify_runtime_error("timeout", "") == "network_error"
        assert classify_runtime_error("unknown error", "") == "runtime_error"


if __name__ == "__main__":
    unittest.main()
