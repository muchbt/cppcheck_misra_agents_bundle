# Pipeline Review Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a low-risk usability layer for the cppcheck/MISRA pipeline: `oneshot`, `doctor`, Chinese review reports, date-based run archives, unified logs, resumable runs, verification recording, and resilient skill guidance.

**Architecture:** Keep the existing `split -> run -> merge` flow. Add focused helpers in `common.py`, introduce `doctor.py` and `oneshot.py`, extend `split_cppcheck_xml.py` / `run_fix_pipeline.py` / `merge_results.py`, and update docs/skill/prompt. Do not change the chunk JSON main structure.

**Tech Stack:** Python 3.8+ standard library, `unittest`, existing `.agents/tools` scripts, Markdown, JSON/JSONL.

---

## File Structure

- Modify `.agents/tools/common.py`: root discovery, Python 3.8-compatible helpers, run IDs, unified logs, config validation, archive copy.
- Create `.agents/tools/doctor.py`: environment/config/runtime diagnostics.
- Create `.agents/tools/oneshot.py`: precheck, fresh/resume decision, staged execution.
- Modify `.agents/tools/pipeline_cli.py`: add `doctor` and `oneshot`; do not add `docter`.
- Modify `.agents/tools/split_cppcheck_xml.py`: run ID, started_at, fresh-run log initialization.
- Modify `.agents/tools/run_fix_pipeline.py`: unified logs, progress messages, verification after successful chunks.
- Modify `.agents/tools/merge_results.py`: Chinese review reports, actionable checklist, manifest, archive.
- Modify `.agents/tools/verify_chunk.py`: expose a callable verification function while preserving CLI behavior.
- Modify `.agents/prompts/fix_chunk_prompt.txt`, `.agents/skills/cppcheck-misra-fix/SKILL.md`, `README.md`.
- Create `tests/` with focused `unittest` modules for common helpers, doctor, CLI, oneshot behavior, reports/archive, and verification integration.

---

## Task 1: 公共基础能力

**Files:**
- `.agents/tools/common.py`
- `tests/test_common_runtime.py`

- [ ] Add tests for project-root discovery from a non-root working directory, run ID incrementation, Python 3.8-compatible config validation, unified JSONL event shape, and archive copying.
- [ ] Replace `ROOT = Path.cwd()` with a deterministic root based on the script location: `Path(__file__).resolve().parents[2]`.
- [ ] Add constants: `RUNS_DIR`, `TZ`, and `RUN_ID_RE`.
- [ ] Add `now_iso()`, `next_run_id()`, `validate_pipeline_config()`, `append_pipeline_event()`, `reset_runtime_logs()`, `copy_current_run_archive()`, and `archive_size_bytes()`.
- [ ] Make `validate_pipeline_config()` return `Tuple[List[str], List[str]]`, not `tuple[...]`.
- [ ] Make `append_pipeline_event()` write both:
  - `.agents/runtime/pipeline.log`
  - `.agents/runtime/run_log.jsonl`
- [ ] Ensure each JSONL event uses this stable schema:

```json
{
  "time": "2026-04-23T10:00:00+08:00",
  "event": "chunk_completed",
  "stage": "run",
  "level": "info",
  "message": "chunk 1 处理完成",
  "chunk_index": 1,
  "returncode": 0,
  "data": {}
}
```

- [ ] Run:

```bash
python3 -m unittest tests.test_common_runtime -v
```

- [ ] Commit:

```bash
git add .agents/tools/common.py tests/test_common_runtime.py
git commit -m "feat: add pipeline runtime helpers"
```

---

## Task 2: Doctor 诊断入口

**Files:**
- `.agents/tools/doctor.py`
- `.agents/tools/pipeline_cli.py`
- `tests/test_doctor.py`
- `tests/test_pipeline_cli.py`

- [ ] Add tests for invalid XML, scan-log text mistakenly used as XML, config errors, runtime strategy mismatch, existing unfinished run, archive size warning, prompt length warning, and CLI command availability.
- [ ] Implement `doctor.py` with callable check functions returning structured results: `level`, `code`, `message`, `detail`.
- [ ] Check Python version is 3.8+.
- [ ] Check root discovery resolves the project root regardless of current working directory.
- [ ] Check `cppcheck.xml`, `pipeline.json`, `agent.command`, custom verification command, runtime strategy, archive count/size, and prompt length.
- [ ] Make `doctor` print Chinese diagnostics and exit non-zero only for blocker-level errors.
- [ ] Add `doctor` and `oneshot` to `pipeline_cli.COMMANDS`.
- [ ] Do not add `docter`; test that argparse rejects it.
- [ ] Run:

```bash
python3 -m unittest tests.test_doctor tests.test_pipeline_cli -v
python3 .agents/tools/pipeline_cli.py doctor
```

