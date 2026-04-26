from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402


class AgentStagingConfigTests(unittest.TestCase):
    def test_validate_pipeline_config_requires_agent_staging_dir(self) -> None:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))
        config["agent"].pop("staging_dir")

        errors, warnings = common.validate_pipeline_config(config)

        self.assertIn("agent.staging_dir must be a non-empty string", errors)
        self.assertEqual(warnings, [])

    def test_resolve_agent_staging_dir_accepts_relative_path_under_project_root(self) -> None:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config["agent"]["staging_dir"] = ".agents/staging"

            staging_dir = common.resolve_agent_staging_dir(config, root=root)

        self.assertEqual(staging_dir, root / ".agents" / "staging")
        self.assertTrue(staging_dir.is_absolute())

    def test_resolve_agent_staging_dir_rejects_path_outside_project_root(self) -> None:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config["agent"]["staging_dir"] = "../outside"

            with self.assertRaisesRegex(ValueError, "project root"):
                common.resolve_agent_staging_dir(config, root=root)

    def test_import_chunk_staging_artifacts_merges_runtime_state_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / ".agents" / "runtime"
            results_dir = runtime_dir / "results"
            staging_dir = root / ".agents" / "staging" / "chunk_001"
            results_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            common.save_json(
                runtime_dir / "issue_status.json",
                {
                    "issue-a": {"status": "pending"},
                },
            )
            common.save_json(
                runtime_dir / "file_change_index.json",
                {
                    "src/a.c": {
                        "edits": [{"edit_id": "src/a.c#001"}],
                    }
                },
            )
            common.save_json(
                staging_dir / "issue_status_delta.json",
                {
                    "issue-a": {"status": "fixed"},
                    "issue-b": {"status": "failed"},
                },
            )
            common.save_json(
                staging_dir / "file_change_delta.json",
                {
                    "src/a.c": {
                        "edits": [{"edit_id": "src/a.c#002"}],
                    },
                    "src/b.c": {
                        "edits": [{"edit_id": "src/b.c#001"}],
                    },
                },
            )
            common.save_json(
                staging_dir / "chunk_result.json",
                {"chunk_index": 1},
            )
            (staging_dir / "chunk_result.md").write_text("# chunk 1\n", encoding="utf-8")

            imported = common.import_chunk_staging_artifacts(
                staging_dir,
                1,
                runtime_dir=runtime_dir,
                results_dir=results_dir,
            )

            issue_status = common.load_json(runtime_dir / "issue_status.json", {})
            file_change_index = common.load_json(runtime_dir / "file_change_index.json", {})
            chunk_result = common.load_json(results_dir / "chunk_001_result.json", {})

        self.assertEqual(issue_status["issue-a"]["status"], "fixed")
        self.assertEqual(issue_status["issue-b"]["status"], "failed")
        self.assertEqual(len(file_change_index["src/a.c"]["edits"]), 2)
        self.assertEqual(file_change_index["src/b.c"]["edits"][0]["edit_id"], "src/b.c#001")
        self.assertEqual(chunk_result["chunk_index"], 1)
        self.assertEqual(imported["chunk_result_json_path"], results_dir / "chunk_001_result.json")

    def test_import_chunk_staging_artifacts_requires_all_staging_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / ".agents" / "runtime"
            results_dir = runtime_dir / "results"
            staging_dir = root / ".agents" / "staging" / "chunk_001"
            results_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)
            common.save_json(runtime_dir / "issue_status.json", {})
            common.save_json(runtime_dir / "file_change_index.json", {})
            common.save_json(staging_dir / "issue_status_delta.json", {})
            common.save_json(staging_dir / "file_change_delta.json", {})
            common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 1})

            with self.assertRaisesRegex(FileNotFoundError, "missing staging artifact"):
                common.import_chunk_staging_artifacts(
                    staging_dir,
                    1,
                    runtime_dir=runtime_dir,
                    results_dir=results_dir,
                )

    def test_import_chunk_staging_artifacts_accepts_wrapped_agent_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / ".agents" / "runtime"
            results_dir = runtime_dir / "results"
            staging_dir = root / ".agents" / "staging" / "chunk_001"
            results_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            common.save_json(
                runtime_dir / "issue_status.json",
                {
                    "issue-a": {
                        "status": "pending",
                        "edit_ids": [],
                    }
                },
            )
            common.save_json(runtime_dir / "file_change_index.json", {})
            common.save_json(
                staging_dir / "issue_status_delta.json",
                {
                    "chunk_index": 1,
                    "status_changes": [
                        {
                            "issue_key": "issue-a",
                            "new_status": "fixed",
                            "risk_level": "low",
                            "risk_reason": None,
                            "requires_review_after_fix": False,
                        }
                    ],
                },
            )
            common.save_json(
                staging_dir / "file_change_delta.json",
                {
                    "chunk_index": 1,
                    "file_changes": [
                        {
                            "file": "src/a.c",
                            "change_type": "modified",
                            "lines_modified": [3],
                            "linked_issues": ["issue-a"],
                            "summary": "Removed unused variable",
                        }
                    ],
                },
            )
            common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 1})
            (staging_dir / "chunk_result.md").write_text("# chunk 1\n", encoding="utf-8")

            common.import_chunk_staging_artifacts(
                staging_dir,
                1,
                runtime_dir=runtime_dir,
                results_dir=results_dir,
            )

            issue_status = common.load_json(runtime_dir / "issue_status.json", {})
            file_change_index = common.load_json(runtime_dir / "file_change_index.json", {})

        self.assertEqual(issue_status["issue-a"]["status"], "fixed")
        self.assertEqual(issue_status["issue-a"]["chunk_index"], 1)
        self.assertEqual(issue_status["issue-a"]["edit_ids"], ["src/a.c#001"])
        self.assertEqual(file_change_index["src/a.c"]["edits"][0]["edit_id"], "src/a.c#001")
        self.assertEqual(
            file_change_index["src/a.c"]["edits"][0]["related_issue_keys"],
            ["issue-a"],
        )

    def test_import_accepts_files_inspected_schema(self) -> None:
        """Test that files_inspected format is treated as inspection-only (no edits)."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / ".agents" / "runtime"
            results_dir = runtime_dir / "results"
            staging_dir = root / ".agents" / "staging" / "chunk_011"
            results_dir.mkdir(parents=True)
            staging_dir.mkdir(parents=True)

            common.save_json(
                runtime_dir / "issue_status.json",
                {
                    "misra_advisory.c:11:misra-c2012-8.4:4a2c80d8": {
                        "status": "pending",
                    }
                },
            )
            common.save_json(runtime_dir / "file_change_index.json", {})
            common.save_json(
                staging_dir / "issue_status_delta.json",
                {
                    "misra_advisory.c:11:misra-c2012-8.4:4a2c80d8": {
                        "new_status": "needs_manual_review",
                        "risk_level": "high",
                        "risk_reason": "No rule-specific auto-fix policy is configured.",
                        "requires_review_after_fix": False,
                        "chunk_index": 11,
                        "edit_id": None,
                        "related_issue_keys": [],
                        "blocker": None,
                    }
                },
            )
            # Agent used files_inspected instead of file_changes — inspection-only
            common.save_json(
                staging_dir / "file_change_delta.json",
                {
                    "files_inspected": [
                        {
                            "file": "misra_advisory.c",
                            "linked_issues": ["misra_advisory.c:11:misra-c2012-8.4:4a2c80d8"],
                            "change_summary": "No changes applied - issue marked for manual review",
                            "edits": [],
                        }
                    ],
                    "chunk_index": 11,
                },
            )
            common.save_json(staging_dir / "chunk_result.json", {"chunk_index": 11})
            (staging_dir / "chunk_result.md").write_text("# chunk 11\n", encoding="utf-8")

            common.import_chunk_staging_artifacts(
                staging_dir,
                11,
                runtime_dir=runtime_dir,
                results_dir=results_dir,
            )

            issue_status = common.load_json(runtime_dir / "issue_status.json", {})
            file_change_index = common.load_json(runtime_dir / "file_change_index.json", {})

        # Issue should be updated to needs_manual_review
        issue = issue_status["misra_advisory.c:11:misra-c2012-8.4:4a2c80d8"]
        self.assertEqual(issue["new_status"], "needs_manual_review")

        # File should appear in file_change_index with empty edits (no fake edit_ids)
        self.assertIn("misra_advisory.c", file_change_index)
        self.assertEqual(file_change_index["misra_advisory.c"]["edits"], [])
        self.assertEqual(
            file_change_index["misra_advisory.c"]["change_summary"],
            "No changes applied - issue marked for manual review",
        )


if __name__ == "__main__":
    unittest.main()
