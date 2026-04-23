# Pipeline Review Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a low-risk usability layer for the cppcheck/MISRA pipeline: `oneshot`, `doctor`, Chinese review reports, date-based run archives, logs, and skill guidance that avoids stalled workflows.

**Architecture:** Keep the existing `split -> run -> merge` flow intact. Add shared helpers in `common.py`, create focused `doctor.py` and `oneshot.py` modules, extend `merge_results.py` for Chinese review output and archive copying, and update prompts/docs without changing chunk JSON structure.

**Tech Stack:** Python 3 standard library, `unittest`, existing `.agents/tools` scripts, Markdown reports, JSON/JSONL runtime files.

---

## File Structure

- Modify `.agents/tools/common.py`: shared config validation, run ID generation, log helpers, archive copy helpers.
- Create `.agents/tools/doctor.py`: environment/config/runtime diagnostics for users.
- Create `.agents/tools/oneshot.py`: orchestrates `split`, `run`, and `merge` with clear progress messages.
- Modify `.agents/tools/pipeline_cli.py`: add `doctor` and `oneshot` commands only. Do not add `docter`.
- Modify `.agents/tools/split_cppcheck_xml.py`: create/store `run_id`, clear current runtime logs, record split start/end events.
- Modify `.agents/tools/run_fix_pipeline.py`: print chunk progress and log stage/chunk events.
- Modify `.agents/tools/merge_results.py`: generate Chinese review reports and archive current run.
- Modify `.agents/prompts/fix_chunk_prompt.txt`: instruct agent to record blockers instead of stalling when sandbox/environment issues occur.
- Modify `.agents/skills/cppcheck-misra-fix/SKILL.md`: mirror the blocker/continue workflow.
- Modify `README.md`: document `oneshot`, `doctor`, reports, archives, and logs.
- Create `tests/test_common_runtime.py`: run ID, config validation, logging, archive helpers.
- Create `tests/test_doctor.py`: XML/config/runtime diagnostics.
- Create `tests/test_reports_archive.py`: Chinese report content and archive layout.
- Create `tests/test_pipeline_cli.py`: command map includes `doctor`/`oneshot` and excludes `docter`.

---

### Task 1: Shared Runtime Helpers

**Files:**
- Modify: `.agents/tools/common.py`
- Test: `tests/test_common_runtime.py`

- [ ] **Step 1: Write failing tests for run IDs, config validation, logging, and archive copy**

Create `tests/test_common_runtime.py`:

```python
import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".agents" / "tools"
sys.path.insert(0, str(TOOLS))

import common


class CommonRuntimeTests(unittest.TestCase):
    def test_next_run_id_increments_for_existing_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            (runs_dir / "20260423-001").mkdir()
            (runs_dir / "20260423-002").mkdir()

            now = datetime(2026, 4, 23, 9, 30, tzinfo=timezone(timedelta(hours=8)))

            self.assertEqual(common.next_run_id(runs_dir, now), "20260423-003")

    def test_next_run_id_ignores_other_dates_and_invalid_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp)
            (runs_dir / "20260422-009").mkdir()
            (runs_dir / "notes").mkdir()

            now = datetime(2026, 4, 23, 9, 30, tzinfo=timezone(timedelta(hours=8)))

            self.assertEqual(common.next_run_id(runs_dir, now), "20260423-001")

    def test_validate_pipeline_config_reports_missing_required_path(self):
        errors, warnings = common.validate_pipeline_config({"input": {}})

        self.assertIn("缺少配置项: input.cppcheck_xml", errors)
        self.assertEqual(warnings, [])

    def test_append_pipeline_log_writes_text_and_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime_dir = Path(tmp)

            common.append_pipeline_log(
                runtime_dir,
                stage="split",
                message="正在拆分 XML",
                level="info",
                data={"strategy": "conservative"},
            )

            text = (runtime_dir / "pipeline.log").read_text(encoding="utf-8")
            event = json.loads((runtime_dir / "run_log.jsonl").read_text(encoding="utf-8"))

            self.assertIn("正在拆分 XML", text)
            self.assertEqual(event["stage"], "split")
            self.assertEqual(event["data"]["strategy"], "conservative")

    def test_copy_current_run_archive_copies_expected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runtime_dir = base / "runtime"
            reports_dir = base / "reports"
            archive_dir = base / "runs" / "20260423-001"
            (runtime_dir / "chunks").mkdir(parents=True)
            (runtime_dir / "results").mkdir()
            reports_dir.mkdir()
            (runtime_dir / "progress.json").write_text("{}", encoding="utf-8")
            (runtime_dir / "pipeline.log").write_text("log", encoding="utf-8")
            (runtime_dir / "run_log.jsonl").write_text("{}", encoding="utf-8")
            (reports_dir / "final_summary.md").write_text("# 汇总\n", encoding="utf-8")

            common.copy_current_run_archive(runtime_dir, reports_dir, archive_dir)

            self.assertTrue((archive_dir / "runtime" / "progress.json").exists())
            self.assertTrue((archive_dir / "reports" / "final_summary.md").exists())
            self.assertTrue((archive_dir / "logs" / "pipeline.log").exists())
            self.assertTrue((archive_dir / "logs" / "run_log.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_common_runtime -v
```

