"""Tests for common.py utility functions."""

import sys
from pathlib import Path

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
    """Test that ensure_dirs creates LOGS_DIR."""
    # Override paths for testing
    original_agents_dir = common.AGENTS_DIR
    original_runtime_dir = common.RUNTIME_DIR

    # Set test paths
    common.AGENTS_DIR = tmp_path / ".agents"
    common.RUNTIME_DIR = common.AGENTS_DIR / "runtime"
    common.LOGS_DIR = common.RUNTIME_DIR / "logs"

    common.ensure_dirs()

    # Verify LOGS_DIR was created
    assert common.LOGS_DIR.exists()

    # Restore original paths
    common.AGENTS_DIR = original_agents_dir
    common.RUNTIME_DIR = original_runtime_dir
    common.LOGS_DIR = common.RUNTIME_DIR / "logs"