# `--chunk-id` 支持实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `run_fix_pipeline.py`、`oneshot.py` 和 `misra-pipeline-cli.py` 添加 `--chunk-id` 参数，支持仅运行指定 chunk。

**Architecture:** 在三层（核心管道 → 一次性入口 → CLI）逐层添加参数解析和转发。核心逻辑在 `run_fix_pipeline.py` 的 `parse_chunk_id_specs` 和修改后的 `next_chunk` 中实现；`oneshot.py` 和 CLI 仅做参数转发。

**Tech Stack:** Python 3.8+，argparse，unittest

---

### Task 1: 在 `run_fix_pipeline.py` 中添加 `parse_chunk_id_specs` 函数

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:5` (imports)
- Modify: `.agents/tools/run_fix_pipeline.py:155-156` (在 `normalize_rule_set` 之后)

- [ ] **Step 1: 添加 `Tuple` 导入**

在 `.agents/tools/run_fix_pipeline.py` 第 5 行，将 `from typing import Iterable, List, Optional, Set` 改为 `from typing import Iterable, List, Optional, Set, Tuple`。

- [ ] **Step 2: 在 `normalize_rule_set` 之后添加 `parse_chunk_id_specs` 函数**

在 `.agents/tools/run_fix_pipeline.py` 第 157 行（`normalize_rule_set` 函数之后）插入：

```python
def parse_chunk_id_specs(specs: Iterable[str], total: int) -> Tuple[List[int], List[str]]:
    """Parse --chunk-id specs into (sorted unique valid ids, warnings)."""
    valid: Set[int] = set()
    warnings: List[str] = []
    for raw in specs:
        token = (raw or "").strip()
        if not token:
            continue
        if "-" in token and not token.startswith("-"):
            parts = token.split("-", 1)
            try:
                lo, hi = int(parts[0]), int(parts[1])
            except ValueError:
                warnings.append(f"忽略无效 chunk-id 范围: '{token}'")
                continue
            if lo > hi:
                lo, hi = hi, lo
            for i in range(lo, hi + 1):
                if 1 <= i <= total:
                    valid.add(i)
                else:
                    warnings.append(f"chunk-id {i} 超出范围 (1..{total})，已跳过")
        else:
            try:
                i = int(token)
            except ValueError:
                warnings.append(f"忽略无效 chunk-id: '{token}'")
                continue
            if 1 <= i <= total:
                valid.add(i)
            else:
                warnings.append(f"chunk-id {i} 超出范围 (1..{total})，已跳过")
    return sorted(valid), warnings
```

- [ ] **Step 3: 运行现有测试确认无回归**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_run_pipeline.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat(pipeline): add parse_chunk_id_specs helper function"
```

---

### Task 2: 修改 `next_chunk` 函数以支持 `requested_ids` 过滤

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:191-204` (`next_chunk` 函数)

- [ ] **Step 1: 修改 `next_chunk` 签名和逻辑**

将当前函数：

```python
def next_chunk(progress: dict, selected_rules: Set[str], misra_only: bool, include_failed: bool) -> Optional[int]:
    done = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))
    total = int(progress.get("total_chunks", 0))

    for idx in range(1, total + 1):
        if idx in done:
            continue
        if not include_failed and idx in failed:
            continue
        if not chunk_matches_filters(idx, selected_rules, misra_only):
            continue
        return idx
    return None
```

替换为：

```python
def next_chunk(progress: dict, selected_rules: Set[str], misra_only: bool, include_failed: bool, requested_ids: Optional[List[int]] = None) -> Optional[int]:
    done = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))
    total = int(progress.get("total_chunks", 0))

    candidates = requested_ids if requested_ids else range(1, total + 1)
    for idx in candidates:
        if idx in done:
            continue
        if not include_failed and idx in failed:
            continue
        if not chunk_matches_filters(idx, selected_rules, misra_only):
            continue
        return idx
    return None
```

注意：failed chunk 的提示信息不在 `next_chunk` 内打印（避免循环中重复），而是在 `main()` 的预处理阶段一次性输出所有 failed chunk 提示。

- [ ] **Step 2: 运行现有测试确认无回归**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_run_pipeline.py -v`
Expected: 全部 PASS（`requested_ids` 默认 `None`，行为不变）

---

### Task 3: 在 `parse_args` 中添加 `--chunk-id` 参数

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:100-152` (`parse_args` 函数)

- [ ] **Step 1: 在 `--include-failed` 参数之后添加 `--chunk-id`**

在 `.agents/tools/run_fix_pipeline.py` 的 `parse_args` 函数内，在 `--include-failed` 参数块（约第 133-137 行）之后，添加：

```python
    parser.add_argument(
        "--chunk-id",
        action="append",
        default=[],
        help=(
            "Only run specific chunk(s). Accepts single id (e.g. 5) or range "
            "(e.g. 3-7). Can be specified multiple times. Unknown ids are warned "
            "and skipped."
        ),
    )
