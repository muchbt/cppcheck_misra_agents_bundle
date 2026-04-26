from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import validate_real  # type: ignore  # noqa: E402


class ValidateRealTests(unittest.TestCase):
    def test_parse_args_accepts_provider_and_keep_workdir(self) -> None:
        args = validate_real.parse_args(["--provider", "claude", "--keep-workdir"])

        self.assertEqual(args.provider, "claude")
        self.assertTrue(args.keep_workdir)

    def test_determine_provider_status_skips_missing_executable(self) -> None:
        checks = [
            {"level": "error", "code": "agent_launch_executable_missing", "message": "", "detail": ""},
        ]

        status, reason = validate_real.determine_provider_status("codex", checks, auth_ok=True, auth_detail="ok")

        self.assertEqual(status, "skipped_not_installed")
        self.assertIn("未安装", reason)

    def test_determine_provider_status_skips_auth_missing(self) -> None:
        checks = [
            {"level": "ok", "code": "agent_launch_ok", "message": "", "detail": ""},
        ]

        status, reason = validate_real.determine_provider_status("claude", checks, auth_ok=False, auth_detail="未检测到登录")

        self.assertEqual(status, "skipped_auth_missing")
        self.assertIn("未检测到登录", reason)

    def test_probe_auth_status_accepts_codex_shared_auth(self) -> None:
        checks = [
            {"level": "ok", "code": "agent_auth_shared", "message": "", "detail": "共享认证文件可复用"},
        ]

        ok, detail = validate_real.probe_auth_status("codex", checks)

        self.assertTrue(ok)
        self.assertIn("共享认证文件", detail)

    def test_main_writes_report_for_passed_provider(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            fake_result = {
                "provider": "claude",
                "status": "passed",
                "message": "ok",
                "workspace_root": str(Path(tmp) / "workspace"),
            }

            with patch.object(validate_real, "run_provider_validation", return_value=fake_result):
                rc = validate_real.main(["--provider", "claude", "--report", str(report_path)])

            self.assertEqual(rc, 0)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["providers"][0]["status"], "passed")
            self.assertEqual(report["summary"]["failed"], 0)

    def test_main_returns_nonzero_when_ready_provider_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "report.json"
            fake_result = {
                "provider": "opencode",
                "status": "failed",
                "message": "runtime failed",
                "workspace_root": str(Path(tmp) / "workspace"),
            }

            with patch.object(validate_real, "run_provider_validation", return_value=fake_result):
                rc = validate_real.main(["--provider", "opencode", "--report", str(report_path)])

            self.assertEqual(rc, 1)
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["providers"][0]["status"], "failed")
            self.assertEqual(report["summary"]["failed"], 1)

    def test_run_provider_validation_marks_timeout_as_failed(self) -> None:
        ok_checks = [
            {"level": "ok", "code": "agent_launch_ok", "message": "", "detail": ""},
        ]

        with patch.object(validate_real, "prepare_workspace"), patch.object(
            validate_real,
            "bootstrap_workspace",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ), patch.object(
            validate_real.doctor,
            "collect_checks",
            return_value=ok_checks,
        ), patch.object(
            validate_real,
            "probe_auth_status",
            return_value=(True, "ok"),
        ), patch.object(
            validate_real,
            "run_cli_command",
            side_effect=subprocess.TimeoutExpired(cmd=["split"], timeout=1),
        ):
            result = validate_real.run_provider_validation("claude")

        self.assertEqual(result["status"], "failed")
        self.assertIn("超时", result["message"])

    def test_run_provider_validation_retries_run_stage_once_after_timeout(self) -> None:
        ok_checks = [
            {"level": "ok", "code": "agent_launch_ok", "message": "", "detail": ""},
        ]
        run_calls = {"count": 0}

        def fake_run_cli_command(workspace_root, args):
            if args[:1] == ["split"]:
                return SimpleNamespace(returncode=0, stdout="split ok", stderr="")
            if args[:1] == ["run"]:
                run_calls["count"] += 1
                if run_calls["count"] == 1:
                    raise subprocess.TimeoutExpired(cmd=args, timeout=1)
                result_path = workspace_root / ".agents" / "runtime" / "results" / "chunk_001_result.json"
                result_path.parent.mkdir(parents=True, exist_ok=True)
                result_path.write_text(json.dumps({"chunk_index": 1}), encoding="utf-8")
                progress_path = workspace_root / ".agents" / "runtime" / "progress.json"
                progress_path.parent.mkdir(parents=True, exist_ok=True)
                progress_path.write_text(json.dumps({"status": "partial"}), encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="run ok", stderr="")
            if args[:1] == ["verify"]:
                result_path = workspace_root / ".agents" / "runtime" / "results" / "chunk_001_result.json"
                result_path.write_text(
                    json.dumps(
                        {
                            "chunk_index": 1,
                            "verification": {"performed": True, "passed": True, "returncode": 0},
                        }
                    ),
                    encoding="utf-8",
                )
                return SimpleNamespace(returncode=0, stdout="verify ok", stderr="")
            raise AssertionError(args)

        with patch.object(validate_real, "prepare_workspace"), patch.object(
            validate_real,
            "bootstrap_workspace",
            return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
        ), patch.object(
            validate_real.doctor,
            "collect_checks",
            return_value=ok_checks,
        ), patch.object(
            validate_real,
            "probe_auth_status",
            return_value=(True, "ok"),
        ), patch.object(
            validate_real,
            "run_cli_command",
            side_effect=fake_run_cli_command,
        ):
            result = validate_real.run_provider_validation("claude")

        self.assertEqual(run_calls["count"], 2)
        self.assertEqual(result["status"], "passed")

    def test_main_returns_error_when_report_path_unwritable(self) -> None:
        fake_result = {
            "provider": "claude",
            "status": "passed",
            "message": "ok",
            "workspace_root": "/tmp/workspace",
        }

        with patch.object(validate_real, "run_provider_validation", return_value=fake_result), patch.object(
            validate_real,
            "save_json",
            side_effect=OSError("read-only"),
        ):
            rc = validate_real.main(["--provider", "claude", "--report", "/readonly/report.json"])

        self.assertEqual(rc, 2)

    def test_run_subprocess_kills_process_group_on_timeout(self) -> None:
        proc = Mock()
        proc.pid = 4321
        proc.communicate.side_effect = [
            subprocess.TimeoutExpired(cmd=["x"], timeout=1),
            ("", ""),
        ]

        with patch.object(validate_real.subprocess, "Popen", return_value=proc), patch.object(
            validate_real, "platform"
        ) as platform_mock:
            platform_mock.system.return_value = "Linux"
            with patch.object(validate_real.os, "getpgid", return_value=4321) as getpgid_mock, patch.object(
                validate_real.os, "killpg"
            ) as killpg_mock:
                with self.assertRaises(subprocess.TimeoutExpired):
                    validate_real.run_subprocess(["x"], timeout=1)

        getpgid_mock.assert_called_once_with(4321)
        killpg_mock.assert_called_once_with(4321, 9)  # SIGKILL = 9


if __name__ == "__main__":
    unittest.main()
