from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402
import merge_results  # type: ignore  # noqa: E402


class ReportsArchiveTests(unittest.TestCase):
    def test_merge_results_writes_chinese_reports_manifest_and_archive(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / ".agents" / "runtime"
            reports_dir = root / ".agents" / "reports"
            runs_dir = root / ".agents" / "runs"
            config_dir = root / ".agents" / "config"
            results_dir = runtime_dir / "results"

            config_dir.mkdir(parents=True)
            results_dir.mkdir(parents=True)

            common.save_json(
                config_dir / "pipeline.json",
                {
                    "input": {"cppcheck_xml": "cppcheck.xml"},
                    "verification": {"custom_command": "", "mode": "light"},
                },
            )
            common.save_json(
                runtime_dir / "progress.json",
                {
                    "run_id": "20260423-002",
                    "started_at": "2026-04-23T10:00:00+08:00",
                    "last_chunk_finished_at": "2026-04-23T10:20:00+08:00",
                    "xml_file": "cppcheck.xml",
                    "fix_strategy": "conservative",
                    "total_chunks": 2,
                    "completed_chunks": [1],
                    "failed_chunks": [2],
                    "status": "failed",
                },
            )
            common.save_json(
                runtime_dir / "issue_status.json",
                {
                    "src/a.c:10:misra-c2012-1.1:aaa": {
                        "status": "fixed",
                        "file": "src/a.c",
                        "line": 10,
                        "rule_id": "misra-c2012-1.1",
                        "fix_strategy": "conservative",
                        "risk_level": "high",
                        "risk_reason": "可能影响控制流",
                        "requires_review_after_fix": True,
                        "edit_ids": ["src/a.c#001"],
                    },
                    "src/b.c:20:misra-c2012-2.1:bbb": {
                        "status": "needs_manual_review",
                        "file": "src/b.c",
                        "line": 20,
                        "rule_id": "misra-c2012-2.1",
                        "fix_strategy": "conservative",
                        "risk_level": "high",
                        "risk_reason": "涉及外设寄存器",
                        "requires_review_after_fix": False,
                        "edit_ids": [],
                    },
                    "src/c.c:30:nullPointer:ccc": {
                        "status": "failed",
                        "file": "src/c.c",
                        "line": 30,
                        "rule_id": "nullPointer",
                        "fix_strategy": "conservative",
                        "risk_level": "medium",
                        "risk_reason": "",
                        "requires_review_after_fix": False,
                        "edit_ids": [],
                    },
                },
            )
            common.save_json(
                runtime_dir / "file_change_index.json",
                {
                    "src/a.c": {
                        "edits": [
                            {
                                "edit_id": "src/a.c#001",
                                "summary": "增加空指针保护",
                                "chunk_index": 1,
                                "related_issue_keys": ["src/a.c:10:misra-c2012-1.1:aaa"],
                            }
                        ]
                    }
                },
            )
            common.save_json(
                results_dir / "chunk_001_result.json",
                {
                    "chunk_index": 1,
                    "verification": {
                        "performed": True,
                        "passed": True,
                        "mode": "light",
                        "notes": "light verification only; no custom command configured",
                        "command": "",
                        "returncode": 0,
                    },
                },
            )
            common.save_json(
                results_dir / "chunk_002_result.json",
                {
                    "chunk_index": 2,
                    "verification": {
                        "performed": True,
                        "passed": False,
                        "mode": "light",
                        "notes": "light verification only; no custom command configured",
                        "command": "",
                        "returncode": 1,
                    },
                },
            )
            (runtime_dir / "pipeline.log").write_text("pipeline log\n", encoding="utf-8")
            (runtime_dir / "run_log.jsonl").write_text("{\"event\": \"x\"}\n", encoding="utf-8")

            with patch.object(merge_results, "RUNTIME_DIR", runtime_dir), patch.object(
                merge_results, "REPORTS_DIR", reports_dir
            ), patch.object(
                merge_results, "RUNS_DIR", runs_dir
            ), patch.object(
                merge_results, "CONFIG_DIR", config_dir
            ), patch.object(
                merge_results, "now_iso", return_value="2026-04-23T10:30:00+08:00"
            ):
                rc = merge_results.main()

            self.assertEqual(rc, 0)

            summary_md = (reports_dir / "final_summary.md").read_text(encoding="utf-8")
            checklist_md = (reports_dir / "review_checklist.md").read_text(encoding="utf-8")
            manifest = common.load_json(reports_dir / "run_manifest.json", {})

            self.assertIn("需人工复核（needs manual review）", summary_md)
            self.assertIn("未执行工程级验证", summary_md)
            self.assertIn("轻量验证记录：通过 1，失败 1", summary_md)
            self.assertNotIn("工程级验证通过：", summary_md)
            self.assertIn("src/a.c:10:misra-c2012-1.1:aaa", checklist_md)
            self.assertIn("src/a.c#001", checklist_md)
            self.assertIn("src/b.c", checklist_md)
            self.assertEqual(manifest["run_id"], "20260423-002")
            self.assertEqual(manifest["started_at"], "2026-04-23T10:00:00+08:00")
            self.assertEqual(manifest["finished_at"], "2026-04-23T10:20:00+08:00")
            self.assertEqual(manifest["archived_at"], "2026-04-23T10:30:00+08:00")
            self.assertEqual(manifest["input_xml"], "cppcheck.xml")
            self.assertEqual(manifest["strategy"], "conservative")
            self.assertEqual(manifest["issue_counts"]["total"], 3)
            self.assertEqual(manifest["chunk_counts"]["total"], 2)
            self.assertEqual(manifest["report_paths"]["final_summary_md"], ".agents/reports/final_summary.md")

            archive_dir = runs_dir / "20260423-002"
            self.assertTrue((archive_dir / "runtime" / "progress.json").is_file())
            self.assertTrue((archive_dir / "reports" / "final_summary.md").is_file())
            self.assertTrue((archive_dir / "reports" / "review_checklist.md").is_file())
            self.assertTrue((archive_dir / "reports" / "run_manifest.json").is_file())
            self.assertTrue((archive_dir / "logs" / "pipeline.log").is_file())


if __name__ == "__main__":
    unittest.main()