Expected: FAIL because `next_run_id`, `validate_pipeline_config`, `append_pipeline_log`, and `copy_current_run_archive` do not exist.

- [ ] **Step 3: Implement shared helpers in `.agents/tools/common.py`**

Add imports:

```python
import re
import shutil
from datetime import datetime, timezone, timedelta
```

Add constants near the existing directory constants:

```python
RUNS_DIR = AGENTS_DIR / "runs"
TZ = timezone(timedelta(hours=8))
RUN_ID_RE = re.compile(r"^(?P<date>\d{8})-(?P<seq>\d{3})$")
```

Update `ensure_dirs()` to include `RUNS_DIR`.

Add these functions:

```python
def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def next_run_id(runs_dir: Path = RUNS_DIR, now: Optional[datetime] = None) -> str:
    current = now or datetime.now(TZ)
    prefix = current.astimezone(TZ).strftime("%Y%m%d")
    max_seq = 0
    if runs_dir.exists():
        for path in runs_dir.iterdir():
            if not path.is_dir():
                continue
            match = RUN_ID_RE.match(path.name)
            if not match or match.group("date") != prefix:
                continue
            max_seq = max(max_seq, int(match.group("seq")))
    return f"{prefix}-{max_seq + 1:03d}"


def validate_pipeline_config(config: Dict[str, Any]) -> tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    required = [
        ("input.cppcheck_xml", str),
        ("chunking.max_issues_per_chunk", int),
        ("chunking.max_files_per_chunk", int),
        ("filter.include_severity", list),
        ("misra.detect_prefixes", list),
        ("fix_strategy.mode", str),
        ("verification.mode", str),
        ("agent.command", str),
    ]

    for dotted, expected_type in required:
        value: Any = config
        for part in dotted.split("."):
            if not isinstance(value, dict) or part not in value:
                errors.append(f"缺少配置项: {dotted}")
                value = None
                break
            value = value[part]
        if value is None:
            continue
        if not isinstance(value, expected_type):
            errors.append(f"配置项类型错误: {dotted} 应为 {expected_type.__name__}")

    mode = config.get("fix_strategy", {}).get("mode")
    if mode is not None and mode not in {"conservative", "all_auto"}:
        errors.append("配置项取值错误: fix_strategy.mode 只能是 conservative 或 all_auto")

    chunking = config.get("chunking", {})
    for key in ["max_issues_per_chunk", "max_files_per_chunk"]:
        value = chunking.get(key)
        if isinstance(value, int) and value <= 0:
            errors.append(f"配置项取值错误: chunking.{key} 必须大于 0")

    custom_command = str(config.get("verification", {}).get("custom_command", "")).strip()
    if custom_command:
        warnings.append("已配置自定义验证命令，运行前请确认该命令不会泄露敏感信息")

    return errors, warnings


def append_pipeline_log(
    runtime_dir: Path,
    stage: str,
    message: str,
    level: str = "info",
    data: Optional[Dict[str, Any]] = None,
) -> None:
    runtime_dir.mkdir(parents=True, exist_ok=True)
    event = {
        "time": now_iso(),
        "level": level,
        "stage": stage,
        "message": message,
        "data": data or {},
    }
    with open(runtime_dir / "pipeline.log", "a", encoding="utf-8") as f:
        f.write(f"{event['time']} [{level}] {stage}: {message}\n")
    append_jsonl(runtime_dir / "run_log.jsonl", event)


def reset_runtime_logs(runtime_dir: Path = RUNTIME_DIR) -> None:
    for name in ["pipeline.log", "run_log.jsonl"]:
        path = runtime_dir / name
        if path.exists():
            path.unlink()


def copy_current_run_archive(runtime_dir: Path, reports_dir: Path, archive_dir: Path) -> None:
    if archive_dir.exists():
        shutil.rmtree(archive_dir)
    (archive_dir / "runtime").mkdir(parents=True, exist_ok=True)
    (archive_dir / "reports").mkdir(parents=True, exist_ok=True)
    (archive_dir / "logs").mkdir(parents=True, exist_ok=True)

    for name in ["issues_master.json", "issue_status.json", "file_change_index.json", "progress.json"]:
        src = runtime_dir / name
        if src.exists():
            shutil.copy2(src, archive_dir / "runtime" / name)

    for dirname in ["chunks", "results"]:
        src_dir = runtime_dir / dirname
        if src_dir.exists():
            shutil.copytree(src_dir, archive_dir / "runtime" / dirname)

    if reports_dir.exists():
        for path in reports_dir.iterdir():
            if path.is_file():
                shutil.copy2(path, archive_dir / "reports" / path.name)

    for name in ["pipeline.log", "run_log.jsonl"]:
        src = runtime_dir / name
        if src.exists():
            shutil.copy2(src, archive_dir / "logs" / name)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_common_runtime -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .agents/tools/common.py tests/test_common_runtime.py
git commit -m "feat: add pipeline runtime helpers"
```

