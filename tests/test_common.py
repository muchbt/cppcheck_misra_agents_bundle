"""Tests for common.py utility functions."""

import sys
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402


def test_reset_runtime_logs_clears_logs_dir(tmp_path):
    """Test that reset_runtime_logs clears the logs directory."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True)
    (logs_dir / "chunk_001.log").write_text("test log content")
    (logs_dir / "chunk_002.log").write_text("test log content 2")
    assert logs_dir.exists()
    assert (logs_dir / "chunk_001.log").exists()

    common.reset_runtime_logs(tmp_path)

    assert logs_dir.exists()  # Directory should be recreated
    assert not (logs_dir / "chunk_001.log").exists()  # Contents should be cleared
    assert not (logs_dir / "chunk_002.log").exists()


def test_logs_dir_constant_exists():
    """Test that LOGS_DIR constant is defined."""
    assert hasattr(common, "LOGS_DIR")
    assert common.LOGS_DIR == common.RUNTIME_DIR / "logs"


def test_ensure_dirs_includes_logs_dir(tmp_path):
    """Test that ensure_dirs creates LOGS_DIR and all other directories."""
    # Use patch to isolate all directory constants
    test_agents_dir = tmp_path / ".agents"
    test_runtime_dir = test_agents_dir / "runtime"

    with patch.object(common, "AGENTS_DIR", test_agents_dir), \
         patch.object(common, "CONFIG_DIR", tmp_path / "config"), \
         patch.object(common, "PROMPTS_DIR", tmp_path / "prompts"), \
         patch.object(common, "SKILLS_DIR", tmp_path / "skills"), \
         patch.object(common, "RUNTIME_DIR", test_runtime_dir), \
         patch.object(common, "RUNS_DIR", test_runtime_dir / "runs"), \
         patch.object(common, "CHUNKS_DIR", test_runtime_dir / "chunks"), \
         patch.object(common, "RESULTS_DIR", test_runtime_dir / "results"), \
         patch.object(common, "REPORTS_DIR", test_runtime_dir / "reports"), \
         patch.object(common, "LOGS_DIR", test_runtime_dir / "logs"):
        # Ensure none of these exist before calling ensure_dirs
        assert not test_runtime_dir.exists()
        assert not (test_runtime_dir / "logs").exists()

        # Call the actual function
        common.ensure_dirs()

        # Verify all directories were created by ensure_dirs
        assert test_agents_dir.exists()
        assert (tmp_path / "config").exists()
        assert (tmp_path / "prompts").exists()
        assert (tmp_path / "skills").exists()
        assert test_runtime_dir.exists()
        assert (test_runtime_dir / "runs").exists()
        assert (test_runtime_dir / "chunks").exists()
        assert (test_runtime_dir / "results").exists()
        assert (test_runtime_dir / "reports").exists()
        assert (test_runtime_dir / "logs").exists()