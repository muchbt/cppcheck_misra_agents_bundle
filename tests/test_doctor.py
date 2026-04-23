from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402
import doctor  # type: ignore  # noqa: E402


class DoctorTests(unittest.TestCase):
    def test_check_cppcheck_xml_reports_invalid_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "cppcheck.xml"
            xml_path.write_text("<results><error></results>", encoding="utf-8")

            result = doctor.check_cppcheck_xml(xml_path)

        self.assertEqual(result["level"], "error")
        self.assertEqual(result["code"], "cppcheck_xml_invalid")
        self.assertIn("XML", result["message"])
        self.assertIn("cppcheck.xml", result["detail"])

    def test_check_cppcheck_xml_reports_scan_log_text_as_invalid_xml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "cppcheck.xml"
            xml_path.write_text("cppcheck: error: something happened", encoding="utf-8")

            result = doctor.check_cppcheck_xml(xml_path)

        self.assertEqual(result["level"], "error")
        self.assertEqual(result["code"], "cppcheck_xml_invalid")

    def test_check_pipeline_config_reports_errors(self) -> None:
        result = doctor.check_pipeline_config({"project": {}, "input": {}})

        self.assertEqual(result["level"], "error")
        self.assertEqual(result["code"], "pipeline_config_invalid")
        self.assertIn("配置", result["message"])
        self.assertTrue(result["detail"])

    def test_check_runtime_strategy_reports_mismatch_warning(self) -> None:
        config = {"fix_strategy": {"mode": "conservative"}}
        progress = {"fix_strategy": "all_auto"}

        result = doctor.check_runtime_strategy(config, progress)

        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["code"], "runtime_strategy_mismatch")
        self.assertIn("策略", result["message"])

    def test_check_existing_unfinished_run_reports_warning(self) -> None:
        result = doctor.check_existing_unfinished_run({"status": "ready"})

        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["code"], "unfinished_run")
        self.assertIn("oneshot", result["detail"])

    def test_check_archive_size_reports_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            runs_dir.mkdir()
            (runs_dir / "20260423-001").mkdir()
            (runs_dir / "20260423-001" / "archive.json").write_text("x" * 8, encoding="utf-8")

            result = doctor.check_archive_size(runs_dir)

        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["code"], "archive_nonempty")
        self.assertIn("归档", result["message"])

    def test_check_prompt_length_reports_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            prompt_path = Path(tmp) / "fix_chunk_prompt.txt"
            prompt_path.write_text("x" * 6001, encoding="utf-8")

            result = doctor.check_prompt_length(prompt_path)

        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["code"], "prompt_too_long")
        self.assertIn("提示词", result["message"])

    def test_check_agent_command_reports_missing_executable(self) -> None:
        config = {"agent": {"command": "missing-codex"}}

        with patch.object(doctor.shutil, "which", return_value=None):
            result = doctor.check_agent_command(config)

        self.assertEqual(result["level"], "error")
        self.assertEqual(result["code"], "agent_command_missing")

    def test_check_custom_verification_command_reports_missing_executable(self) -> None:
        config = {"verification": {"custom_command": "missing-verify"}}

        with patch.object(doctor.shutil, "which", return_value=None):
            result = doctor.check_custom_verification_command(config)

        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["code"], "custom_verification_command_missing")

    def test_collect_checks_uses_repo_root_from_any_cwd(self) -> None:
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            os.chdir(tmp)
            try:
                reloaded = importlib.reload(doctor)
                results = reloaded.collect_checks()
            finally:
                os.chdir(original_cwd)

        self.assertEqual(reloaded.ROOT, REPO_ROOT)
        self.assertTrue(any(item["code"] == "python_version" for item in results))

    def test_collect_checks_reports_malformed_progress_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".agents" / "config"
            runtime_dir = root / ".agents" / "runtime"
            prompts_dir = root / ".agents" / "prompts"
            runs_dir = root / ".agents" / "runs"

            config_dir.mkdir(parents=True)
            runtime_dir.mkdir(parents=True)
            prompts_dir.mkdir(parents=True)
            runs_dir.mkdir(parents=True)

            (config_dir / "pipeline.json").write_text("{}", encoding="utf-8")
            (runtime_dir / "progress.json").write_text("{", encoding="utf-8")
            (prompts_dir / "fix_chunk_prompt.txt").write_text("short prompt", encoding="utf-8")

            results = doctor.collect_checks(root=root)

        self.assertTrue(any(item["code"] == "progress_json_invalid" for item in results))
        progress_result = next(item for item in results if item["code"] == "progress_json_invalid")
        self.assertEqual(progress_result["level"], "error")
        self.assertIn("progress.json", progress_result["message"])
        self.assertIn("progress.json", progress_result["detail"])

    def test_task2_cli_sources_do_not_use_pep604_optional_syntax(self) -> None:
        doctor_source = (TOOLS_DIR / "doctor.py").read_text(encoding="utf-8")
        pipeline_cli_source = (TOOLS_DIR / "pipeline_cli.py").read_text(encoding="utf-8")

        self.assertNotIn(" | None", doctor_source)
        self.assertNotIn(" | None", pipeline_cli_source)


if __name__ == "__main__":
    unittest.main()
