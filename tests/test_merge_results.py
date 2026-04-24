from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import merge_results  # type: ignore  # noqa: E402


class CountFileChangesTests(unittest.TestCase):
    def test_count_from_edits_list(self) -> None:
        file_data = {"edits": [{"edit_id": "a"}, {"edit_id": "b"}, {"edit_id": "c"}]}
        self.assertEqual(merge_results.count_file_changes(file_data), 3)

    def test_count_from_lines_fields(self) -> None:
        file_data = {
            "lines_added": [1, 2],
            "lines_removed": [3],
            "lines_changed": [4, 5, 6],
        }
        self.assertEqual(merge_results.count_file_changes(file_data), 6)

    def test_count_from_change_summary(self) -> None:
        file_data = {"change_summary": "added null check"}
        self.assertEqual(merge_results.count_file_changes(file_data), 1)

    def test_count_empty(self) -> None:
        self.assertEqual(merge_results.count_file_changes({}), 0)
        self.assertEqual(merge_results.count_file_changes({"edits": []}), 0)

    def test_edits_takes_precedence(self) -> None:
        file_data = {
            "edits": [{"edit_id": "a"}],
            "lines_added": [1, 2, 3],
            "lines_removed": [4],
        }
        self.assertEqual(merge_results.count_file_changes(file_data), 1)


class BuildReportPathsTests(unittest.TestCase):
    def test_returns_expected_paths(self) -> None:
        paths = merge_results.build_report_paths()
        self.assertEqual(paths["final_summary_md"], ".agents/reports/final_summary.md")
        self.assertEqual(paths["final_summary_json"], ".agents/reports/final_summary.json")
        self.assertEqual(paths["review_checklist_md"], ".agents/reports/review_checklist.md")
        self.assertEqual(paths["run_manifest_json"], ".agents/reports/run_manifest.json")