---

### Task 2: Doctor Command

**Files:**
- Create: `.agents/tools/doctor.py`
- Modify: `.agents/tools/pipeline_cli.py`
- Test: `tests/test_doctor.py`
- Test: `tests/test_pipeline_cli.py`

- [ ] **Step 1: Write failing tests for diagnostics and CLI command map**

Create `tests/test_doctor.py`:

```python
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".agents" / "tools"
sys.path.insert(0, str(TOOLS))

import doctor


class DoctorTests(unittest.TestCase):
    def test_check_cppcheck_xml_rejects_plain_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            xml_path = Path(tmp) / "cppcheck_misra.xml"
            xml_path.write_text("Checking file.c ...\n1/1 files checked 100% done\n", encoding="utf-8")

            results = doctor.check_cppcheck_xml(xml_path)

            self.assertEqual(results[0]["level"], "error")
            self.assertIn("不是合法的 cppcheck XML", results[0]["message"])

    def test_check_runtime_strategy_warns_on_mismatch(self):
        config = {"fix_strategy": {"mode": "conservative"}}
        progress = {"fix_strategy": "all_auto"}

        results = doctor.check_runtime_strategy(config, progress)

        self.assertEqual(results[0]["level"], "warning")
        self.assertIn("策略不一致", results[0]["message"])

    def test_has_blockers_detects_error(self):
        results = [
            {"level": "ok", "message": "ok"},
            {"level": "error", "message": "bad"},
        ]

        self.assertTrue(doctor.has_blockers(results))
```

Create `tests/test_pipeline_cli.py`:

```python
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".agents" / "tools"
sys.path.insert(0, str(TOOLS))

import pipeline_cli


class PipelineCliTests(unittest.TestCase):
    def test_cli_exposes_doctor_and_oneshot_without_misspelled_alias(self):
        self.assertIn("doctor", pipeline_cli.COMMANDS)
        self.assertIn("oneshot", pipeline_cli.COMMANDS)
        self.assertNotIn("docter", pipeline_cli.COMMANDS)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_doctor tests.test_pipeline_cli -v
```

Expected: FAIL because `doctor.py` and `oneshot` CLI command do not exist.

- [ ] **Step 3: Implement `.agents/tools/doctor.py`**

Create `.agents/tools/doctor.py`:

```python
from __future__ import annotations

import argparse
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

from common import CONFIG_DIR, RUNTIME_DIR, load_json, validate_pipeline_config


CheckResult = Dict[str, str]


def result(level: str, message: str) -> CheckResult:
    return {"level": level, "message": message}


def check_cppcheck_xml(xml_path: Path) -> List[CheckResult]:
    if not xml_path.exists():
        return [result("error", f"找不到 cppcheck XML 文件: {xml_path}")]
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as exc:
        return [result("error", f"不是合法的 cppcheck XML 文件: {xml_path} ({exc})")]
    root = tree.getroot()
    errors = root.findall(".//error")
    if not errors:
        return [result("warning", f"XML 中没有 <error> 节点: {xml_path}")]
    return [result("ok", f"cppcheck XML 可读取，发现 {len(errors)} 个问题节点")]


def check_config(config: Dict[str, Any]) -> List[CheckResult]:
    errors, warnings = validate_pipeline_config(config)
    items = [result("error", item) for item in errors]
    items.extend(result("warning", item) for item in warnings)
    if not items:
        items.append(result("ok", "pipeline.json 配置检查通过"))
    return items


def check_agent_command(config: Dict[str, Any]) -> List[CheckResult]:
    command = str(config.get("agent", {}).get("command", "")).strip()
    if not command:
        return [result("error", "缺少 agent.command 配置")]
    if shutil.which(command) is None:
        return [result("error", f"找不到 agent 命令: {command}")]
    return [result("ok", f"agent 命令可执行: {command}")]


def check_runtime_strategy(config: Dict[str, Any], progress: Dict[str, Any]) -> List[CheckResult]:
    if not progress:
        return [result("ok", "尚未生成 runtime/progress.json")]
    config_strategy = config.get("fix_strategy", {}).get("mode", "conservative")
    runtime_strategy = progress.get("fix_strategy")
    if runtime_strategy and runtime_strategy != config_strategy:
        return [
            result(
                "warning",
                f"runtime 策略不一致: progress={runtime_strategy}, config={config_strategy}。建议重新执行 split。",
            )
        ]
    return [result("ok", "runtime 策略与配置一致")]


def collect_checks() -> List[CheckResult]:
    config = load_json(CONFIG_DIR / "pipeline.json", {})
    progress = load_json(RUNTIME_DIR / "progress.json", {})
    xml_path = Path(str(config.get("input", {}).get("cppcheck_xml", "cppcheck.xml")))

    checks: List[CheckResult] = []
    checks.extend(check_config(config))
    checks.extend(check_cppcheck_xml(xml_path))
    checks.extend(check_agent_command(config))
    checks.extend(check_runtime_strategy(config, progress))
    return checks


def has_blockers(checks: List[CheckResult]) -> bool:
    return any(item.get("level") == "error" for item in checks)


def print_checks(checks: List[CheckResult]) -> None:
    label = {"ok": "通过", "warning": "警告", "error": "错误"}
    for item in checks:
        level = item.get("level", "info")
        print(f"[{label.get(level, level)}] {item.get('message', '')}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查 cppcheck/MISRA pipeline 运行环境。")
    return parser.parse_args()


def main() -> None:
    parse_args()
    checks = collect_checks()
    print_checks(checks)
    if has_blockers(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Wire `doctor` and `oneshot` in `.agents/tools/pipeline_cli.py`**

Modify `COMMANDS`:

```python
COMMANDS = {
    "split": ("split_cppcheck_xml", "Split cppcheck XML into runtime chunks."),
    "run": ("run_fix_pipeline", "Run the agent fixing pipeline."),
    "merge": ("merge_results", "Merge runtime results into reports."),
    "verify": ("verify_chunk", "Verify one chunk result."),
    "bootstrap": ("bootstrap_agents", "Generate agent compatibility files."),
    "doctor": ("doctor", "Check pipeline environment and configuration."),
    "oneshot": ("oneshot", "Run split, run, and merge in one command."),
}
```

Do not add `docter`.

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_doctor tests.test_pipeline_cli -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add .agents/tools/doctor.py .agents/tools/pipeline_cli.py tests/test_doctor.py tests/test_pipeline_cli.py
git commit -m "feat: add pipeline doctor command"
```

