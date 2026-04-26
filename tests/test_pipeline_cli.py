from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import pipeline_cli  # type: ignore  # noqa: E402


class PipelineCliTests(unittest.TestCase):
    def test_command_map_exposes_doctor_and_oneshot(self) -> None:
        self.assertIn("doctor", pipeline_cli.COMMANDS)
        self.assertIn("oneshot", pipeline_cli.COMMANDS)
        self.assertIn("validate-real", pipeline_cli.COMMANDS)
        self.assertEqual(pipeline_cli.COMMANDS["doctor"][0], "doctor")
        self.assertEqual(pipeline_cli.COMMANDS["oneshot"][0], "oneshot")
        self.assertEqual(pipeline_cli.COMMANDS["validate-real"][0], "validate_real")

    def test_main_dispatches_subcommand_args(self) -> None:
        seen = {}

        class FakeModule:
            def main(self) -> int:
                seen["argv"] = list(sys.argv)
                return 0

        with patch.object(pipeline_cli.importlib, "import_module", return_value=FakeModule()):
            with patch.object(sys, "argv", ["pipeline_cli.py", "doctor", "--dry-run"]):
                with self.assertRaises(SystemExit) as ctx:
                    pipeline_cli.main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(seen["argv"], ["doctor.py", "--dry-run"])

    def test_main_rejects_doctor_bogus_args(self) -> None:
        with patch.object(pipeline_cli.importlib, "import_module", return_value=__import__("doctor")):
            with patch.object(sys, "argv", ["pipeline_cli.py", "doctor", "--bogus"]):
                with self.assertRaises(SystemExit) as ctx:
                    pipeline_cli.main()

        self.assertNotEqual(ctx.exception.code, 0)

    def test_parse_args_rejects_docter(self) -> None:
        with self.assertRaises(SystemExit):
            pipeline_cli.parse_args(["docter"])

    def test_parse_args_accepts_doctor(self) -> None:
        args = pipeline_cli.parse_args(["doctor"])

        self.assertEqual(args.command, "doctor")

    def test_parse_args_accepts_validate_real(self) -> None:
        args = pipeline_cli.parse_args(["validate-real", "--provider", "claude"])

        self.assertEqual(args.command, "validate-real")
        self.assertEqual(args.args, ["--provider", "claude"])

    def test_parse_args_accepts_global_provider(self) -> None:
        args = pipeline_cli.parse_args(["--provider", "claude", "doctor"])

        self.assertEqual(args.provider, "claude")
        self.assertEqual(args.command, "doctor")
        self.assertEqual(args.args, [])

    def test_parse_args_rejects_invalid_provider(self) -> None:
        with self.assertRaises(SystemExit):
            pipeline_cli.parse_args(["--provider", "invalid", "doctor"])

    def test_parse_args_provider_choices(self) -> None:
        for provider in ["codex", "claude", "opencode", "kimi"]:
            args = pipeline_cli.parse_args(["--provider", provider, "doctor"])
            self.assertEqual(args.provider, provider)

    def test_parse_args_no_provider_default_none(self) -> None:
        args = pipeline_cli.parse_args(["doctor"])

        self.assertIsNone(args.provider)

    def test_main_sets_provider_env_var(self) -> None:
        seen_env = {}

        class FakeModule:
            def main(self) -> int:
                seen_env["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                return 0

        with patch.object(pipeline_cli.importlib, "import_module", return_value=FakeModule()):
            with patch.object(sys, "argv", ["pipeline_cli.py", "--provider", "claude", "doctor"]):
                with self.assertRaises(SystemExit) as ctx:
                    pipeline_cli.main()

        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(seen_env["provider"], "claude")

    def test_main_no_provider_does_not_set_env(self) -> None:
        seen_env = {}

        class FakeModule:
            def main(self) -> int:
                seen_env["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                return 0

        # Clear any existing value
        original = os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        try:
            with patch.object(pipeline_cli.importlib, "import_module", return_value=FakeModule()):
                with patch.object(sys, "argv", ["pipeline_cli.py", "doctor"]):
                    with self.assertRaises(SystemExit) as ctx:
                        pipeline_cli.main()
        finally:
            if original is not None:
                os.environ["PIPELINE_AGENT_PROVIDER"] = original

        self.assertEqual(ctx.exception.code, 0)
        self.assertIsNone(seen_env["provider"])

    def test_sequential_calls_clear_stale_provider_env(self) -> None:
        """Regression test: second call without --provider should not see stale env from first."""
        seen_env_first = {}
        seen_env_second = {}

        class FakeModuleFirst:
            def main(self) -> int:
                seen_env_first["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                return 0

        class FakeModuleSecond:
            def main(self) -> int:
                seen_env_second["provider"] = os.environ.get("PIPELINE_AGENT_PROVIDER")
                return 0

        # Ensure starting clean
        original = os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        try:
            # First call with --provider codex
            with patch.object(pipeline_cli.importlib, "import_module", return_value=FakeModuleFirst()):
                with patch.object(sys, "argv", ["pipeline_cli.py", "--provider", "codex", "doctor"]):
                    with self.assertRaises(SystemExit) as ctx1:
                        pipeline_cli.main()

            self.assertEqual(ctx1.exception.code, 0)
            self.assertEqual(seen_env_first["provider"], "codex")

            # Second call without --provider - should NOT see stale codex
            with patch.object(pipeline_cli.importlib, "import_module", return_value=FakeModuleSecond()):
                with patch.object(sys, "argv", ["pipeline_cli.py", "doctor"]):
                    with self.assertRaises(SystemExit) as ctx2:
                        pipeline_cli.main()

            self.assertEqual(ctx2.exception.code, 0)
            self.assertIsNone(seen_env_second["provider"])

            # Env var should remain unset after both calls
            self.assertIsNone(os.environ.get("PIPELINE_AGENT_PROVIDER"))
        finally:
            if original is not None:
                os.environ["PIPELINE_AGENT_PROVIDER"] = original


if __name__ == "__main__":
    unittest.main()