class CollectSummaryTests(unittest.TestCase):
    def test_basic_summary(self) -> None:
        issue_status = {
            "issue1": {"status": "fixed", "fix_strategy": "auto", "rule_id": "MISRA-C-2012:14.4", "file": "src/a.c"},
            "issue2": {"status": "skipped", "fix_strategy": "manual", "rule_id": "MISRA-C-2012:15.5", "file": "src/b.c"},
        }
        file_change_index = {"src/a.c": {"edits": [{"edit_id": "src/a.c#001"}]}}
        progress = {
            "run_id": "20260424-001",
            "started_at": "2026-04-24T10:00:00+08:00",
            "last_chunk_finished_at": "2026-04-24T10:30:00+08:00",
            "status": "completed",
            "xml_file": "input.xml",
            "fix_strategy": "conservative",
            "total_chunks": 2,
            "completed_chunks": [0, 1],
            "failed_chunks": [],
        }

        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime" / "results"
            runtime_dir.mkdir(parents=True)
            with patch.object(merge_results, "RUNTIME_DIR", Path(tmp) / "runtime"):
                summary = merge_results.collect_summary(issue_status, file_change_index, progress)

        self.assertEqual(summary["run_id"], "20260424-001")
        self.assertEqual(summary["started_at"], "2026-04-24T10:00:00+08:00")
        self.assertEqual(summary["finished_at"], "2026-04-24T10:30:00+08:00")
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["input_xml"], "input.xml")
        self.assertEqual(summary["strategy"], "conservative")
        self.assertEqual(summary["total_issues"], 2)
        self.assertEqual(summary["status_counts"]["fixed"], 1)
        self.assertEqual(summary["status_counts"]["skipped"], 1)
        self.assertEqual(summary["fixed_by_rule"]["MISRA-C-2012:14.4"], 1)
        self.assertEqual(summary["fixed_by_file"]["src/a.c"], 1)
        self.assertEqual(summary["touched_files"], ["src/a.c"])
        self.assertEqual(summary["chunk_counts"]["total"], 2)
        self.assertEqual(summary["chunk_counts"]["completed"], 2)
        self.assertEqual(summary["chunk_counts"]["failed"], 0)

    def test_high_risk_and_review_required(self) -> None:
        issue_status = {
            "issue1": {
                "status": "fixed",
                "fix_strategy": "auto",
                "rule_id": "MISRA-C-2012:14.4",
                "file": "src/a.c",
                "risk_level": "high",
                "requires_review_after_fix": True,
                "risk_reason": "null pointer dereference",
            },
        }
        file_change_index: dict = {}
        progress: dict = {"run_id": "test", "total_chunks": 1, "completed_chunks": [0], "failed_chunks": []}

        with patch.object(merge_results, "RUNTIME_DIR", Path("/nonexistent")):
            summary = merge_results.collect_summary(issue_status, file_change_index, progress)

        self.assertEqual(summary["fixed_high_risk_count"], 1)
        self.assertEqual(summary["review_required_after_fix_count"], 1)
        self.assertEqual(summary["fixed_high_risk"], ["issue1"])
        self.assertEqual(summary["review_required_after_fix"], ["issue1"])

    def test_verification_summary(self) -> None:
        issue_status: dict = {}
        file_change_index: dict = {}
        progress: dict = {}

        with tempfile.TemporaryDirectory() as tmp:
            results_dir = Path(tmp) / "runtime" / "results"
            results_dir.mkdir(parents=True)
            (results_dir / "chunk_001_result.json").write_text('{"verification": {"mode": "build", "passed": true}}\n', encoding="utf-8")
            (results_dir / "chunk_002_result.json").write_text('{"verification": {"mode": "build", "passed": false}}\n', encoding="utf-8")
            (results_dir / "chunk_003_result.json").write_text('{"verification": {"mode": "test", "passed": true, "command": "make test"}}\n', encoding="utf-8")

            with patch.object(merge_results, "RUNTIME_DIR", Path(tmp) / "runtime"):
                summary = merge_results.collect_summary(issue_status, file_change_index, progress)

        self.assertEqual(summary["verification"]["total"], 3)
        self.assertEqual(summary["verification"]["passed"], 2)
        self.assertEqual(summary["verification"]["failed"], 1)
        self.assertEqual(summary["verification"]["modes"]["build"], 2)
        self.assertEqual(summary["verification"]["modes"]["test"], 1)
        self.assertTrue(summary["verification"]["custom_command_ran"])