---

### Task 3: Run ID, Progress Messages, and Oneshot

**Files:**
- Create: `.agents/tools/oneshot.py`
- Modify: `.agents/tools/split_cppcheck_xml.py`
- Modify: `.agents/tools/run_fix_pipeline.py`
- Test: extend `tests/test_pipeline_cli.py`

- [ ] **Step 1: Add failing CLI smoke test for `oneshot --help`**

Extend `tests/test_pipeline_cli.py`:

```python
import subprocess


class PipelineCliProcessTests(unittest.TestCase):
    def test_oneshot_help_exits_successfully(self):
        proc = subprocess.run(
            ["python3", str(TOOLS / "pipeline_cli.py"), "oneshot", "--help"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(proc.returncode, 0)
        self.assertIn("自动执行", proc.stdout)
```

- [ ] **Step 2: Run test and verify it fails**

Run:

```bash
python3 -m unittest tests.test_pipeline_cli -v
```

Expected: FAIL because `.agents/tools/oneshot.py` does not exist.

- [ ] **Step 3: Integrate `run_id` and split logging**

Modify imports in `.agents/tools/split_cppcheck_xml.py` to include:

```python
    RUNS_DIR,
    append_pipeline_log,
    next_run_id,
    reset_runtime_logs,
```

Add argument:

```python
    parser.add_argument(
        "--run-id",
        default="",
        help="Use an existing run id instead of generating YYYYMMDD-NNN.",
    )
```

At the start of `main()` after resolving config/strategy:

```python
    run_id = args.run_id.strip() or next_run_id(RUNS_DIR)
    reset_runtime_logs()
    append_pipeline_log(
        RUNTIME_DIR,
        stage="split",
        message=f"正在拆分 XML，运行 ID: {run_id}",
        data={"strategy": strategy, "xml_file": str(xml_file).replace("\\", "/")},
    )
```

Add `run_id` to `progress`:

```python
        "run_id": run_id,
```

After saving progress:

```python
    append_pipeline_log(
        RUNTIME_DIR,
        stage="split",
        message=f"已生成 {total} 个 chunk，问题数 {len(issues)}",
        data={"run_id": run_id, "total_chunks": total, "total_issues": len(issues)},
    )
```

- [ ] **Step 4: Add progress logging in `.agents/tools/run_fix_pipeline.py`**

Import `append_pipeline_log`:

```python
from common import RESULTS_DIR, RUNTIME_DIR, append_jsonl, append_pipeline_log, load_json, save_json
```

After setting `progress["status"] = "running"`:

```python
    append_pipeline_log(
        RUNTIME_DIR,
        stage="run",
        message="开始处理 chunk",
        data={"strategy": requested_strategy, "filters": progress["last_run_filters"]},
    )
```

Before processing a chunk:

```python
        print(f"正在处理 chunk {idx}/{progress.get('total_chunks', 0)}")
        append_pipeline_log(
            RUNTIME_DIR,
            stage="run",
            message=f"正在处理 chunk {idx}/{progress.get('total_chunks', 0)}",
            data={"chunk_index": idx, "attempts": max_attempts},
        )
```

On success:

```python
                append_pipeline_log(
                    RUNTIME_DIR,
                    stage="run",
                    message=f"chunk {idx} 处理完成",
                    data={"chunk_index": idx, "attempt": attempt},
                )
```

On exhausted failure:

```python
            if exhausted:
                append_pipeline_log(
                    RUNTIME_DIR,
                    stage="run",
                    message=f"chunk {idx} 处理失败",
                    level="error",
                    data={"chunk_index": idx, "returncode": rc, "attempt": attempt},
                )
```