- [ ] Commit:

```bash
git add .agents/tools/doctor.py .agents/tools/pipeline_cli.py tests/test_doctor.py tests/test_pipeline_cli.py
git commit -m "feat: add pipeline doctor diagnostics"
```

---

## Task 3: Split、Run 与可续跑 Oneshot

**Files:**
- `.agents/tools/split_cppcheck_xml.py`
- `.agents/tools/run_fix_pipeline.py`
- `.agents/tools/verify_chunk.py`
- `.agents/tools/oneshot.py`
- `tests/test_oneshot.py`
- `tests/test_run_pipeline.py`

- [ ] Add tests that `split --run-id` records `run_id` and `started_at`.
- [ ] Add tests that `oneshot` defaults to resume when `.agents/runtime/progress.json` has status `ready`, `running`, `partial`, or `failed`.
- [ ] Add tests that `oneshot --fresh` runs split and resets current runtime logs/results.
- [ ] Add tests that resume mode does not delete existing chunk result files.
- [ ] Add tests that resume mode rejects a conflicting explicit `--strategy` and tells the user to use `--fresh`.
- [ ] Add tests that `--run-id` is accepted for fresh runs and rejected for resume when it differs from current progress.
- [ ] Modify `split_cppcheck_xml.py`:
  - Add `--run-id`.
  - Generate `run_id` with `next_run_id()` when absent.
  - Record `started_at`.
  - Reset runtime logs only for fresh split.
  - Log `split_started` and `split_completed` using the unified event helper.
- [ ] Modify `verify_chunk.py`:
  - Extract a callable `verify_chunk_result(chunk_index: int) -> dict`.
  - Keep CLI behavior by calling that function from `main()`.
- [ ] Modify `run_fix_pipeline.py`:
  - Remove local `TZ` / `now()`, use `common.now_iso()`.
  - Replace direct `append_jsonl(RUNTIME_DIR / "run_log.jsonl", ...)` calls with unified events.
  - Print `正在处理 chunk X/Y`.
  - After successful agent result JSON creation, call `verify_chunk_result(idx)`.
  - Preserve existing retry, filter, include-failed, and strategy-mismatch behavior.
- [ ] Implement `oneshot.py`:
  - Run basic precheck via `doctor` helpers.
  - If unfinished runtime exists, default to resume and print run ID/progress summary.
  - If resume mode receives an explicit `--strategy` that differs from `progress["fix_strategy"]`, exit before running any stage and print a Chinese message that names both strategies and recommends `--fresh --strategy <target>`.
  - If `--fresh`, run split before run.
  - If no runtime exists, run split.
  - Then run `run`, then `merge`.
  - On failure, log event and leave runtime intact for the next resume.
  - Keep stage execution behind a small runner function so future work can add lock files, custom run IDs, or direct function calls without changing user-facing arguments.
- [ ] Run:

```bash
python3 -m unittest tests.test_oneshot tests.test_run_pipeline -v
python3 .agents/tools/pipeline_cli.py oneshot --help
```

- [ ] Commit:

```bash
git add .agents/tools/split_cppcheck_xml.py .agents/tools/run_fix_pipeline.py .agents/tools/verify_chunk.py .agents/tools/oneshot.py tests/test_oneshot.py tests/test_run_pipeline.py
git commit -m "feat: add resumable oneshot pipeline"
```

---

## Task 4: 中文 Review 报告、Manifest 与归档

**Files:**
- `.agents/tools/merge_results.py`
- `tests/test_reports_archive.py`

- [ ] Add tests for Chinese `final_summary.md`, actionable `review_checklist.md`, manifest timestamps, archive directory layout, and verification summary wording.
- [ ] Refactor `merge_results.py` into callable helpers:
  - `collect_summary(issue_status, file_change_index, progress)`
  - `build_review_markdown(summary, issue_status, file_change_index)`
  - `build_review_checklist(summary, issue_status, file_change_index)`
  - `write_run_manifest(archive_dir, summary, progress)`
- [ ] Ensure `review_checklist.md` lists concrete issue keys, files, rules, statuses, and edit IDs for required review items.
- [ ] Ensure `final_summary.md` uses Simplified Chinese and keeps first-use English terms, including “需人工复核（needs manual review）”.
- [ ] Write `run_manifest.json` with `started_at`, `finished_at`, `archived_at`, input XML, strategy, issue/chunk counts, completed/failed chunks, and report paths.
- [ ] Copy runtime, reports, and logs into `.agents/runs/<run_id>/`.
- [ ] When no custom verification command ran, report “未执行工程级验证”; do not claim verification success.
- [ ] Run:

```bash
python3 -m unittest tests.test_reports_archive -v
```

- [ ] Commit:

```bash
git add .agents/tools/merge_results.py tests/test_reports_archive.py
git commit -m "feat: improve review reports and run archives"
```

