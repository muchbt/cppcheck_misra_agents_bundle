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

    def test_dry_run_prints_summary_and_exits_after_split(self) -> None:
        """--dry-run should print chunk summary after split without running agents."""
        stage_calls = []
        stdout = io.StringIO()
        chunks_dir = self.runtime_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        # Create mock chunk files
        common.save_json(chunks_dir / "chunk_001.json", {
            "chunk_index": 1,
            "issue_count": 5,
            "files": ["src/file1.c", "src/file2.c"],
            "contains_high_risk": False,
            "requires_review_after_fix_count": 0,
        })
        common.save_json(chunks_dir / "chunk_002.json", {
            "chunk_index": 2,
            "issue_count": 3,
            "files": ["src/file3.c"],
            "contains_high_risk": True,
            "requires_review_after_fix_count": 2,
        })
        common.save_json(self.runtime_dir / "progress.json", {
            "run_id": "20260424-001",
            "fix_strategy": "conservative",
            "total_chunks": 2,
            "status": "ready",
        })
        common.save_json(self.runtime_dir / "issues_master.json", [
            {"issue_key": "test:1:rule", "file": "src/file1.c"},
            {"issue_key": "test:2:rule", "file": "src/file2.c"},
            {"issue_key": "test:3:rule", "file": "src/file3.c"},
            {"issue_key": "test:4:rule", "file": "src/file3.c"},
            {"issue_key": "test:5:rule", "file": "src/file3.c"},
            {"issue_key": "test:6:rule", "file": "src/file3.c"},
            {"issue_key": "test:7:rule", "file": "src/file3.c"},
            {"issue_key": "test:8:rule", "file": "src/file3.c"},
        ])

        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "collect_precheck_results", return_value=self.ok_checks()
        ), patch.object(
            oneshot.doctor, "print_checks"
        ), patch.object(
            oneshot, "run_stage", side_effect=lambda stage, argv: stage_calls.append((stage, argv)) or 0
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--fresh", "--dry-run"])

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        # Should only have split stage, not run/merge
        self.assertEqual([name for name, _ in stage_calls], ["split"])
        # Should print dry-run summary
        self.assertIn("DRY-RUN PREVIEW", output)
        self.assertIn("total_issues: 8", output)
        self.assertIn("total_chunks: 2", output)
        self.assertIn("chunk_001: 5 issues, 2 file(s)", output)
        self.assertIn("chunk_002: 3 issues, 1 file(s)", output)
        self.assertIn("HIGH_RISK", output)
        self.assertIn("NEEDS_REVIEW:2", output)
        self.assertIn("DRY-RUN complete", output)
        self.assertIn("No agents were started", output)

    def test_dry_run_with_resume_mode_uses_existing_chunks(self) -> None:
        """--dry-run in resume mode should show existing chunks without re-splitting."""
        stage_calls = []
        stdout = io.StringIO()
        chunks_dir = self.runtime_dir / "chunks"
        chunks_dir.mkdir(parents=True, exist_ok=True)

        # Create existing runtime state
        common.save_json(chunks_dir / "chunk_001.json", {
            "chunk_index": 1,
            "issue_count": 2,
            "files": ["src/existing.c"],
            "contains_high_risk": False,
            "requires_review_after_fix_count": 0,
        })
        common.save_json(self.runtime_dir / "progress.json", {
            "run_id": "20260424-002",
            "fix_strategy": "conservative",
            "total_chunks": 1,
            "status": "ready",
            "completed_chunks": [],
        })
        common.save_json(self.runtime_dir / "issues_master.json", [
            {"issue_key": "test:1:rule", "file": "src/existing.c"},
            {"issue_key": "test:2:rule", "file": "src/existing.c"},
        ])

        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "collect_precheck_results", return_value=self.ok_checks()
        ), patch.object(
            oneshot.doctor, "print_checks"
        ), patch.object(
            oneshot, "run_stage", side_effect=lambda stage, argv: stage_calls.append((stage, argv)) or 0
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--dry-run"])

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        # Should not run any stages (resume mode doesn't run split, dry-run skips run/merge)
        self.assertEqual(stage_calls, [])
        # Should print dry-run summary from existing chunks
        self.assertIn("DRY-RUN PREVIEW", output)
        self.assertIn("total_issues: 2", output)
        self.assertIn("chunk_001: 2 issues, 1 file(s)", output)

    def test_status_with_no_progress_json(self) -> None:
        """--status should report no run record when progress.json doesn't exist."""
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--status"])

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("无运行记录", output)

    def test_status_shows_done_when_completed(self) -> None:
        """--status should show DONE when all chunks completed without failures."""
        self.write_progress("done", {
            "completed_chunks": [1, 2, 3],
            "failed_chunks": [],
            "total_chunks": 3,
        })
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "get_current_commit_sha", return_value="a5332505"
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--status"])

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("run_id: 20260423-001", output)
        self.assertIn("status: DONE", output)
        self.assertIn("progress: 3/3", output)
        self.assertIn("commit: a5332505", output)

    def test_status_shows_done_with_concerns_when_has_failed_chunks(self) -> None:
        """--status should show DONE_WITH_CONCERNS when done but has failed chunks."""
        self.write_progress("done", {
            "completed_chunks": [1, 2],
            "failed_chunks": [3],
            "total_chunks": 3,
        })
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--status"])

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("status: DONE_WITH_CONCERNS", output)
        self.assertIn("failed_chunks: 1", output)

    def test_status_shows_blocked_when_failed(self) -> None:
        """--status should show BLOCKED when status is failed."""
        self.write_progress("failed", {
            "completed_chunks": [1],
            "failed_chunks": [2],
            "total_chunks": 3,
        })
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--status"])

        output = stdout.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("status: BLOCKED", output)

    def test_status_shows_needs_context_for_unfinished_statuses(self) -> None:
        """--status should show NEEDS_CONTEXT for ready, running, partial."""
        for status in ("ready", "running", "partial"):
            with self.subTest(status=status):
                self.write_progress(status)
                stdout = io.StringIO()
                with patch.object(oneshot, "ROOT", self.root), patch.object(
                    oneshot, "RUNTIME_DIR", self.runtime_dir
                ), redirect_stdout(stdout):
                    rc = oneshot.main(["--status"])

                output = stdout.getvalue()
                self.assertEqual(rc, 0)
                self.assertIn("status: NEEDS_CONTEXT", output)

    def test_status_exits_early_without_running_other_stages(self) -> None:
        """--status should not run any pipeline stages, just print summary."""
        self.write_progress("ready")
        stage_calls = []
        stdout = io.StringIO()
        with patch.object(oneshot, "ROOT", self.root), patch.object(
            oneshot, "RUNTIME_DIR", self.runtime_dir
        ), patch.object(
            oneshot, "run_stage", side_effect=lambda stage, argv: stage_calls.append((stage, argv)) or 0
        ), redirect_stdout(stdout):
            rc = oneshot.main(["--status"])

        self.assertEqual(rc, 0)
        self.assertEqual(stage_calls, [])  # No stages should be called
        self.assertIn("--status 查询结果", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
