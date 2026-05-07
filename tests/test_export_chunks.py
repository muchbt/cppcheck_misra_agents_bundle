"""Tests for export_chunks module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import export_chunks  # noqa: E402


def test_resolve_host_id_prefers_cli_flag():
    args = MagicMock()
    args.host_id = "my-host"
    with patch.dict("os.environ", {}, clear=True):
        with patch("export_chunks.socket.gethostname", return_value="socket-host"):
            result = export_chunks.resolve_host_id(args)
    assert result == "my-host"


def test_resolve_host_id_falls_back_to_env():
    args = MagicMock()
    args.host_id = None
    with patch.dict("os.environ", {"PIPELINE_HOST_ID": "env-host"}):
        with patch("export_chunks.socket.gethostname", return_value="socket-host"):
            result = export_chunks.resolve_host_id(args)
    assert result == "env-host"


def test_resolve_host_id_falls_back_to_socket():
    args = MagicMock()
    args.host_id = None
    with patch.dict("os.environ", {}, clear=True):
        with patch("export_chunks.socket.gethostname", return_value="socket-host"):
            result = export_chunks.resolve_host_id(args)
    assert result == "socket-host"


def test_try_generate_patch_returns_content_and_message(tmp_path):
    with patch("export_chunks.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "diff --git a/foo.c b/foo.c\n"
        content, msg = export_chunks.try_generate_patch(tmp_path)
    assert content == "diff --git a/foo.c b/foo.c\n"
    assert "已生成 source patch" in msg


def test_build_manifest_contains_expected_fields():
    manifest = export_chunks.build_manifest(
        run_id="20260507-001",
        host_id="device-B",
        completed_chunks=[3, 4],
        failed_chunks=[5],
        chunk_ids_requested=[3, 4, 5],
        has_source_patch=True,
        staging_dirs=["staging/chunk_003", "staging/chunk_004"],
    )
    assert manifest["format_version"] == 1
    assert manifest["run_id"] == "20260507-001"
    assert manifest["host_id"] == "device-B"
    assert manifest["completed_chunks"] == [3, 4]
    assert manifest["failed_chunks"] == [5]
    assert manifest["has_source_patch"] is True
    assert manifest["source_patch_file"] == "patches/source.patch"
    assert "exported_at" in manifest


def test_create_bundle_writes_tar_gz(tmp_path):
    staging_base = tmp_path / "staging"
    chunk_dir = staging_base / "chunk_003"
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "chunk_result.json").write_text('{"ok": true}')
    (chunk_dir / "issue_status_delta.json").write_text('{}')
    (chunk_dir / "file_change_delta.json").write_text('{}')
    (chunk_dir / "chunk_result.md").write_text("# Result")

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "chunk_003.log").write_text("log line")

    output = tmp_path / "export.tar.gz"
    manifest = export_chunks.build_manifest(
        run_id="20260507-001",
        host_id="device-B",
        completed_chunks=[3],
        failed_chunks=[],
        chunk_ids_requested=[3],
        has_source_patch=False,
        staging_dirs=["staging/chunk_003"],
    )
    export_chunks.create_bundle(
        output_path=output,
        manifest=manifest,
        patch_content=None,
        completed_export=[3],
        staging_base=staging_base,
        all_ids=[3],
        logs_dir=log_dir,
    )
    assert output.exists()
    import tarfile
    with tarfile.open(output, "r:gz") as tar:
        names = tar.getnames()
    assert "manifest.json" in names
    assert "staging/chunk_003/chunk_result.json" in names
    assert "logs/chunk_003.log" in names