class BuildReviewMarkdownTests(unittest.TestCase):
    def test_basic_structure(self) -> None:
        summary = {
            "run_id": "20260424-001",
            "input_xml": "input.xml",
            "strategy": "conservative",
            "started_at": "2026-04-24T10:00:00+08:00",
            "finished_at": "2026-04-24T10:30:00+08:00",
            "status": "completed",
            "total_issues": 3,
            "status_counts": {"fixed": 2, "skipped": 1, "needs_manual_review": 0, "failed": 0},
            "chunk_counts": {"total": 1, "completed": 1, "failed": 0},
            "verification": {"total": 0, "passed": 0, "failed": 0, "custom_command_ran": False},
            "fixed_high_risk_count": 0,
            "review_required_after_fix_count": 0,
            "review_required_after_fix": [],
            "touched_files": ["src/a.c"],
        }
        issue_status: dict = {}
        file_change_index = {"src/a.c": {"edits": [{"edit_id": "src/a.c#001"}]}}

        md = merge_results.build_review_markdown(summary, issue_status, file_change_index)

        self.assertIn("# 运行总结", md)
        self.assertIn("运行编号：20260424-001", md)
        self.assertIn("输入 XML：input.xml", md)
        self.assertIn("修复策略：conservative", md)
        self.assertIn("## 问题汇总", md)
        self.assertIn("总问题数：3", md)
        self.assertIn("已修复：2", md)
        self.assertIn("已跳过：1", md)
        self.assertIn("## Chunk 汇总", md)
        self.assertIn("总 chunk 数：1", md)
        self.assertIn("## 验证汇总", md)
        self.assertIn("轻量验证记录", md)
        self.assertIn("## 修改文件", md)
        self.assertIn("src/a.c", md)
        self.assertIn("1 处修改", md)

    def test_custom_verification_display(self) -> None:
        summary = {
            "run_id": "test",
            "input_xml": "input.xml",
            "strategy": "conservative",
            "started_at": "2026-04-24T10:00:00+08:00",
            "finished_at": "2026-04-24T10:30:00+08:00",
            "status": "completed",
            "total_issues": 1,
            "status_counts": {"fixed": 1},
            "chunk_counts": {"total": 1, "completed": 1, "failed": 0},
            "verification": {"total": 2, "passed": 2, "failed": 0, "custom_command_ran": True, "modes": {"build": 2}},
            "fixed_high_risk_count": 0,
            "review_required_after_fix_count": 0,
            "review_required_after_fix": [],
            "touched_files": [],
        }
        issue_status: dict = {}
        file_change_index: dict = {}

        md = merge_results.build_review_markdown(summary, issue_status, file_change_index)

        self.assertIn("工程级验证通过：2", md)
        self.assertIn("工程级验证失败：0", md)
        self.assertIn("已执行；模式统计：build=2", md)

    def test_review_required_items(self) -> None:
        summary = {
            "run_id": "test",
            "input_xml": "input.xml",
            "strategy": "conservative",
            "started_at": "",
            "finished_at": "",
            "status": "",
            "total_issues": 1,
            "status_counts": {"fixed": 1},
            "chunk_counts": {"total": 0, "completed": 0, "failed": 0},
            "verification": {"total": 0, "passed": 0, "failed": 0, "custom_command_ran": False},
            "fixed_high_risk_count": 1,
            "review_required_after_fix_count": 1,
            "review_required_after_fix": ["issue1"],
            "touched_files": [],
        }
        issue_status = {
            "issue1": {
                "risk_reason": "null pointer risk",
                "file": "src/a.c",
                "rule_id": "MISRA-C-2012:14.4",
            }
        }
        file_change_index: dict = {}

        md = merge_results.build_review_markdown(summary, issue_status, file_change_index)

        self.assertIn("高风险已修复：1", md)
        self.assertIn("修复后仍需复核：1", md)
        self.assertIn("issue1：null pointer risk", md)
        self.assertIn("文件：src/a.c", md)
        self.assertIn("规则：MISRA-C-2012:14.4", md)


