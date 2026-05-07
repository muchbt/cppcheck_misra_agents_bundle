"""Tests for collect_chunks module."""

import json
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import collect_chunks  # noqa: E402


def test_collect_result_dataclass():
    r = collect_chunks.CollectResult(
        host_id="device-B",
        imported_chunks=[3, 4],
        skipped_conflicts=[],
        failed_chunks=[5],
    )
    assert r.host_id == "device-B"
    assert r.imported_chunks == [3, 4]


def _make_bundle(tmp_path: Path, manifest: dict, patch_content: str = None, staging_files: dict = None):
    """Helper to create a fake export bundle tar.gz."""
    bundle = tmp_path / "bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        import io
        data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        if patch_content:
            pdata = patch_content.encode("utf-8")
            pinfo = tarfile.TarInfo(name="patches/source.patch")
            pinfo.size = len(pdata)
            tar.addfile(pinfo, io.BytesIO(pdata))
        if staging_files:
            for arcname, content in staging_files.items():
                cdata = content.encode("utf-8")
                cinfo = tarfile.TarInfo(name=arcname)
                cinfo.size = len(cdata)
                tar.addfile(cinfo, io.BytesIO(cdata))
    return bundle


def test_import_one_bundle_run_id_mismatch_raises(tmp_path):
    manifest = {
        "format_version": 1,
        "run_id": "remote-id",
        "host_id": "device-B",
        "completed_chunks": [3],
        "failed_chunks": [],
    }
    bundle = _make_bundle(tmp_path, manifest)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "progress.json").write_text('{"run_id": "local-id"}')

    with patch("collect_chunks.RUNTIME_DIR", runtime_dir):
        with patch("collect_chunks.RESULTS_DIR", tmp_path / "results"):
            with patch("collect_chunks.LOGS_DIR", tmp_path / "logs"):
                with patch("collect_chunks.import_chunk_staging_artifacts"):
                    with pytest.raises(SystemExit) as exc_info:
                        collect_chunks.import_one_bundle(bundle)
    assert "run_id 不匹配" in str(exc_info.value)


def test_import_one_bundle_format_version_mismatch_raises(tmp_path):
    manifest = {
        "format_version": 99,
        "run_id": "local-id",
        "host_id": "device-B",
        "completed_chunks": [3],
        "failed_chunks": [],
    }
    bundle = _make_bundle(tmp_path, manifest)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "progress.json").write_text('{"run_id": "local-id"}')

    with patch("collect_chunks.RUNTIME_DIR", runtime_dir):
        with patch("collect_chunks.RESULTS_DIR", tmp_path / "results"):
            with patch("collect_chunks.LOGS_DIR", tmp_path / "logs"):
                with pytest.raises(SystemExit) as exc_info:
                    collect_chunks.import_one_bundle(bundle)
    assert "不支持的 bundle 格式版本" in str(exc_info.value)
