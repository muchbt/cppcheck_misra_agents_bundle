from __future__ import annotations

import sys
import unittest
from pathlib import Path


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
        self.assertIn("agent.launch must be an object", errors)
        self.assertEqual(warnings, [])

    def test_validate_pipeline_config_accepts_structured_agent(self) -> None:
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})

        errors, warnings = common.validate_pipeline_config(config)

        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])


if __name__ == "__main__":
    unittest.main()