- [ ] **Step 5: Implement `.agents/tools/oneshot.py`**

Create `.agents/tools/oneshot.py`:

```python
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List

from common import ROOT, RUNTIME_DIR, append_pipeline_log, load_json
from doctor import collect_checks, has_blockers, print_checks


VALID_STRATEGIES = {"conservative", "all_auto"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动执行 split、run、merge。")
    parser.add_argument("--strategy", choices=sorted(VALID_STRATEGIES), default=None)
    parser.add_argument("--max-chunks", type=int, default=0)
    parser.add_argument("--retry-failed", type=int, default=0)
    parser.add_argument("--rule-id", action="append", default=[])
    parser.add_argument("--misra-only", action="store_true")
    parser.add_argument("--include-failed", action="store_true")
    return parser.parse_args()


def run_tool(args: List[str]) -> int:
    cmd = [sys.executable, str(ROOT / ".agents" / "tools" / "pipeline_cli.py"), *args]
    proc = subprocess.run(cmd, cwd=str(ROOT), check=False)
    return proc.returncode


def main() -> None:
    args = parse_args()

    checks = collect_checks()
    if has_blockers(checks):
        print("环境检查未通过。请运行以下命令查看完整诊断：")
        print("python3 .agents/tools/pipeline_cli.py doctor")
        print_checks(checks)
        raise SystemExit(1)

    split_args = ["split"]
    run_args = ["run"]
    if args.strategy:
        split_args.extend(["--strategy", args.strategy])
        run_args.extend(["--strategy", args.strategy])
    if args.max_chunks:
        run_args.extend(["--max-chunks", str(args.max_chunks)])
    if args.retry_failed:
        run_args.extend(["--retry-failed", str(args.retry_failed)])
    for rule_id in args.rule_id:
        run_args.extend(["--rule-id", rule_id])
    if args.misra_only:
        run_args.append("--misra-only")
    if args.include_failed:
        run_args.append("--include-failed")

    stages = [
        ("split", "正在拆分 XML", split_args),
        ("run", "正在运行 agent 修复流程", run_args),
        ("merge", "正在生成 review 报告并归档", ["merge"]),
    ]

    for stage, message, command in stages:
        print(message)
        append_pipeline_log(RUNTIME_DIR, stage=stage, message=message, data={"command": command})
        rc = run_tool(command)
        if rc != 0:
            append_pipeline_log(
                RUNTIME_DIR,
                stage=stage,
                message=f"{stage} 阶段失败",
                level="error",
                data={"returncode": rc},
            )
            print(f"{stage} 阶段失败，返回码 {rc}。请运行 doctor 检查环境。")
            raise SystemExit(rc)

    progress = load_json(RUNTIME_DIR / "progress.json", {})
    run_id = progress.get("run_id", "")
    if run_id:
        print(f"运行完成，结果已归档到 .agents/runs/{run_id}/")
    else:
        print("运行完成，结果已生成。")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Run tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_pipeline_cli -v
```

Expected: PASS.

- [ ] **Step 7: Run a no-agent safe smoke command**

Run:

```bash
python3 .agents/tools/pipeline_cli.py oneshot --help
```

Expected: exits 0 and prints help text containing `自动执行`.

- [ ] **Step 8: Commit**

```bash
git add .agents/tools/oneshot.py .agents/tools/split_cppcheck_xml.py .agents/tools/run_fix_pipeline.py tests/test_pipeline_cli.py
git commit -m "feat: add oneshot pipeline runner"
```

---

### Task 4: Chinese Review Reports and Archives

**Files:**
- Modify: `.agents/tools/merge_results.py`
- Test: `tests/test_reports_archive.py`

- [ ] **Step 1: Write failing report/archive tests**

Create `tests/test_reports_archive.py`:

```python
import json
import tempfile
import unittest
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / ".agents" / "tools"
sys.path.insert(0, str(TOOLS))

import merge_results


class ReportArchiveTests(unittest.TestCase):
    def test_build_review_markdown_contains_chinese_review_sections(self):
        summary = {
            "run_id": "20260423-001",
            "total_issues": 2,
            "status_counts": {"fixed": 1, "needs_manual_review": 1},
            "strategy_counts": {"conservative": 2},
            "fixed_high_risk_count": 1,
            "review_required_after_fix_count": 1,
            "fixed_high_risk": ["file.c:1:rule:abcd1234"],
            "review_required_after_fix": ["file.c:1:rule:abcd1234"],
            "fixed_by_rule": {"uninitvar": 1},
            "fixed_by_file": {"file.c": 1},
            "failed_issues": [],
            "unverified_issues": ["file.c:2:rule:abcd1234"],
            "touched_files": ["file.c"],
        }
        issue_status = {
            "file.c:1:rule:abcd1234": {
                "file": "file.c",
                "rule_id": "rule",
                "status": "fixed",
                "risk_reason": "No rule-specific auto-fix policy is configured.",
            }
        }
        file_change_index = {
            "file.c": {
                "edits": [
                    {
                        "edit_id": "file.c#001",
                        "summary": "初始化局部变量",
                        "chunk_index": 1,
                        "related_issue_keys": ["file.c:1:rule:abcd1234"],
                    }
                ]
            }
        }

        markdown = merge_results.build_review_markdown(summary, issue_status, file_change_index)

        self.assertIn("运行概览", markdown)
        self.assertIn("Review 重点", markdown)
        self.assertIn("需人工复核（needs manual review）", markdown)
        self.assertIn("未执行工程级验证", markdown)

    def test_write_run_manifest_records_report_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive_dir = Path(tmp) / "20260423-001"
            archive_dir.mkdir()
            summary = {"run_id": "20260423-001", "total_issues": 1}
            progress = {"fix_strategy": "conservative", "total_chunks": 1}

            merge_results.write_run_manifest(archive_dir, summary, progress)

            manifest = json.loads((archive_dir / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["run_id"], "20260423-001")
            self.assertEqual(manifest["reports"]["summary_md"], "reports/final_summary.md")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_reports_archive -v
```

