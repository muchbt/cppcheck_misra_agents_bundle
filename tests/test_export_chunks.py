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