```

- [ ] **Step 2: 运行测试确认参数解析正确**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -c "import sys; sys.path.insert(0, '.agents/tools'); from run_fix_pipeline import parse_args; args = parse_args(['--chunk-id', '5', '--chunk-id', '3-7']); print('chunk_id:', args.chunk_id)"`
Expected: 输出 `chunk_id: ['5', '3-7']`

---

### Task 4: 在 `main()` 中集成 `--chunk-id` 逻辑

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:226-442` (`main` 函数)

- [ ] **Step 1: 在加载 `progress` 后、设置 `last_run_filters` 前注入解析、告警与 failed-chunk 提示**

在 `main()` 函数中，`progress = load_json(progress_path, {})` 之后、`progress["status"] = "running"` 之前，插入：

```python
    total_chunks_for_parse = int(progress.get("total_chunks", 0))
    requested_ids, chunk_id_warnings = parse_chunk_id_specs(
        args.chunk_id, total_chunks_for_parse
    )
    for w in chunk_id_warnings:
        print(f"[run] 警告: {w}")
    # 一次性输出 failed-chunk 提示，避免循环中重复打印
    if requested_ids:
        failed_set = set(progress.get("failed_chunks", []))
        for rid in requested_ids:
            if rid in failed_set and not args.include_failed:
                print(f"[run] chunk {rid} 在 failed_chunks 中，使用 --include-failed 可重跑")
    if args.chunk_id and not requested_ids:
        print("[run] 未提供任何有效 chunk-id，未执行 agent 阶段。"
              "如已完成所有 chunk，可继续：misra-pipeline run --stage merge")
        return 0
```

- [ ] **Step 2: 在 `last_run_filters` 中添加 `chunk_ids` 字段**

将现有的 `progress["last_run_filters"]` 字典添加一行 `"chunk_ids": requested_ids or None,`。修改后如下：

```python
    progress["last_run_filters"] = {
        "max_chunks": args.max_chunks,
        "retry_failed": args.retry_failed,
        "rule_ids": sorted(selected_rules),
        "misra_only": args.misra_only,
        "include_failed": args.include_failed,
        "strategy": requested_strategy,
        "chunk_ids": requested_ids or None,
    }
```

- [ ] **Step 3: 在 `run_started` 事件的 `data.filters` 中带上 `chunk_ids`**

在 `run_started` 事件的 `data` 字典中也添加 `"chunk_ids": requested_ids or None`。找到 `append_pipeline_event` 调用中 `event="run_started"` 对应的 `data` 字典，确保包含 chunk_ids。

- [ ] **Step 4: 修改 `next_chunk` 调用传入 `requested_ids`**

在 while 循环中，将：
```python
        idx = next_chunk(progress, selected_rules, args.misra_only, args.include_failed)
```
改为：
```python
        idx = next_chunk(progress, selected_rules, args.misra_only, args.include_failed, requested_ids)
```

- [ ] **Step 5: 修改 `idx is None` 分支的提示逻辑**

将当前的 `idx is None` 分支：

```python
        if idx is None:
            progress["status"] = "done"
            save_json(progress_path, progress)
            append_pipeline_event(
                RUNTIME_DIR,
                event="run_completed",
                stage="run",
                message="run 阶段已完成，无可处理 chunk。",
                data={
                    "processed": processed_this_run,
                    "completed_chunks": len(progress.get("completed_chunks", [])),
                    "failed_chunks": len(progress.get("failed_chunks", [])),
                },
            )
            print("No more eligible chunks to process.")
            return 0
```

替换为：

```python
        if idx is None:
            progress["status"] = "partial" if requested_ids else "done"
            save_json(progress_path, progress)
            if requested_ids:
                print(f"[run] 指定的 chunk-id {requested_ids} 已全部处理完毕（或被过滤跳过）。")
                print("[run] 如需汇总报告，请继续：misra-pipeline run --stage merge")
            else:
                print("No more eligible chunks to process.")
            append_pipeline_event(
                RUNTIME_DIR,
                event="run_completed",
                stage="run",
                message="run 阶段已完成，无可处理 chunk。",
                data={
                    "processed": processed_this_run,
                    "completed_chunks": len(progress.get("completed_chunks", [])),
                    "failed_chunks": len(progress.get("failed_chunks", [])),
                },
            )
            return 0
```

关键变更：`status` 设为 `"partial"` 而非 `"running"`，复用现有 `--max-chunks` 截断时的语义。

- [ ] **Step 6: 运行现有测试确认无回归**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_run_pipeline.py -v`
Expected: 全部 PASS（默认 `requested_ids=[]`，`parse_chunk_id_specs([], total)` 返回 `([], [])`，行为不变）