Expected: FAIL because `build_review_markdown` and `write_run_manifest` do not exist.

- [ ] **Step 3: Refactor `merge_results.py` into focused helpers**

Add imports:

```python
from common import (
    REPORTS_DIR,
    RUNTIME_DIR,
    RUNS_DIR,
    copy_current_run_archive,
    load_json,
    now_iso,
    save_json,
)
```

Add these helper functions:

```python
def issue_line(issue_key: str, item: dict) -> str:
    return (
        f"- `{issue_key}`：文件 `{item.get('file', '')}`，规则 `{item.get('rule_id', '')}`，"
        f"状态 `{item.get('status', 'unknown')}`，原因：{item.get('risk_reason', '') or '未记录'}"
    )


def collect_summary(issue_status: dict, file_change_index: dict, progress: dict) -> dict:
    status_counts = Counter()
    fixed_by_rule = Counter()
    fixed_by_file = Counter()
    strategy_counts = Counter()
    fixed_high_risk = []
    review_required_after_fix = []
    failed_issues = []
    unverified_issues = []

    for issue_key, item in issue_status.items():
        status = item.get("status", "unknown")
        status_counts[status] += 1
        strategy_counts[item.get("fix_strategy", progress.get("fix_strategy", "unknown"))] += 1
        if status == "fixed":
            fixed_by_rule[item.get("rule_id", "")] += 1
            fixed_by_file[item.get("file", "")] += 1
            if item.get("risk_level") == "high":
                fixed_high_risk.append(issue_key)
            if item.get("requires_review_after_fix"):
                review_required_after_fix.append(issue_key)
        if status == "failed":
            failed_issues.append(issue_key)
        if not item.get("verified", False):
            unverified_issues.append(issue_key)

    return {
        "run_id": progress.get("run_id", ""),
        "total_issues": len(issue_status),
        "total_chunks": progress.get("total_chunks", 0),
        "completed_chunks": progress.get("completed_chunks", []),
        "failed_chunks": progress.get("failed_chunks", []),
        "status": progress.get("status", "unknown"),
        "status_counts": dict(status_counts),
        "strategy_counts": dict(strategy_counts),
        "fixed_high_risk_count": len(fixed_high_risk),
        "review_required_after_fix_count": len(review_required_after_fix),
        "fixed_high_risk": fixed_high_risk,
        "review_required_after_fix": review_required_after_fix,
        "failed_issues": failed_issues,
        "unverified_issues": unverified_issues,
        "fixed_by_rule": dict(fixed_by_rule),
        "fixed_by_file": dict(fixed_by_file),
        "touched_files": sorted(file_change_index.keys()),
    }


def build_review_markdown(summary: dict, issue_status: dict, file_change_index: dict) -> str:
    lines = [
        "# cppcheck/MISRA 修复结果汇总",
        "",
        "## 运行概览",
        "",
        f"- 运行 ID：`{summary.get('run_id') or '未记录'}`",
        f"- 流水线状态：`{summary.get('status', 'unknown')}`",
        f"- 问题总数：{summary.get('total_issues', 0)}",
        f"- Chunk 总数：{summary.get('total_chunks', 0)}",
        f"- 已完成 chunk：{len(summary.get('completed_chunks', []))}",
        f"- 失败 chunk：{len(summary.get('failed_chunks', []))}",
        "",
        "## Review 重点",
        "",
        f"- 高风险已修复项：{summary.get('fixed_high_risk_count', 0)}",
        f"- 需人工复核（needs manual review）项：{summary.get('status_counts', {}).get('needs_manual_review', 0)}",
        f"- 修复后仍需复核项：{summary.get('review_required_after_fix_count', 0)}",
        f"- 失败项：{len(summary.get('failed_issues', []))}",
        f"- 未执行工程级验证项：{len(summary.get('unverified_issues', []))}",
        "",
        "## 高风险与复核项",
        "",
    ]
    keys = summary.get("fixed_high_risk", []) + summary.get("review_required_after_fix", [])
    if keys:
        for issue_key in sorted(set(keys)):
            lines.append(issue_line(issue_key, issue_status.get(issue_key, {})))
    else:
        lines.append("- 无")

    lines.extend(["", "## 失败项", ""])
    if summary.get("failed_issues"):
        for issue_key in summary["failed_issues"]:
            lines.append(issue_line(issue_key, issue_status.get(issue_key, {})))
    else:
        lines.append("- 无")

    lines.extend(["", "## 按文件汇总", ""])
    for file_path in summary.get("touched_files", []):
        lines.append(f"### `{file_path}`")
        for edit in file_change_index.get(file_path, {}).get("edits", []):
            lines.append(
                f"- `{edit.get('edit_id', '')}`：{edit.get('summary', '') or '未记录摘要'}，"
                f"chunk {edit.get('chunk_index', '')}，关联问题 {len(edit.get('related_issue_keys', []))} 个"
            )
        lines.append("")

    lines.extend(["## 按规则汇总", ""])
    for rule_id, count in sorted(summary.get("fixed_by_rule", {}).items()):
        lines.append(f"- `{rule_id}`：fixed {count}")

    lines.extend(["", "## 验证结果", ""])
    if summary.get("unverified_issues"):
        lines.append("- 未执行工程级验证，以下问题未标记为 verified。")
        for issue_key in summary["unverified_issues"]:
            lines.append(f"  - `{issue_key}`")
    else:
        lines.append("- 所有问题均已记录验证结果。")

    return "\n".join(lines).rstrip() + "\n"


def build_review_checklist(summary: dict) -> str:
    lines = [
        "# 人工 Review 检查清单",
        "",
        "## 必看项",
        "",
        f"- 高风险已修复项：{summary.get('fixed_high_risk_count', 0)}",
        f"- 修复后仍需复核项：{summary.get('review_required_after_fix_count', 0)}",
        f"- 失败项：{len(summary.get('failed_issues', []))}",
        "",
        "## 抽查项",
        "",
        "- 检查普通自动修复是否只包含局部、明确的改动。",
        "- 检查同一文件内多个问题合并修改时，是否仍能对应到 edit_id。",
        "",
        "## 验证项",
        "",
        "- 确认是否重新运行 cppcheck。",
        "- 确认是否执行自定义验证命令。",
        "- 对未执行工程级验证的结果，不要按已验证结论放行。",
    ]
    return "\n".join(lines) + "\n"


def write_run_manifest(archive_dir: Path, summary: dict, progress: dict) -> None:
    manifest = {
        "run_id": summary.get("run_id", ""),
        "created_at": now_iso(),
        "input_xml": progress.get("xml_file", ""),
        "fix_strategy": progress.get("fix_strategy", ""),
        "status": progress.get("status", ""),
        "total_issues": summary.get("total_issues", 0),
        "total_chunks": summary.get("total_chunks", 0),
        "completed_chunks": summary.get("completed_chunks", []),
        "failed_chunks": summary.get("failed_chunks", []),
        "reports": {
            "summary_md": "reports/final_summary.md",
            "checklist_md": "reports/review_checklist.md",
            "summary_json": "reports/final_summary.json",
        },
    }
    save_json(archive_dir / "run_manifest.json", manifest)
```