class BuildReviewChecklistTests(unittest.TestCase):
    def test_empty_checklist(self) -> None:
        summary = {
            "review_required_after_fix": [],
            "touched_files": [],
        }
        issue_status: dict = {}
        file_change_index: dict = {}

        checklist = merge_results.build_review_checklist(summary, issue_status, file_change_index)

        self.assertIn("# 人工复核清单", checklist)
        self.assertIn("| issue_key | 文件 | 规则 | 状态 | edit_ids | 复核原因 |", checklist)
        self.assertIn("本次没有需人工复核的条目", checklist)
        self.assertIn("没有记录到修改点", checklist)

    def test_review_required_after_fix(self) -> None:
        summary = {
            "review_required_after_fix": ["issue1"],
            "touched_files": [],
        }
        issue_status = {
            "issue1": {
                "status": "fixed",
                "file": "src/a.c",
                "rule_id": "MISRA-C-2012:14.4",
                "edit_ids": ["src/a.c#001"],
            }
        }
        file_change_index: dict = {}

        checklist = merge_results.build_review_checklist(summary, issue_status, file_change_index)

        self.assertIn("issue1", checklist)
        self.assertIn("src/a.c", checklist)
        self.assertIn("MISRA-C-2012:14.4", checklist)
        self.assertIn("修复后仍需人工确认", checklist)

    def test_needs_manual_review_items(self) -> None:
        summary: dict = {"review_required_after_fix": []}
        issue_status = {
            "issue1": {"status": "needs_manual_review", "file": "src/a.c", "rule_id": "R1", "risk_reason": "complex"},
            "issue2": {"status": "failed", "file": "src/b.c", "rule_id": "R2"},
            "issue3": {"status": "fixed", "file": "src/c.c", "rule_id": "R3"},
        }
        file_change_index: dict = {}

        checklist = merge_results.build_review_checklist(summary, issue_status, file_change_index)

        self.assertIn("issue1", checklist)
        self.assertIn("complex", checklist)
        self.assertIn("issue2", checklist)
        self.assertIn("未自动修复，需人工确认", checklist)
        self.assertNotIn("issue3", checklist)

    def test_file_change_index_display(self) -> None:
        summary: dict = {"review_required_after_fix": []}
        issue_status: dict = {}
        file_change_index = {
            "src/a.c": {
                "edits": [
                    {
                        "edit_id": "src/a.c#001",
                        "summary": "fix null pointer",
                        "chunk_index": 0,
                        "related_issue_keys": ["issue1", "issue2"],
                    }
                ]
            },
            "src/b.c": {"change_summary": "minor fix"},
        }

        checklist = merge_results.build_review_checklist(summary, issue_status, file_change_index)

        self.assertIn("文件：src/a.c", checklist)
        self.assertIn("src/a.c#001", checklist)
        self.assertIn("fix null pointer", checklist)
        self.assertIn("chunk=0", checklist)
        self.assertIn("issue1, issue2", checklist)
        self.assertIn("文件：src/b.c", checklist)
        self.assertIn("minor fix", checklist)


class WriteRunManifestTests(unittest.TestCase):
    def test_manifest_content(self) -> None:
        summary = {
            "run_id": "20260424-001",
            "started_at": "2026-04-24T10:00:00+08:00",
            "finished_at": "2026-04-24T10:30:00+08:00",
            "input_xml": "input.xml",
            "strategy": "conservative",
            "total_issues": 5,
            "status_counts": {"fixed": 3, "skipped": 1, "needs_manual_review": 1, "failed": 0},
            "chunk_counts": {"total": 2, "completed": 2, "failed": 0},
            "completed_chunks": [0, 1],
            "failed_chunks": [],
        }
        progress = {
            "started_at": "2026-04-24T10:00:00+08:00",
            "last_chunk_finished_at": "2026-04-24T10:30:00+08:00",
            "xml_file": "input.xml",
            "fix_strategy": "conservative",
        }

        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp) / "archive"
            reports_dir = archive_dir / "reports"
            reports_dir.mkdir(parents=True)

            manifest = merge_results.write_run_manifest(archive_dir, summary, progress)

            self.assertEqual(manifest["run_id"], "20260424-001")
            self.assertEqual(manifest["started_at"], "2026-04-24T10:00:00+08:00")
            self.assertEqual(manifest["finished_at"], "2026-04-24T10:30:00+08:00")
            self.assertEqual(manifest["input_xml"], "input.xml")
            self.assertEqual(manifest["strategy"], "conservative")
            self.assertEqual(manifest["issue_counts"]["total"], 5)
            self.assertEqual(manifest["issue_counts"]["fixed"], 3)
            self.assertEqual(manifest["issue_counts"]["skipped"], 1)
            self.assertEqual(manifest["issue_counts"]["needs_manual_review"], 1)
            self.assertEqual(manifest["issue_counts"]["failed"], 0)
            self.assertEqual(manifest["chunk_counts"]["total"], 2)
            self.assertEqual(manifest["completed_chunks"], [0, 1])
            self.assertEqual(manifest["failed_chunks"], [])
            self.assertIn("report_paths", manifest)

            manifest_path = reports_dir / "run_manifest.json"
            self.assertTrue(manifest_path.exists())


if __name__ == "__main__":
    unittest.main()