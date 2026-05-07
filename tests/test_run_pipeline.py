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
                    "argv": ["opencode"],
                    "imported_paths": {
                        "chunk_result_json_path": result_path,
                    },
                }

            stdout = io.StringIO()
            logs_dir = runtime_dir / "logs"
            logs_dir.mkdir()
            config_dir = Path(tmp) / "config"
            config_dir.mkdir()
            common.save_json(config_dir / "pipeline.json", {
                "agent": {"provider": "opencode", "staging_dir": ".agents/staging"}
            })
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
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
            logs_dir = runtime_dir / "logs"
            logs_dir.mkdir()
            config_dir = Path(tmp) / "config"
            config_dir.mkdir()
            # Use relative staging_dir to avoid ROOT validation issues
            # (resolve_agent_staging_dir default root=ROOT is bound at definition time)
            common.save_json(config_dir / "pipeline.json", {
                "agent": {
                    "provider": "opencode",
                    "staging_dir": ".agents/staging"
                }
            })
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
            ), patch.object(
                run_fix_pipeline, "run_chunk_agent", side_effect=fake_run_chunk_agent
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main([])

            self.assertEqual(rc, 0)
            output = stdout.getvalue()
            # New format: error_kind on separate line, log path, and summary
            self.assertIn("[run] Chunk 1 失败: agent_error", output)
            self.assertIn("[run] 查看完整日志:", output)
            self.assertIn("[run] 错误摘要: Error: something went wrong in the agent execution...", output)


class ExecutionLogTests(unittest.TestCase):
    """Tests for write_chunk_execution_log and extract_error_summary."""

    def test_write_chunk_execution_log_format(self) -> None:
        """Test log file format on first attempt."""
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "logs"
            logs_dir.mkdir(parents=True)

            with patch.object(run_fix_pipeline, "LOGS_DIR", logs_dir):
                log_path = run_fix_pipeline.write_chunk_execution_log(
                    chunk_index=1,
                    attempt=1,
                    provider="codex",
                    command="codex exec --full-auto",
                    cwd="/workspace",
                    staging_dir="/workspace/.agents/staging/chunk_001",
                    prompt="Fix the issue",
                    stdout="Output line 1\nOutput line 2",
                    stderr="Error: something failed",
                    returncode=1,
                    error_kind="runtime_error",
                    started_at="2026-04-25T10:00:00+08:00",
                    finished_at="2026-04-25T10:00:15+08:00",
                )

                # Verify path
                self.assertEqual(log_path, logs_dir / "chunk_001.log")
                self.assertTrue(log_path.exists())

            content = log_path.read_text(encoding="utf-8")
            # Check header format
            self.assertIn("=== CHUNK 001 EXECUTION LOG ===", content)
            self.assertIn("Started: 2026-04-25T10:00:00+08:00", content)
            self.assertIn("Provider: codex", content)
            self.assertIn("Command: codex exec --full-auto", content)
            self.assertIn("CWD: /workspace", content)
            self.assertIn("Staging: /workspace/.agents/staging/chunk_001", content)
            self.assertIn("Prompt length: 13 characters", content)
            # Check output sections
            self.assertIn("--- STDOUT ---", content)
            self.assertIn("Output line 1", content)
            self.assertIn("--- STDERR ---", content)
            self.assertIn("Error: something failed", content)
            # Check tail metadata
            self.assertIn("--- END ---", content)
            self.assertIn("Returncode: 1", content)
            self.assertIn("Error kind: runtime_error", content)
            self.assertIn("Finished: 2026-04-25T10:00:15+08:00", content)

    def test_write_chunk_execution_log_retry_append(self) -> None:
        """Test that retry attempts append to existing log."""
        with tempfile.TemporaryDirectory() as tmp:
            logs_dir = Path(tmp) / "logs"
            logs_dir.mkdir(parents=True)

            with patch.object(run_fix_pipeline, "LOGS_DIR", logs_dir):
                # First attempt
                run_fix_pipeline.write_chunk_execution_log(
                    chunk_index=1,
                    attempt=1,
                    provider="codex",
                    command="codex exec",
                    cwd="/workspace",
                    staging_dir="/staging",
                    prompt="prompt",
                    stdout="first stdout",
                    stderr="first stderr",
                    returncode=1,
                    error_kind="network_error",
                    started_at="2026-04-25T10:00:00+08:00",
                    finished_at="2026-04-25T10:00:10+08:00",
                )

                # Second attempt (retry)
                run_fix_pipeline.write_chunk_execution_log(
                    chunk_index=1,
                    attempt=2,
                    provider="codex",
                    command="codex exec",
                    cwd="/workspace",
                    staging_dir="/staging",
                    prompt="prompt",
                    stdout="second stdout",
                    stderr="second stderr",
                    returncode=1,
                    error_kind="runtime_error",
                    started_at="2026-04-25T10:00:15+08:00",
                    finished_at="2026-04-25T10:00:25+08:00",
                )

                log_path = logs_dir / "chunk_001.log"

            content = log_path.read_text(encoding="utf-8")

            # Header should appear once
            self.assertEqual(content.count("=== CHUNK 001 EXECUTION LOG ==="), 1)
            # Attempt separator should appear
            self.assertIn("--- ATTEMPT 2 ---", content)
            # Both stdout/stderr pairs should be present
            self.assertIn("first stdout", content)
            self.assertIn("second stdout", content)
            # Both tail metadata blocks should be present
            self.assertEqual(content.count("--- END ---"), 2)
            self.assertEqual(content.count("Returncode:"), 2)

    def test_extract_error_summary_provider_keywords(self) -> None:
        """Test keyword matching for each provider."""
        # Codex quota error
        summary = run_fix_pipeline.extract_error_summary(
            stdout="Processing...\nERROR: You've hit your usage limit. Upgrade to Pro\nDone.",
            stderr="",
            provider="codex",
        )
        self.assertIn("usage limit", summary.lower())

        # Claude rate limit
        summary = run_fix_pipeline.extract_error_summary(
            stdout="API call failed\nRate limit exceeded. HTTP 429\n",
            stderr="",
            provider="claude",
        )
        self.assertIn("rate limit", summary.lower())

        # OpenAPI auth error
        summary = run_fix_pipeline.extract_error_summary(
            stdout="Starting...\nPOST https://opencode.ai/zen/v1/messages timed out\n",
            stderr="",
            provider="opencode",
        )
        self.assertIn("zen/v1/messages", summary.lower())

    def test_extract_error_summary_common_keywords(self) -> None:
        """Test common error keyword matching."""
        summary = run_fix_pipeline.extract_error_summary(
            stdout="Processing...\nFATAL: Connection lost\nERROR: Retry failed\n",
            stderr="",
            provider="codex",
        )
        # Should return up to 3 matching lines
        self.assertIn("FATAL", summary)
        self.assertIn("ERROR", summary)

    def test_extract_error_summary_fallback(self) -> None:
        """Test fallback to last 200 chars when no keywords match."""
        long_output = "A" * 300 + "END"
        summary = run_fix_pipeline.extract_error_summary(
            stdout=long_output,
            stderr="",
            provider="codex",
        )
        # Fallback returns last 200 chars of stdout (stripped)
        self.assertEqual(len(summary), 200)  # last 200 chars
        self.assertTrue(summary.endswith("END"))

    def test_extract_error_summary_stderr_combined(self) -> None:
        """Test that stderr is combined with stdout for search."""
        summary = run_fix_pipeline.extract_error_summary(
            stdout="Normal output here",
            stderr="ERROR: Failed to connect",
            provider="codex",
        )
        # Should find ERROR from stderr
        self.assertIn("ERROR", summary)

    def test_verbose_output_on_failure(self) -> None:
        """Test --verbose flag shows full stdout/stderr."""
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            logs_dir = runtime_dir / "logs"
            config_dir = Path(tmp) / "config"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()
            logs_dir.mkdir()
            config_dir.mkdir()

            common.save_json(runtime_dir / "progress.json", {
                "run_id": "test-verbose",
                "total_chunks": 1,
                "completed_chunks": [],
                "failed_chunks": [],
                "current_chunk": None,
                "fix_strategy": "conservative",
                "status": "ready",
            })
            common.save_json(chunks_dir / "chunk_001.json", {
                "chunk_index": 1,
                "chunk_total": 1,
                "issues": [{"rule_id": "test-rule"}],
            })
            common.save_json(config_dir / "pipeline.json", {
                "agent": {"provider": "opencode", "staging_dir": ".agents/staging"}
            })

            def fake_run_chunk_agent(config: dict, chunk: dict) -> dict:
                return {
                    "returncode": 1,
                    "stdout": "Verbose stdout output here",
                    "stderr": "Verbose stderr output here",
                    "error_kind": "test_error",
                    "prompt": "test",
                    "argv": ["opencode"],
                    "imported_paths": {},
                }

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
            ), patch.object(
                run_fix_pipeline, "run_chunk_agent", side_effect=fake_run_chunk_agent
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main(["--verbose"])

            self.assertEqual(rc, 0)
            output = stdout.getvalue()
            # Verbose output should include full stdout/stderr
            self.assertIn("=== CHUNK 001 STDOUT (verbose) ===", output)
            self.assertIn("Verbose stdout output here", output)
            self.assertIn("=== CHUNK 001 STDERR (verbose) ===", output)
            self.assertIn("Verbose stderr output here", output)


class ChunkIdParserTests(unittest.TestCase):
    def test_single_id(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["5"], 10)
        self.assertEqual(valid, [5])
        self.assertEqual(warnings, [])

    def test_range(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["3-7"], 10)
        self.assertEqual(valid, [3, 4, 5, 6, 7])
        self.assertEqual(warnings, [])

    def test_multiple_specs(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["3-5", "12"], 20)
        self.assertEqual(valid, [3, 4, 5, 12])
        self.assertEqual(warnings, [])

    def test_deduplication(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["3", "3", "2-4"], 10)
        self.assertEqual(valid, [2, 3, 4])
        self.assertEqual(warnings, [])

    def test_out_of_range_warning(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["999"], 10)
        self.assertEqual(valid, [])
        self.assertIn("999", warnings[0])

    def test_invalid_id_warning(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["abc"], 10)
        self.assertEqual(valid, [])
        self.assertIn("abc", warnings[0])

    def test_invalid_range_warning(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["1-abc"], 10)
        self.assertEqual(valid, [])
        self.assertIn("1-abc", warnings[0])

    def test_empty_specs(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs([], 10)
        self.assertEqual(valid, [])
        self.assertEqual(warnings, [])

    def test_all_valid_ids_out_of_range(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["5"], 4)
        self.assertEqual(valid, [])
        self.assertTrue(any("5" in w for w in warnings))

    def test_reversed_range(self):
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["7-3"], 10)
        self.assertEqual(valid, [3, 4, 5, 6, 7])
        self.assertEqual(warnings, [])

    def test_negative_id_warning(self):
        """Negative IDs like '-5' should report as invalid chunk-id, not as range."""
        valid, warnings = run_fix_pipeline.parse_chunk_id_specs(["-5"], 10)
        self.assertEqual(valid, [])
        self.assertIn("-5", warnings[0])
        self.assertIn("无效", warnings[0])

    def test_next_chunk_with_requested_ids_filters(self):
        progress = {
            "completed_chunks": [],
            "failed_chunks": [],
            "total_chunks": 10,
        }
        result = run_fix_pipeline.next_chunk(
            progress, set(), False, False, requested_ids=[3, 5, 7]
        )
        self.assertEqual(result, 3)

    def test_next_chunk_with_requested_ids_skips_done(self):
        progress = {
            "completed_chunks": [3, 5],
            "failed_chunks": [],
            "total_chunks": 10,
        }
        result = run_fix_pipeline.next_chunk(
            progress, set(), False, False, requested_ids=[3, 5, 7]
        )
        self.assertEqual(result, 7)

    def test_next_chunk_with_no_requested_ids_returns_all(self):
        progress = {
            "completed_chunks": [],
            "failed_chunks": [],
            "total_chunks": 5,
        }
        result = run_fix_pipeline.next_chunk(
            progress, set(), False, False, requested_ids=None
        )
        self.assertEqual(result, 1)

    def test_next_chunk_with_empty_requested_ids_returns_first(self):
        progress = {
            "completed_chunks": [],
            "failed_chunks": [],
            "total_chunks": 5,
        }
        result = run_fix_pipeline.next_chunk(
            progress, set(), False, False, requested_ids=[]
        )
        self.assertEqual(result, 1)

    def test_next_chunk_with_requested_ids_skips_failed_silently(self):
        """Failed chunks are skipped silently in next_chunk; hint is printed in main()."""
        progress = {
            "completed_chunks": [],
            "failed_chunks": [5],
            "total_chunks": 10,
        }
        result = run_fix_pipeline.next_chunk(
            progress, set(), False, False, requested_ids=[5]
        )
        self.assertIsNone(result)

    def test_run_with_chunk_id_single(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            logs_dir = runtime_dir / "logs"
            config_dir = Path(tmp) / "config"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()
            logs_dir.mkdir()
            config_dir.mkdir()

            common.save_json(runtime_dir / "progress.json", {
                "run_id": "test-chunk-id",
                "total_chunks": 3,
                "completed_chunks": [],
                "failed_chunks": [],
                "current_chunk": None,
                "fix_strategy": "conservative",
                "status": "ready",
            })
            common.save_json(chunks_dir / "chunk_002.json", {
                "chunk_index": 2,
                "chunk_total": 3,
                "issues": [{"rule_id": "misra-c2012-1.1", "is_misra": True}],
            })
            common.save_json(config_dir / "pipeline.json", {
                "agent": {"provider": "opencode", "staging_dir": ".agents/staging"}
            })

            def fake_run(config, chunk):
                result_path = results_dir / f"chunk_{chunk['chunk_index']:03d}_result.json"
                common.save_json(result_path, {"chunk_index": chunk["chunk_index"]})
                return {
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "error_kind": "",
                    "prompt": "",
                    "argv": ["opencode"],
                    "imported_paths": {"chunk_result_json_path": result_path},
                }

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
            ), patch.object(
                run_fix_pipeline, "run_chunk_agent", side_effect=fake_run
            ), patch.object(
                run_fix_pipeline, "verify_chunk_result", return_value={"passed": True, "mode": "light"}
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main(["--chunk-id", "2"])

            self.assertEqual(rc, 0)
            output = stdout.getvalue()
            self.assertIn("正在处理 chunk 2/3", output)
            self.assertIn("指定的 chunk-id", output)

    def test_run_with_chunk_id_sets_partial_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            logs_dir = runtime_dir / "logs"
            config_dir = Path(tmp) / "config"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()
            logs_dir.mkdir()
            config_dir.mkdir()

            common.save_json(runtime_dir / "progress.json", {
                "run_id": "test-partial-status",
                "total_chunks": 3,
                "completed_chunks": [],
                "failed_chunks": [],
                "current_chunk": None,
                "fix_strategy": "conservative",
                "status": "ready",
            })
            common.save_json(chunks_dir / "chunk_002.json", {
                "chunk_index": 2,
                "chunk_total": 3,
                "issues": [{"rule_id": "misra-c2012-1.1", "is_misra": True}],
            })
            common.save_json(config_dir / "pipeline.json", {
                "agent": {"provider": "opencode", "staging_dir": ".agents/staging"}
            })

            def fake_run(config, chunk):
                result_path = results_dir / f"chunk_{chunk['chunk_index']:03d}_result.json"
                common.save_json(result_path, {"chunk_index": chunk["chunk_index"]})
                return {
                    "returncode": 0,
                    "stdout": "",
                    "stderr": "",
                    "error_kind": "",
                    "prompt": "",
                    "argv": ["opencode"],
                    "imported_paths": {"chunk_result_json_path": result_path},
                }

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
            ), patch.object(
                run_fix_pipeline, "run_chunk_agent", side_effect=fake_run
            ), patch.object(
                run_fix_pipeline, "verify_chunk_result", return_value={"passed": True, "mode": "light"}
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main(["--chunk-id", "2"])

            self.assertEqual(rc, 0)
            progress = common.load_json(runtime_dir / "progress.json", {})
            self.assertEqual(progress["status"], "partial")

    def test_completed_chunk_not_rerun_with_chunk_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            logs_dir = runtime_dir / "logs"
            config_dir = Path(tmp) / "config"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()
            logs_dir.mkdir()
            config_dir.mkdir()

            common.save_json(runtime_dir / "progress.json", {
                "run_id": "test-completed-skip",
                "total_chunks": 3,
                "completed_chunks": [1, 2, 3],
                "failed_chunks": [],
                "current_chunk": None,
                "fix_strategy": "conservative",
                "status": "running",
            })
            common.save_json(config_dir / "pipeline.json", {
                "agent": {"provider": "opencode", "staging_dir": ".agents/staging"}
            })

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main(["--chunk-id", "2"])

            self.assertEqual(rc, 0)
            output = stdout.getvalue()
            self.assertIn("指定的 chunk-id", output)

    def test_run_with_chunk_id_prints_failed_hint(self):
        """main() 一性打印 failed-chunk 提示，而非 next_chunk 循环内重复打印。"""
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp) / "runtime"
            results_dir = runtime_dir / "results"
            chunks_dir = runtime_dir / "chunks"
            logs_dir = runtime_dir / "logs"
            config_dir = Path(tmp) / "config"
            runtime_dir.mkdir(parents=True)
            results_dir.mkdir()
            chunks_dir.mkdir()
            logs_dir.mkdir()
            config_dir.mkdir()

            common.save_json(runtime_dir / "progress.json", {
                "run_id": "test-failed-hint",
                "total_chunks": 3,
                "completed_chunks": [],
                "failed_chunks": [2],
                "current_chunk": None,
                "fix_strategy": "conservative",
                "status": "ready",
            })
            common.save_json(config_dir / "pipeline.json", {
                "agent": {"provider": "opencode", "staging_dir": ".agents/staging"}
            })

            stdout = io.StringIO()
            with patch.object(run_fix_pipeline, "RUNTIME_DIR", runtime_dir), patch.object(
                run_fix_pipeline, "RESULTS_DIR", results_dir
            ), patch.object(
                run_fix_pipeline, "LOGS_DIR", logs_dir
            ), patch.object(
                run_fix_pipeline, "CONFIG_DIR", config_dir
            ), redirect_stdout(stdout):
                rc = run_fix_pipeline.main(["--chunk-id", "2"])

            self.assertEqual(rc, 0)
            output = stdout.getvalue()
            self.assertIn("使用 --include-failed 可重跑", output)


if __name__ == "__main__":
    unittest.main()