- [ ] **Step 4: Update `main()` in `merge_results.py` to use helpers and archive**

Replace current inline summary/report construction with:

```python
def main() -> None:
    issue_status = load_json(RUNTIME_DIR / "issue_status.json", {})
    file_change_index = load_json(RUNTIME_DIR / "file_change_index.json", {})
    progress = load_json(RUNTIME_DIR / "progress.json", {})

    summary = collect_summary(issue_status, file_change_index, progress)
    save_json(REPORTS_DIR / "final_summary.json", summary)

    (REPORTS_DIR / "final_summary.md").write_text(
        build_review_markdown(summary, issue_status, file_change_index),
        encoding="utf-8",
    )
    (REPORTS_DIR / "review_checklist.md").write_text(
        build_review_checklist(summary),
        encoding="utf-8",
    )

    patch_lines = ["# Final Patch Index", ""]
    for file_path, data in sorted(file_change_index.items()):
        patch_lines.append(f"## {file_path}")
        for edit in data.get("edits", []):
            patch_lines.append(
                f"- {edit.get('edit_id')}: {edit.get('summary', '')} "
                f"(chunk {edit.get('chunk_index')}, issues={len(edit.get('related_issue_keys', []))})"
            )
        patch_lines.append("")
    (REPORTS_DIR / "final_patch_index.md").write_text("\n".join(patch_lines), encoding="utf-8")

    run_id = summary.get("run_id")
    if run_id:
        archive_dir = RUNS_DIR / run_id
        copy_current_run_archive(RUNTIME_DIR, REPORTS_DIR, archive_dir)
        write_run_manifest(archive_dir, summary, progress)
        print(f"Summary generated. Archive: {archive_dir}")
    else:
        print("Summary generated. No run_id found; archive skipped.")
```

