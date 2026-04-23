from __future__ import annotations

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402
import oneshot  # type: ignore  # noqa: E402


class OneshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.runtime_dir = self.root / ".agents" / "runtime"
        self.results_dir = self.runtime_dir / "results"
        self.runtime_dir.mkdir(parents=True)
        self.results_dir.mkdir(parents=True)

    def write_progress(self, status: str, extra: Optional[Dict[str, object]] = None) -> None:
        payload = {
            "run_id": "20260423-001",
            "total_chunks": 3,
            "completed_chunks": [1],
            "failed_chunks": [],
            "current_chunk": 2,
            "fix_strategy": "conservative",
            "status": status,
        }
        if extra:
            payload.update(extra)
        common.save_json(self.runtime_dir / "progress.json", payload)

    def ok_checks(self) -> List[Dict[str, str]]:
        return [
            {"level": "ok", "code": "python_version", "message": "ok", "detail": ""},
            {"level": "ok", "code": "pipeline_config_ok", "message": "ok", "detail": ""},
        ]

    def test_oneshot_defaults_to_resume_for_unfinished_statuses(self) -> None:
        for status in ("ready", "running", "partial", "failed"):
            with self.subTest(status=status):
                self.write_progress(status)
                stage_calls = []
                stdout = io.StringIO()
                with patch.object(oneshot, "ROOT", self.root), patch.object(
                    oneshot, "RUNTIME_DIR", self.runtime_dir
                ), patch.object(
                    oneshot, "collect_precheck_results", return_value=self.ok_checks()
                ), patch.object(
                    oneshot.doctor, "print_checks"
                ), patch.object(
                    oneshot, "run_stage", side_effect=lambda stage, argv: stage_calls.append((stage, argv)) or 0
                ), redirect_stdout(stdout):
                    rc = oneshot.main([])

                self.assertEqual(rc, 0)
                self.assertEqual([name for name, _ in stage_calls], ["run", "merge"])
                self.assertIn("默认继续执行", stdout.getvalue())

    def test_oneshot_fresh_runs_split_first(self) -> None:
        stage_calls = []
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "collect_precheck_results", return_value=self.ok_checks()
        ), patch.object(
            oneshot.doctor, "print_checks"
        ), patch.object(
            oneshot, "run_stage", side_effect=lambda stage, argv: stage_calls.append((stage, list(argv))) or 0
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--fresh", "--strategy", "all_auto", "--run-id", "20260423-010"])

        self.assertEqual(rc, 0)
        self.assertEqual([name for name, _ in stage_calls], ["split", "run", "merge"])
        self.assertEqual(stage_calls[0][1], ["--strategy", "all_auto", "--run-id", "20260423-010"])

    def test_resume_mode_does_not_delete_existing_chunk_results(self) -> None:
        self.write_progress("ready")
        result_path = self.results_dir / "chunk_001_result.json"
        result_path.write_text("keep-me", encoding="utf-8")

        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "collect_precheck_results", return_value=self.ok_checks()
        ), patch.object(
            oneshot.doctor, "print_checks"
        ), patch.object(
            oneshot, "run_stage", return_value=0
        ):
            rc = oneshot.main([])

        self.assertEqual(rc, 0)
        self.assertEqual(result_path.read_text(encoding="utf-8"), "keep-me")

    def test_resume_rejects_conflicting_strategy(self) -> None:
        self.write_progress("ready", {"fix_strategy": "conservative"})
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--strategy", "all_auto"])

        self.assertEqual(rc, 2)
        self.assertIn("--fresh --strategy all_auto", stdout.getvalue())

    def test_run_id_is_rejected_for_resume_when_it_differs(self) -> None:
        self.write_progress("ready", {"run_id": "20260423-003"})
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--run-id", "20260423-099"])

        self.assertEqual(rc, 2)
        self.assertIn("run_id 冲突", stdout.getvalue())

    def test_run_id_is_accepted_for_fresh(self) -> None:
        stage_calls = []
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "collect_precheck_results", return_value=self.ok_checks()
        ), patch.object(
            oneshot.doctor, "print_checks"
        ), patch.object(
            oneshot, "run_stage", side_effect=lambda stage, argv: stage_calls.append((stage, list(argv))) or 0
        ):
            rc = oneshot.main(["--fresh", "--run-id", "20260423-123"])

        self.assertEqual(rc, 0)
        self.assertEqual(stage_calls[0], ("split", ["--run-id", "20260423-123"]))


if __name__ == "__main__":
    unittest.main()
