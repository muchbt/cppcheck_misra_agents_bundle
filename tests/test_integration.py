"""Integration tests for bootstrap_agents.py and AGENTS.md consistency.

These tests verify that build_agents_md_block() produces content
matching the actual AGENTS.md, preventing regression when bootstrap
is run with --mode merge.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import bootstrap_agents  # type: ignore  # noqa: E402


class BootstrapIntegrationTests(unittest.TestCase):
    """Tests that verify bootstrap_agents.py produces correct AGENTS.md content."""

    def test_build_agents_md_block_matches_actual_agents_md(self) -> None:
        """Verify build_agents_md_block() output matches AGENTS.md auto-block.

        This prevents regression: if build_agents_md_block() is outdated,
        running bootstrap --mode merge would overwrite correct AGENTS.md
        with stale content.
        """
        agents_md_path = REPO_ROOT / "AGENTS.md"
        if not agents_md_path.exists():
            self.skipTest("AGENTS.md not found in repo root")

        agents_md_content = agents_md_path.read_text(encoding="utf-8")

        # Extract the auto-generated block from AGENTS.md
        begin_marker = "<!-- BEGIN AUTO-GENERATED: cppcheck-misra-fix -->"
        end_marker = "<!-- END AUTO-GENERATED: cppcheck-misra-fix -->"

        begin_idx = agents_md_content.find(begin_marker)
        end_idx = agents_md_content.find(end_marker)

        if begin_idx == -1 or end_idx == -1:
            self.skipTest("AGENTS.md does not contain auto-generated markers")

        # Extract block content (excluding markers)
        actual_block = agents_md_content[begin_idx + len(begin_marker) : end_idx].strip()

        # Get expected block from bootstrap function
        expected_block = bootstrap_agents.build_agents_md_block().strip()

        # Normalize whitespace for comparison
        actual_normalized = "\n".join(line.strip() for line in actual_block.splitlines() if line.strip())
        expected_normalized = "\n".join(line.strip() for line in expected_block.splitlines() if line.strip())

        self.assertEqual(
            actual_normalized,
            expected_normalized,
            "build_agents_md_block() output differs from AGENTS.md auto-block. "
            "Running bootstrap --mode merge would cause regression.",
        )

    def test_build_agents_md_block_contains_staging_delta_paths(self) -> None:
        """Verify build_agents_md_block() uses staging delta paths, not runtime paths.

        This is the core fix for the high-risk regression bug.
        """
        block = bootstrap_agents.build_agents_md_block()

        # Should NOT contain old runtime paths
        self.assertNotIn(".agents/runtime/issue_status.json", block)
        self.assertNotIn(".agents/runtime/file_change_index.json", block)
        self.assertNotIn(".agents/runtime/results/chunk_XXX_result.json", block)

        # Should contain staging delta paths
        self.assertIn("staging_dir", block)
        self.assertIn("issue_status_delta.json", block)
        self.assertIn("file_change_delta.json", block)
        self.assertIn("chunk_result.json", block)
        self.assertIn("chunk_result.md", block)

        # Should reference SKILL.md for format contract
        self.assertIn("SKILL.md", block)

    def test_build_agents_md_block_contains_edit_id_reference(self) -> None:
        """Verify block mentions edit_id for issue-to-edit mapping."""
        block = bootstrap_agents.build_agents_md_block()
        self.assertIn("edit_id", block)
        self.assertIn("related_issue_keys", block)


class CompatLayerIntegrationTests(unittest.TestCase):
    """Tests for compat layer synchronization."""

    def test_compat_agents_md_matches_root_agents_md(self) -> None:
        """Verify .agents/compat/AGENTS.md matches root AGENTS.md."""
        root_agents = REPO_ROOT / "AGENTS.md"
        compat_agents = REPO_ROOT / ".agents" / "compat" / "AGENTS.md"

        if not root_agents.exists() or not compat_agents.exists():
            self.skipTest("AGENTS.md files not found")

        root_content = root_agents.read_text(encoding="utf-8")
        compat_content = compat_agents.read_text(encoding="utf-8")

        self.assertEqual(
            root_content,
            compat_content,
            ".agents/compat/AGENTS.md differs from root AGENTS.md",
        )


if __name__ == "__main__":
    unittest.main()