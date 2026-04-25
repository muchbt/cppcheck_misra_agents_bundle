from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, get_type_hints
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402


class CommonRuntimeTests(unittest.TestCase):
    def test_root_discovery_from_non_root_workdir(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                reloaded = importlib.reload(common)
                self.assertEqual(Path.cwd(), Path(tmp))
                self.assertEqual(reloaded.ROOT, REPO_ROOT)
                self.assertEqual(reloaded.RUNTIME_DIR, REPO_ROOT / ".agents" / "runtime")
            finally:
                os.chdir(original_cwd)

    def test_next_run_id_increments_by_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            (runs_dir / "20260423-001").mkdir()
            (runs_dir / "20260423-003").mkdir()
            (runs_dir / "20260422-010").mkdir()
            (runs_dir / "not-a-run").mkdir()

            run_id = common.next_run_id(runs_dir=runs_dir, now=datetime(2026, 4, 23, 10, 0, tzinfo=common.TZ))

        self.assertEqual(run_id, "20260423-004")

    def test_validate_pipeline_config_is_python_38_compatible(self) -> None:
        hints = get_type_hints(common.validate_pipeline_config)
        self.assertEqual(hints["return"], Tuple[List[str], List[str]])

        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        errors, warnings = common.validate_pipeline_config(config)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

        broken = deepcopy(config)
        broken["fix_strategy"]["mode"] = "fast"
        broken["chunking"]["max_issues_per_chunk"] = "12"

        errors, warnings = common.validate_pipeline_config(broken)
        self.assertIn("fix_strategy.mode must be one of: conservative, all_auto", errors)
        self.assertIn("chunking.max_issues_per_chunk must be a positive integer", errors)
        self.assertEqual(warnings, [])

    def test_validate_pipeline_config_rejects_bool_chunk_sizes(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        broken = deepcopy(config)
        broken["chunking"]["max_issues_per_chunk"] = True
        broken["chunking"]["max_files_per_chunk"] = False

        errors, warnings = common.validate_pipeline_config(broken)

        self.assertIn("chunking.max_issues_per_chunk must be a positive integer", errors)
        self.assertIn("chunking.max_files_per_chunk must be a positive integer", errors)
        self.assertEqual(warnings, [])

    def test_append_pipeline_event_writes_stable_jsonl_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)
            fixed_time = "2026-04-23T10:00:00+08:00"
            with patch.object(common, "now_iso", return_value=fixed_time):
                common.append_pipeline_event(
                    runtime_dir,
                    event="chunk_completed",
                    stage="run",
                    message="chunk 1 处理完成",
                    chunk_index=1,
                    returncode=0,
                    data={},
                )

            pipeline_log = (runtime_dir / "pipeline.log").read_text(encoding="utf-8").strip()
            jsonl_line = (runtime_dir / "run_log.jsonl").read_text(encoding="utf-8").strip()
            event = json.loads(jsonl_line)

        self.assertIn("chunk 1 处理完成", pipeline_log)
        self.assertIn("chunk=1", pipeline_log)
        self.assertIn("returncode=0", pipeline_log)
        self.assertEqual(
            list(event.keys()),
            ["time", "event", "stage", "level", "message", "chunk_index", "returncode", "data"],
        )
        self.assertEqual(event["time"], fixed_time)
        self.assertEqual(event["event"], "chunk_completed")
        self.assertEqual(event["stage"], "run")
        self.assertEqual(event["level"], "info")
        self.assertEqual(event["message"], "chunk 1 处理完成")
        self.assertEqual(event["chunk_index"], 1)
        self.assertEqual(event["returncode"], 0)
        self.assertEqual(event["data"], {})

    def test_archive_copy_and_size(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            reports_dir = root / "reports"
            archive_dir = root / "archive"

            (runtime_dir / "chunks").mkdir(parents=True)
            (runtime_dir / "results").mkdir(parents=True)
            (runtime_dir / "logs").mkdir(parents=True)
            reports_dir.mkdir()

            (runtime_dir / "progress.json").write_text("{\"run_id\": \"20260423-001\"}\n", encoding="utf-8")
            (runtime_dir / "issue_status.json").write_text("{\"issues\": []}\n", encoding="utf-8")
            (runtime_dir / "chunks" / "chunk_001.json").write_text("{\"chunk\": 1}\n", encoding="utf-8")
            (runtime_dir / "results" / "chunk_001_result.json").write_text("{\"result\": true}\n", encoding="utf-8")
            (runtime_dir / "pipeline.log").write_text("line one\n", encoding="utf-8")
            (runtime_dir / "run_log.jsonl").write_text("{\"event\": \"x\"}\n", encoding="utf-8")
            # Add execution logs in runtime/logs/
            (runtime_dir / "logs" / "chunk_001.log").write_text("=== CHUNK 001 EXECUTION LOG ===\n", encoding="utf-8")
            (runtime_dir / "logs" / "chunk_002.log").write_text("=== CHUNK 002 EXECUTION LOG ===\n", encoding="utf-8")
            (reports_dir / "final_summary.md").write_text("# summary\n", encoding="utf-8")
            (reports_dir / "final_summary.json").write_text("{\"ok\": true}\n", encoding="utf-8")

            common.copy_current_run_archive(runtime_dir, reports_dir, archive_dir)

            self.assertEqual(
                (archive_dir / "runtime" / "progress.json").read_text(encoding="utf-8"),
                "{\"run_id\": \"20260423-001\"}\n",
            )
            self.assertEqual(
                (archive_dir / "runtime" / "chunks" / "chunk_001.json").read_text(encoding="utf-8"),
                "{\"chunk\": 1}\n",
            )
            self.assertEqual(
                (archive_dir / "runtime" / "results" / "chunk_001_result.json").read_text(encoding="utf-8"),
                "{\"result\": true}\n",
            )
            # Verify runtime/logs/ subdirectory was archived
            self.assertEqual(
                (archive_dir / "runtime" / "logs" / "chunk_001.log").read_text(encoding="utf-8"),
                "=== CHUNK 001 EXECUTION LOG ===\n",
            )
            self.assertEqual(
                (archive_dir / "runtime" / "logs" / "chunk_002.log").read_text(encoding="utf-8"),
                "=== CHUNK 002 EXECUTION LOG ===\n",
            )
            self.assertEqual(
                (archive_dir / "reports" / "final_summary.md").read_text(encoding="utf-8"),
                "# summary\n",
            )
            self.assertEqual(
                (archive_dir / "logs" / "pipeline.log").read_text(encoding="utf-8"),
                "line one\n",
            )
            self.assertGreater(common.archive_size_bytes(archive_dir), 0)
            self.assertEqual(common.archive_size_bytes(root / "missing"), 0)

    def test_archive_copy_preserves_empty_runtime_directories(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_dir = root / "runtime"
            reports_dir = root / "reports"
            archive_dir = root / "archive"

            (runtime_dir / "chunks").mkdir(parents=True)
            (runtime_dir / "results").mkdir(parents=True)
            reports_dir.mkdir()

            common.copy_current_run_archive(runtime_dir, reports_dir, archive_dir)

            self.assertTrue((archive_dir / "runtime" / "chunks").is_dir())
            self.assertTrue((archive_dir / "runtime" / "results").is_dir())

    def test_validate_rule_policy_is_python_38_compatible(self) -> None:
        hints = get_type_hints(common.validate_rule_policy)
        self.assertEqual(hints["return"], Tuple[List[str], List[str]])

        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        errors, warnings = common.validate_rule_policy(config)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_invalid_action(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        broken["actions"]["unusedVariable"]["action"] = "invalid_action"

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("actions.unusedVariable.action must be one of: auto_fix, careful_fix, fix, needs_manual_review, skip", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_missing_default(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        del broken["default"]

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("missing required field: default", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_missing_default_action(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        del broken["default"]["action"]

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("default.action is required", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_invalid_pattern_match_contains(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        broken["patterns"][0]["match_contains"] = ""

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("patterns[0].match_contains must be a non-empty string", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_invalid_risk_level(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        broken["actions"]["nullPointer"]["risk_level"] = "critical"

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("actions.nullPointer.risk_level must be one of: high, low, medium", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_non_object_config(self) -> None:
        errors, warnings = common.validate_rule_policy("not a dict")
        self.assertIn("rule_policy config must be a JSON object", errors)
        self.assertEqual(warnings, [])

        errors, warnings = common.validate_rule_policy([])
        self.assertIn("rule_policy config must be a JSON object", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_missing_actions(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        del broken["actions"]

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("missing required field: actions", errors)
        self.assertEqual(warnings, [])

    def test_validate_rule_policy_rejects_missing_patterns(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "rule_policy.json", {})
        broken = deepcopy(config)
        del broken["patterns"]

        errors, warnings = common.validate_rule_policy(broken)
        self.assertIn("missing required field: patterns", errors)
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
