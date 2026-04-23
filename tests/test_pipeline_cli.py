from __future__ import annotations

import sys
import unittest
from pathlib import Path


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

    def test_parse_args_rejects_docter(self) -> None:
        with self.assertRaises(SystemExit):
            pipeline_cli.parse_args(["docter"])

    def test_parse_args_accepts_doctor(self) -> None:
        args = pipeline_cli.parse_args(["doctor"])

        self.assertEqual(args.command, "doctor")


if __name__ == "__main__":
    unittest.main()