- [ ] **Step 7: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat(pipeline): integrate --chunk-id into main loop and next_chunk"
```

---

### Task 5: 为 `run_fix_pipeline.py` 添加 `--chunk-id` 单元测试

**Files:**
- Modify: `tests/test_run_pipeline.py`

- [ ] **Step 0: 确认 imports 齐全**

在 `tests/test_run_pipeline.py` 顶部确认已有以下导入，缺失则补上：

```python
import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
```

在 `tests/test_run_pipeline.py` 末尾（`class ExecutionLogTests` 之后）添加新测试类：

```python
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
```

- [ ] **Step 2: 运行全部 run_pipeline 测试**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_run_pipeline.py -v`
Expected: 全部 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_run_pipeline.py
git commit -m "test(pipeline): add tests for --chunk-id parsing, filtering, and status"
```

---

### Task 6: 在 `oneshot.py` 中转发 `--chunk-id` 参数

**Files:**
- Modify: `.agents/tools/oneshot.py:32-46` (`parse_args`)
- Modify: `.agents/tools/oneshot.py:187-203` (`build_run_args`)

- [ ] **Step 1: 在 `parse_args` 中添加 `--chunk-id` 参数**

在 `.agents/tools/oneshot.py` 的 `parse_args` 函数中，`--include-failed` 之后添加：

```python
    parser.add_argument("--chunk-id", action="append", default=[],
                        help="Run only this chunk id or range (e.g. 5 or 3-7). Repeatable.")
```

- [ ] **Step 2: 在 `build_run_args` 中转发 `--chunk-id`**

在 `build_run_args` 函数（约第 187-203 行）末尾、`return stage_args` 之前添加：

```python
    for cid in getattr(args, "chunk_id", []) or []:
        stage_args.extend(["--chunk-id", cid])
```

- [ ] **Step 3: 运行现有 oneshot 测试确认无回归**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_oneshot.py -v`
Expected: 全部 PASS

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/oneshot.py
git commit -m "feat(oneshot): forward --chunk-id to run_fix_pipeline"
```

---

### Task 7: 在 `misra-pipeline-cli.py` 中添加 `--chunk-id` 参数

**Files:**
- Modify: `cli/misra-pipeline-cli.py:240-260` (`run` 子命令定义区)
- Modify: `cli/misra-pipeline-cli.py:1053-1073` (`cmd_run` 中 `--stage agent` 的参数转发)
- Modify: `cli/misra-pipeline-cli.py:1124-1146` (`cmd_run` 中 oneshot 全流模式的参数转发)

- [ ] **Step 1: 在 `run_parser` 中添加 `--chunk-id` 参数**

在 `cli/misra-pipeline-cli.py` 的 `run_parser` 定义中（约第 252 行 `--include-failed` 之后），添加：

```python
    run_parser.add_argument("--chunk-id", action="append", default=[],
                            help="Run only this chunk id or range (e.g. 5 or 3-7). Repeatable.")
```

- [ ] **Step 2: 在 `cmd_run` 的 `--stage agent` 分支中转发 `--chunk-id`**

在 `cmd_run` 函数中 `elif args.stage == "agent":` 块（约第 1059-1073 行）的末尾、`if args.verbose:` 之前添加：

```python
            for cid in args.chunk_id:
                stage_args.extend(["--chunk-id", cid])
```

- [ ] **Step 3: 在 `cmd_run` 的 oneshot 全流模式中转发 `--chunk-id`**

在 `cmd_run` 函数中全流模式的 `oneshot_argv` 构建（约第 1124-1146 行）的 `if args.include_failed:` 块之后添加：

```python
    for cid in args.chunk_id:
        oneshot_argv.extend(["--chunk-id", cid])
```

- [ ] **Step 4: 运行 CLI 测试确认无回归**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_misra_pipeline_cli.py -v`
Expected: 全部 PASS

- [ ] **Step 5: 添加 `--chunk-id` 参数解析测试**

在 `tests/test_misra_pipeline_cli.py` 的 `MisraPipelineCliTests` 类中添加：

```python
    def test_parse_args_run_with_chunk_id(self):
        """Test parse_args for 'run --chunk-id 5'."""
        args = misra_pipeline_cli.parse_args(["run", "--chunk-id", "5"])
        self.assertEqual(args.subcommand, "run")
        self.assertEqual(args.chunk_id, ["5"])

    def test_parse_args_run_with_chunk_id_range(self):
        """Test parse_args for 'run --chunk-id 3-7 --chunk-id 12'."""
        args = misra_pipeline_cli.parse_args(["run", "--chunk-id", "3-7", "--chunk-id", "12"])
        self.assertEqual(args.chunk_id, ["3-7", "12"])
```

- [ ] **Step 6: 运行新增测试**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineCliTests::test_parse_args_run_with_chunk_id tests/test_misra_pipeline_cli.py::MisraPipelineCliTests::test_parse_args_run_with_chunk_id_range -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): add --chunk-id to run subcommand and forward to pipeline"
```

---

### Task 8: 运行全量测试

- [ ] **Step 1: 运行所有相关测试**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python -m pytest tests/test_run_pipeline.py tests/test_oneshot.py tests/test_misra_pipeline_cli.py -v`
Expected: 全部 PASS

- [ ] **Step 2: 手动验证参数帮助信息**

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python .agents/tools/run_fix_pipeline.py --help`
Expected: 输出中包含 `--chunk-id` 参数及其帮助文本

Run: `cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2 && python cli/misra-pipeline-cli.py run --help`
Expected: 输出中包含 `--chunk-id` 参数及其帮助文本