---

## Task 5: Skill、Prompt、兼容层与 README

**Files:**
- `.agents/prompts/fix_chunk_prompt.txt`
- `.agents/skills/cppcheck-misra-fix/SKILL.md`
- `.codex/skills/cppcheck-misra-fix/SKILL.md`
- `README.md`

- [ ] Update prompt with short resilience guidance:
  - Prefer completing work inside the workspace.
  - Record blockers instead of waiting indefinitely.
  - Continue safe issues when one issue is blocked.
  - Ask users only when explicit authorization is required.
- [ ] Update project skill with the same behavior.
- [ ] Run bootstrap sync:

```bash
python3 .agents/tools/bootstrap_agents.py --mode merge
```

- [ ] Update README:
  - `oneshot` is the recommended entry.
  - `doctor` is for first run and failure diagnosis.
  - Explain default resume behavior and `--fresh`.
  - Explain archive, logs, review reports, and verification wording.
- [ ] Verify no misspelled alias appears:

```bash
rg -n "docter" README.md .agents .codex
```

Expected: no output.

- [ ] Commit:

```bash
git add README.md .agents/prompts/fix_chunk_prompt.txt .agents/skills/cppcheck-misra-fix/SKILL.md .codex/skills/cppcheck-misra-fix/SKILL.md
git commit -m "docs: document resumable oneshot workflow"
```

---

## Task 6: End-to-End Verification

**Files:**
- No planned source edits.

- [ ] Run all unit tests:

```bash
python3 -m unittest discover -s tests -v
```

- [ ] Run diagnostics:

```bash
python3 .agents/tools/pipeline_cli.py doctor
```

Expected: exits 0 when local dependencies are available. If `codex` is missing, exits non-zero with a clear Chinese error.

- [ ] Run fresh split smoke:

```bash
python3 .agents/tools/pipeline_cli.py split --strategy conservative --run-id 20260423-999
```

Expected: `progress.json` includes `run_id` and `started_at`.

- [ ] Run limited pipeline smoke:

```bash
python3 .agents/tools/pipeline_cli.py run --max-chunks 1
```

Expected: handles one chunk or records a clear failure without corrupting runtime.

- [ ] Run merge smoke:

```bash
python3 .agents/tools/pipeline_cli.py merge
```

Expected: creates reports and `.agents/runs/<run_id>/run_manifest.json`.

- [ ] Run resume smoke:

```bash
python3 .agents/tools/pipeline_cli.py oneshot --strategy conservative
```

Expected: if runtime is unfinished, prints that it is resuming and does not delete existing result files.

- [ ] Run strategy-conflict smoke:

```bash
python3 .agents/tools/pipeline_cli.py oneshot --strategy all_auto
```

Expected: if the unfinished runtime was split with `conservative`, exits before running stages and tells the user to use `--fresh --strategy all_auto`.

- [ ] Verify alias rejection:

```bash
python3 .agents/tools/pipeline_cli.py docter
```

Expected: argparse invalid choice, non-zero exit.

- [ ] Verify final working tree:

```bash
git status --short
```

Expected: no uncommitted implementation changes.

---

## Future Improvements

These items came from `improvements_v2.md` but are intentionally deferred because they are low priority. The current implementation should keep extension points open for them.

- Add `oneshot --run-id` so users can set custom run IDs from the one-command entry. For now, only `split --run-id` is required.
- Decide whether `oneshot` stages should remain subprocess-based or become direct function calls. Current work should hide stage execution behind a runner helper.
- Improve `doctor` support for compound agent commands such as `python3 -m some_agent`; current work only needs a basic executable check.
- Add a runtime lock file such as `.agents/runtime/.lock` to prevent concurrent `oneshot` processes.
- Document that `.agents/reports/` represents the latest merge result, while `.agents/runs/<run_id>/` is the historical archive.
- Expand verification integration tests to cover custom command success, custom command failure, missing command, and timeout behavior.

---

## Task 7: 通用非交互 agent 执行抽象

> 背景：Task 6 的真实链路验证表明，当前 `split -> run -> merge` 主流程可用，但 `run` 阶段仍依赖“字符串命令 + prompt 位置参数”的旧式 agent 调用方式。该方式会把交互式 CLI 当成批处理执行器，导致真实环境下因为 TTY、PATH 更新或只读文件系统而失败。该问题属于通用执行层缺陷，不应作为 Codex 特例处理。

**Files:**
- `.agents/config/pipeline.json`
- `.agents/tools/common.py`
- `.agents/tools/doctor.py`
- `.agents/tools/run_fix_pipeline.py`
- `.agents/tools/providers/base.py`
- `.agents/tools/providers/__init__.py`
- `.agents/tools/providers/codex.py`
- `.agents/tools/agent_runner.py`
- `README.md`
- `tests/test_doctor.py`
- `tests/test_run_pipeline.py`
- `tests/test_agent_runner.py`

