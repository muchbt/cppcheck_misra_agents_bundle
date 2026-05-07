"""End-to-end test: export -> collect roundtrip."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import export_chunks
import collect_chunks


def test_export_then_collect_roundtrip(tmp_path):
    """Simulate worker export + coordinator collect with mocked filesystem."""
    # --- Setup worker filesystem ---
    worker_runtime = tmp_path / "worker" / "runtime"
    worker_runtime.mkdir(parents=True)
    worker_config = tmp_path / "worker" / "config"
    worker_config.mkdir(parents=True)
    worker_staging = tmp_path / "worker" / ".agents" / "staging"
    worker_staging.mkdir(parents=True)
    worker_logs = tmp_path / "worker" / "logs"
    worker_logs.mkdir()

    chunk_dir = worker_staging / "chunk_003"
    chunk_dir.mkdir()
    (chunk_dir / "chunk_result.json").write_text('{"fixed": 2}')
    (chunk_dir / "issue_status_delta.json").write_text('{"k1": {"status": "fixed"}}')
    (chunk_dir / "file_change_delta.json").write_text('{"k1": []}')
    (chunk_dir / "chunk_result.md").write_text("# Chunk 3 Result")
    (worker_logs / "chunk_003.log").write_text("agent stdout")
    (worker_runtime / "progress.json").write_text(
        json.dumps({"run_id": "20260507-001", "completed_chunks": [3], "failed_chunks": []})
    )
    (worker_config / "pipeline.json").write_text(
        json.dumps({"agent": {"staging_dir": str(tmp_path / "worker" / ".agents" / "staging")}})
    )

    # --- Worker export ---
    bundle_path = tmp_path / "export-20260507-001-worker.tar.gz"
    with patch("export_chunks.RUNTIME_DIR", worker_runtime):
        with patch("export_chunks.CONFIG_DIR", worker_config):
            with patch("export_chunks.LOGS_DIR", worker_logs):
                with patch("export_chunks.ROOT", tmp_path / "worker"):
                    with patch("export_chunks.subprocess.run") as mock_git:
                        mock_git.return_value.returncode = 0
                        mock_git.return_value.stdout = ""
                        rc = export_chunks.main(["--output", str(bundle_path), "--host-id", "worker"])
    assert rc == 0
    assert bundle_path.exists()

    # --- Setup coordinator filesystem ---
    coord_runtime = tmp_path / "coord" / "runtime"
    coord_runtime.mkdir(parents=True)
    coord_results = tmp_path / "coord" / "results"
    coord_results.mkdir(parents=True)
    coord_logs = tmp_path / "coord" / "logs"
    coord_logs.mkdir()
    (coord_runtime / "progress.json").write_text(
        json.dumps({"run_id": "20260507-001", "completed_chunks": [], "failed_chunks": [], "total_chunks": 5})
    )
    (coord_runtime / "issue_status.json").write_text('{}')
    (coord_runtime / "file_change_index.json").write_text('{}')

    mock_import = MagicMock()
    with patch("collect_chunks.RUNTIME_DIR", coord_runtime):
        with patch("collect_chunks.RESULTS_DIR", coord_results):
            with patch("collect_chunks.LOGS_DIR", coord_logs):
                with patch("collect_chunks.import_chunk_staging_artifacts", mock_import):
                    rc = collect_chunks.main(["--from", str(bundle_path)])
    assert rc == 0
    mock_import.assert_called_once()
    args_pos, kwargs = mock_import.call_args
    assert args_pos[1] == 3  # chunk_index is the 2nd positional arg

    progress = json.loads((coord_runtime / "progress.json").read_text())
    assert 3 in progress["completed_chunks"]