- [ ] **Step 5: Run report/archive tests**

Run:

```bash
python3 -m unittest tests.test_reports_archive -v
```

Expected: PASS.

- [ ] **Step 6: Run all tests added so far**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .agents/tools/merge_results.py tests/test_reports_archive.py
git commit -m "feat: improve review reports and archive runs"
```

---

### Task 5: Skill, Prompt, and README Updates

**Files:**
- Modify: `.agents/prompts/fix_chunk_prompt.txt`
- Modify: `.agents/skills/cppcheck-misra-fix/SKILL.md`
- Modify: `README.md`

- [ ] **Step 1: Update prompt to avoid stalled workflows**

Append to `.agents/prompts/fix_chunk_prompt.txt`:

```text

Workflow resilience:
- Prefer completing the current chunk within the workspace: edit files, update runtime JSON, write result JSON/Markdown, and record verification.
- If sandbox, permission, missing tool, or external command limitations prevent a safe fix, do not wait indefinitely for user input.
- Record the affected issue as failed or needs_manual_review with a clear blocker reason.
- If later issues in the same chunk can still be handled safely, continue with them.
- Ask the user only when explicit authorization is required and no useful progress can be recorded without it.
```

- [ ] **Step 2: Update skill instructions**

Append to `.agents/skills/cppcheck-misra-fix/SKILL.md` under `# Rules`:

```markdown
- Prefer completing work inside the current workspace without asking the user.
- If sandbox, permission, missing tool, or external command issues block a fix, record a clear blocker in the result files instead of stalling.
- When one issue is blocked but other issues in the chunk are still safe to process, continue with the remaining issues.
- Ask the user only when explicit authorization is required and no useful progress can be recorded without it.
```

Append to `# Required outputs`:

```markdown
- blocker reasons for issues that could not be handled because of environment or permission limits
- user action required, when manual authorization or external setup is needed
```

- [ ] **Step 3: Update README quick start**

Replace the quick start section with:

```markdown
## 快速开始

推荐使用一键入口：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --strategy conservative
```

`oneshot` 会自动完成：

1. 拆分 `cppcheck.xml`
2. 调用本地 agent 逐 chunk 修复
3. 合并结果
4. 生成中文 review 报告
5. 归档本次运行结果

首次运行或运行失败时，先执行环境检查：

```bash
python3 .agents/tools/pipeline_cli.py doctor
```

结果归档在：

```text
.agents/runs/YYYYMMDD-序号/
```

主要 review 文件：

- `.agents/runs/YYYYMMDD-序号/reports/final_summary.md`
- `.agents/runs/YYYYMMDD-序号/reports/review_checklist.md`

运行日志：

- `.agents/runs/YYYYMMDD-序号/logs/pipeline.log`
- `.agents/runs/YYYYMMDD-序号/logs/run_log.jsonl`
```

Keep the existing split/run/merge commands under a later “分步调试” section.

- [ ] **Step 4: Verify docs mention no misspelled alias**

Run:

```bash
rg -n "docter" README.md .agents/prompts/fix_chunk_prompt.txt .agents/skills/cppcheck-misra-fix/SKILL.md .agents/tools
```

Expected: no output.

- [ ] **Step 5: Commit**

```bash
git add README.md .agents/prompts/fix_chunk_prompt.txt .agents/skills/cppcheck-misra-fix/SKILL.md
git commit -m "docs: document oneshot workflow and resilient agent guidance"
```

---

### Task 6: End-to-End Verification

**Files:**
- No planned source changes. Only run verification commands.

- [ ] **Step 1: Run unit tests**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 2: Run doctor**

Run:

```bash
python3 .agents/tools/pipeline_cli.py doctor
```

Expected: exits 0 when local `codex` is available and `cppcheck.xml` is valid. If `codex` is not installed in the environment, expected result is exit 1 with a clear “找不到 agent 命令” message.

- [ ] **Step 3: Run split-only smoke test**

Run:

```bash
python3 .agents/tools/pipeline_cli.py split --strategy conservative
```

Expected: prints `Generated N chunks...`, writes `.agents/runtime/progress.json`, and includes `run_id`.

- [ ] **Step 4: Run merge-only smoke test**

Run:

```bash
python3 .agents/tools/pipeline_cli.py merge
```

Expected: generates:

```text
.agents/reports/final_summary.md
.agents/reports/review_checklist.md
.agents/reports/final_summary.json
.agents/runs/YYYYMMDD-序号/run_manifest.json
```

- [ ] **Step 5: Verify archive and logs**

Run:

```bash
find .agents/runs -maxdepth 3 -type f | sort
```

Expected: latest run directory contains `reports/`, `runtime/`, and `logs/`.

- [ ] **Step 6: Verify no misspelled alias**

Run:

```bash
python3 .agents/tools/pipeline_cli.py docter
```

Expected: exits non-zero with argparse invalid choice; no command alias should handle it.

- [ ] **Step 7: Final status**

Run:

```bash
git status --short
```

Expected: no uncommitted source changes after all task commits.