### Task 7.1: 升级 agent 配置模型

- [ ] Replace legacy `agent.command` string config with a structured model:

```json
"agent": {
  "provider": "codex",
  "launch": {
    "argv": ["codex", "exec", "--full-auto"],
    "prompt_via": "stdin",
    "cwd": "project_root",
    "env": {
      "CODEX_HOME": ".agents/runtime/agent-home"
    },
    "requires_tty": false,
    "output": {
      "mode": "exit_code"
    }
  },
  "capabilities": {
    "non_interactive": true,
    "workspace_write_required": true
  },
  "auto_bootstrap_compat": true
}
```

- [ ] Update config validation so the old `agent.command: "codex"` form is rejected with a clear error.
- [ ] Keep Python 3.8-compatible type annotations in config validation and runner code.

### Task 7.2: 引入 provider 目录和通用 runner

- [ ] Add `.agents/tools/providers/base.py` for provider and launch spec types.
- [ ] Add `.agents/tools/providers/__init__.py` for provider registry.
- [ ] Add `.agents/tools/providers/codex.py` as the only real provider in phase 1.
- [ ] Add `.agents/tools/agent_runner.py`:
  - Load structured `agent` config
  - Resolve provider
  - Validate launch spec
  - Support `prompt_via = stdin | arg | file`
  - Resolve `cwd = project_root | runtime_dir | custom`
  - Prepare environment variables mapped to writable workspace paths
  - Execute subprocess and return a unified result
- [ ] Remove or replace direct use of `.agents/tools/agent_adapter_codex.py` so the pipeline no longer executes `[agent_cmd, prompt]`.

### Task 7.3: 将 run 流程切换到通用执行层

- [ ] Modify `.agents/tools/run_fix_pipeline.py` so chunk execution goes through the new runner.
- [ ] Preserve existing progress updates, retry behavior, unified logging, verification calls, and failure semantics.
- [ ] Keep failure classification compatible with current runtime state:
  - `config_error`
  - `spawn_error`
  - `runtime_error`
  - `interactive_not_supported`

### Task 7.4: 升级 doctor 诊断规则

- [ ] Update `.agents/tools/doctor.py` to validate execution suitability instead of only checking command existence.
- [ ] Check at least:
  - `agent.provider` is supported
  - `launch.argv` is a non-empty array
  - `prompt_via` is supported by the provider
  - `cwd` resolves correctly
  - mapped env directories can be created/written in workspace
  - `requires_tty` and `capabilities.non_interactive` are not contradictory
  - provider is implemented in this phase
- [ ] For the phase-1 `codex` provider, block configurations that still imply an interactive TUI-style launch.
- [ ] Reserve provider-differentiated diagnostics for a future `claude` provider without implementing it now.

### Task 7.5: 文档与测试

- [ ] Update `README.md` with the new structured agent config model and non-interactive execution requirements.
- [ ] Add tests for:
  - accepting structured `agent` config
  - rejecting legacy string command config
  - runner stdin/env/cwd handling
  - spawn error and non-zero exit propagation
  - doctor blocker diagnostics for interactive / non-writable / malformed configs
  - run pipeline behavior after switching to the runner
- [ ] Run:

```bash
python3 -m unittest tests.test_doctor tests.test_run_pipeline tests.test_agent_runner -v
python3 .agents/tools/pipeline_cli.py doctor
```

- [ ] Run a real pipeline verification against generated sample input after the runner switch:

```bash
python3 gen_scan_files.py
cppcheck --enable=warning,style --addon=misra.py --xml --xml-version=2 . 2> cppcheck.xml
python3 .agents/tools/pipeline_cli.py oneshot --fresh --run-id 20260423-999
```

Expected:
- no interactive TUI prompt
- no PATH update failure caused by interactive startup mode
- split completes
- run enters provider-backed non-interactive execution
- failures, if any, are recorded through the new unified execution layer

- [ ] Commit:

```bash
git add .agents/config/pipeline.json .agents/tools/common.py .agents/tools/doctor.py .agents/tools/run_fix_pipeline.py .agents/tools/providers/base.py .agents/tools/providers/__init__.py .agents/tools/providers/codex.py .agents/tools/agent_runner.py README.md tests/test_doctor.py tests/test_run_pipeline.py tests/test_agent_runner.py
git commit -m "feat: add non-interactive agent runner"
```

---

## Phase 2 Reservation

`Claude Code` support is intentionally reserved for phase 2. The phase-1 design must leave room for:

- adding `.agents/tools/providers/claude.py`
- extending provider registry without changing the runner contract
- adding provider-specific doctor diagnostics
- mapping provider-specific writable home/config directories
