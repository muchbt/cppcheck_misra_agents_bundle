from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import common  # type: ignore  # noqa: E402
import run_fix_pipeline  # type: ignore  # noqa: E402
import split_cppcheck_xml  # type: ignore  # noqa: E402


class SplitAndRunPipelineTests(unittest.TestCase):
    def build_temp_pipeline_config(self, xml_relpath: str = "cppcheck.xml") -> dict:
        config = deepcopy(common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {}))
        config["input"]["cppcheck_xml"] = xml_relpath
        return config

    def test_split_run_id_records_started_at_and_resets_runtime_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config_dir = root / ".agents" / "config"
            runtime_dir = root / ".agents" / "runtime"
            chunks_dir = runtime_dir / "chunks"
            results_dir = runtime_dir / "results"
            xml_path = root / "cppcheck.xml"

            config_dir.mkdir(parents=True)
            chunks_dir.mkdir(parents=True)
            results_dir.mkdir(parents=True)

            (config_dir / "pipeline.json").write_text(
                json.dumps(self.build_temp_pipeline_config()),
                encoding="utf-8",
            )
            (config_dir / "rule_policy.json").write_text(
                json.dumps({"actions": {}, "patterns": [], "default": {"action": "fix"}}),
                encoding="utf-8",
            )
            xml_path.write_text(
                (
                    "<results><errors><error id=\"misra-c2012-1.1\" severity=\"style\" "
                    "msg=\"sample\"><location file=\"src/a.c\" line=\"10\"/></error></errors></results>"
                ),
                encoding="utf-8",
            )
            (runtime_dir / "pipeline.log").write_text("old log\n", encoding="utf-8")
            (runtime_dir / "run_log.jsonl").write_text("{\"old\": true}\n", encoding="utf-8")
            (chunks_dir / "chunk_999.json").write_text("{}", encoding="utf-8")
            (results_dir / "chunk_999_result.json").write_text("{}", encoding="utf-8")

            def ensure_dirs_local() -> None:
                for path in [config_dir, runtime_dir, chunks_dir, results_dir]:
                    path.mkdir(parents=True, exist_ok=True)

            with patch.object(split_cppcheck_xml, "CONFIG_DIR", config_dir), patch.object(
                split_cppcheck_xml, "CHUNKS_DIR", chunks_dir
            ), patch.object(split_cppcheck_xml, "RESULTS_DIR", results_dir), patch.object(
                split_cppcheck_xml, "RUNTIME_DIR", runtime_dir
            ), patch.object(
                split_cppcheck_xml, "ensure_dirs", side_effect=ensure_dirs_local
            ):
                rc = split_cppcheck_xml.main(["--run-id", "20260423-007"])

            self.assertEqual(rc, 0)
            progress = common.load_json(runtime_dir / "progress.json", {})
            self.assertEqual(progress["run_id"], "20260423-007")
            self.assertTrue(progress["started_at"])
            self.assertEqual(progress["status"], "ready")
            self.assertFalse((chunks_dir / "chunk_999.json").exists())
            self.assertFalse((results_dir / "chunk_999_result.json").exists())

            pipeline_log = (runtime_dir / "pipeline.log").read_text(encoding="utf-8")
            run_log_lines = (runtime_dir / "run_log.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertNotIn("old log", pipeline_log)
            self.assertEqual(len(run_log_lines), 2)
            self.assertEqual(json.loads(run_log_lines[0])["event"], "split_started")
            self.assertEqual(json.loads(run_log_lines[1])["event"], "split_completed")

    def test_run_pipeline_uses_agent_runner_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()

            common.save_json(
                runtime_dir / "progress.json",
                {
                    "run_id": "20260423-001",
                    "total_chunks": 1,
                    "completed_chunks": [],
                    "failed_chunks": [],
                    "current_chunk": None,
                    "fix_strategy": "conservative",
                    "status": "ready",
                },
            )
            common.save_json(
                chunks_dir / "chunk_001.json",
                {
                    "chunk_index": 1,
                    "chunk_total": 1,
                    "issues": [{"rule_id": "misra-c2012-1.1", "is_misra": True}],
                },
            )

            def fake_run_chunk_agent(config: dict, chunk: dict) -> dict:
                result_path = results_dir / "chunk_001_result.json"
                common.save_json(result_path, {"chunk_index": chunk["chunk_index"]})
                return {
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "error_kind": "",
                    "prompt": "prompt body",
                    "imported_paths": {
                        "chunk_result_json_path": result_path,
                    },
                }

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "run_chunk_agent", side_effect=fake_run_chunk_agent
            ), patch.object(
                run_fix_pipeline,
                "verify_chunk_result",
                return_value={"passed": True, "mode": "light"},
            ) as verify_mock, redirect_stdout(stdout):
                rc = run_fix_pipeline.main([])

            self.assertEqual(rc, 0)
            self.assertIn("正在处理 chunk 1/1", stdout.getvalue())
            verify_mock.assert_called_once_with(1)

            progress = common.load_json(runtime_dir / "progress.json", {})
            self.assertEqual(progress["status"], "done")
            self.assertEqual(progress["completed_chunks"], [1])

            events = [
                json.loads(line)
                for line in (runtime_dir / "run_log.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertIn("run_started", [item["event"] for item in events])
            self.assertIn("chunk_started", [item["event"] for item in events])
            self.assertIn("chunk_completed", [item["event"] for item in events])
            completed = next(item for item in events if item["event"] == "chunk_completed")
            self.assertTrue(completed["data"]["verification_passed"])
            self.assertEqual(str(results_dir / "chunk_001_result.json"), completed["data"]["imported_result_json"])

    def test_run_pipeline_failure_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()

            common.save_json(
                runtime_dir / "progress.json",
                {
                    "run_id": "20260423-002",
                    "total_chunks": 1,
                    "completed_chunks": [],
                    "failed_chunks": [],
                    "current_chunk": None,
                    "fix_strategy": "conservative",
                    "status": "ready",
                },
            )
            common.save_json(
                chunks_dir / "chunk_001.json",
                {
                    "chunk_index": 1,
                    "chunk_total": 1,
                    "issues": [{"rule_id": "misra-c2012-1.1", "is_misra": True}],
                },
            )

            def fake_run_chunk_agent(config: dict, chunk: dict) -> dict:
                return {
                    "returncode": 1,
                    "stdout": "",
                    "stderr": "Error: something went wrong in the agent execution...",
                    "error_kind": "agent_error",
                    "prompt": "prompt body",
                    "imported_paths": {},
                }

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "run_chunk_agent", side_effect=fake_run_chunk_agent
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main([])

            self.assertEqual(rc, 1)
            output = stdout.getvalue()
            # New format: error_kind on separate line, log path, and summary
            self.assertIn("[run] Chunk 1 失败: agent_error", output)
            self.assertIn("[run] 查看完整日志:", output)
            self.assertIn("[run] 错误摘要: Error: something went wrong in the agent execution...", output)


if __name__ == "__main__":
    unittest.main()
