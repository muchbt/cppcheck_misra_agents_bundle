from __future__ import annotations

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
        self.assertEqual(pipeline_cli.COMMANDS["doctor"][0], "doctor")
        self.assertEqual(pipeline_cli.COMMANDS["oneshot"][0], "oneshot")

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


if __name__ == "__main__":
    unittest.main()
