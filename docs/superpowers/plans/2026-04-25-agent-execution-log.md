# Agent Execution Log Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add chunk-level execution logs with stdout/stderr capture, improve error classification to analyze stdout, and provide better failure summaries.

**Architecture:** Add LOGS_DIR infrastructure in common.py, extend classify_runtime_error signature to accept stdout, write logs per-chunk in run_fix_pipeline.py with retry append strategy, improve failure output with keyword-based summary extraction.

**Tech Stack:** Python 3.10, pathlib, subprocess, shutil

---

## File Structure

| File | Purpose |
|------|---------|
| `common.py` | LOGS_DIR constant, ensure_dirs() update, reset_runtime_logs() update, copy_current_run_archive() update |
| `providers/base.py` | ProviderProtocol signature update for classify_runtime_error |
| `providers/codex.py` | classify_runtime_error(stderr, stdout="") with quota detection |
| `providers/claude.py` | classify_runtime_error(stderr, stdout="") with stdout analysis |
| `providers/opencode.py` | classify_runtime_error(stderr, stdout="") with stdout analysis |
| `agent_runner.py` | Call classify_runtime_error with stdout parameter |
| `run_fix_pipeline.py` | Log writing, summary extraction, --verbose flag |

---

### Task 1: Add LOGS_DIR infrastructure to common.py

**Files:**
- Modify: `.agents/tools/common.py:20-24` (add constant)
- Modify: `.agents/tools/common.py:93-105` (ensure_dirs)
- Modify: `.agents/tools/common.py:435-439` (reset_runtime_logs)
- Modify: `.agents/tools/common.py:453` (copy_current_run_archive)

- [ ] **Step 1: Add LOGS_DIR constant after RESULTS_DIR**

```python
# After line 23: RESULTS_DIR = RUNTIME_DIR / "results"
LOGS_DIR = RUNTIME_DIR / "logs"
```

- [ ] **Step 2: Update ensure_dirs() to include LOGS_DIR**

```python
def ensure_dirs() -> None:
    for path in [
        AGENTS_DIR,
        CONFIG_DIR,
        PROMPTS_DIR,
        SKILLS_DIR,
        RUNTIME_DIR,
        RUNS_DIR,
        CHUNKS_DIR,
        RESULTS_DIR,
        REPORTS_DIR,
        LOGS_DIR,  # 新增
    ]:
        path.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 3: Update reset_runtime_logs() to clear logs directory**

```python
def reset_runtime_logs(runtime_dir: Path = RUNTIME_DIR) -> None:
    for name in ("pipeline.log", "run_log.jsonl"):
        path = runtime_dir / name
        if path.exists():
            path.unlink()
    # 新增：清理 logs 目录
    logs_dir = runtime_dir / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir, ignore_errors=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Update copy_current_run_archive() to archive logs directory**

```python
# Replace line 453: for name in ("chunks", "results"):
for name in ("chunks", "results", "logs"):
```

- [ ] **Step 5: Run existing tests to verify no breakage**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass

- [ ] **Step 6: Commit**

```bash
git add .agents/tools/common.py
git commit -m "feat: add LOGS_DIR infrastructure and update archive/reset logic"
```

---

### Task 2: Update ProviderProtocol signature in base.py

**Files:**
- Modify: `.agents/tools/providers/base.py:39-41`

- [ ] **Step 1: Update classify_runtime_error signature in ProviderProtocol**

```python
# Replace line 39-41
def classify_runtime_error(self, stderr: str, stdout: str = "") -> str:
    """Classify runtime errors from stderr and stdout output."""
    ...
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/providers/base.py
git commit -m "feat: extend ProviderProtocol classify_runtime_error signature"
```

---

### Task 3: Extend codex.py classify_runtime_error

**Files:**
- Modify: `.agents/tools/providers/codex.py:39-45`

- [ ] **Step 1: Update classify_runtime_error to accept stdout and detect quota errors**

```python
def classify_runtime_error(stderr: str, stdout: str = "") -> str:
    # 优先从 stdout 分析（codex 主要输出在 stdout）
    text = (stdout or stderr or "").lower()
    if "usage limit" in text or "upgrade to pro" in text or "quota" in text:
        return ERROR_KIND_AUTH_ERROR
    if "failed to connect to websocket" in text or "api.openai.com/v1/responses" in text or "stream disconnected before completion" in text:
        return ERROR_KIND_NETWORK_ERROR
    if "auth" in text and ("login" in text or "token" in text or "credential" in text):
        return ERROR_KIND_AUTH_ERROR
    return ERROR_KIND_RUNTIME_ERROR
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/providers/codex.py
git commit -m "feat: codex classify_runtime_error analyzes stdout for quota errors"
```

---

### Task 4: Extend claude.py classify_runtime_error

**Files:**
- Modify: `.agents/tools/providers/claude.py:22-28`

- [ ] **Step 1: Update classify_runtime_error to accept stdout**

```python
def classify_runtime_error(stderr: str, stdout: str = "") -> str:
    # 优先从 stdout 分析（claude 主要输出在 stdout）
    text = (stdout or stderr or "").lower()
    if "anthropic_api_key" in text or "authentication" in text or "login" in text or "unauthorized" in text:
        return ERROR_KIND_AUTH_ERROR
    if "rate limit" in text or "429" in text:
        return ERROR_KIND_AUTH_ERROR
    if "network" in text or "timed out" in text or "econn" in text or "socket" in text:
        return ERROR_KIND_NETWORK_ERROR
    return ERROR_KIND_RUNTIME_ERROR
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/providers/claude.py
git commit -m "feat: claude classify_runtime_error analyzes stdout"
```

---

### Task 5: Extend opencode.py classify_runtime_error

**Files:**
- Modify: `.agents/tools/providers/opencode.py:24-38`

- [ ] **Step 1: Update classify_runtime_error to accept stdout**

```python
def classify_runtime_error(stderr: str, stdout: str = "") -> str:
    """Classify runtime errors from stderr and stdout output."""
    # 优先从 stdout 分析（opencode 主要输出在 stdout）
    text = (stdout or stderr or "").lower()
    if "auth" in text or "login" in text or "unauthorized" in text or "api key" in text or "credentials" in text:
        return ERROR_KIND_AUTH_ERROR
    if (
        "network" in text
        or "timeout" in text
        or "timed out" in text
        or "connection refused" in text
        or "dial tcp" in text
        or "zen/v1/messages" in text
    ):
        return ERROR_KIND_NETWORK_ERROR
    return ERROR_KIND_RUNTIME_ERROR
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/providers/opencode.py
git commit -m "feat: opencode classify_runtime_error analyzes stdout"
```

---

### Task 6: Update agent_runner.py to pass stdout to classify

**Files:**
- Modify: `.agents/tools/agent_runner.py:117-119`

- [ ] **Step 1: Pass stdout to classify_runtime_error**

```python
# Replace lines 117-119
if completed.returncode != 0:
    classify_fn = getattr(provider, "classify_runtime_error", None)
    if callable(classify_fn):
        error_kind = classify_fn(completed.stderr, completed.stdout)
    else:
        # Fallback for providers without classify_runtime_error method
        error_kind = ERROR_KIND_RUNTIME_ERROR
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/agent_runner.py
git commit -m "feat: pass stdout to classify_runtime_error"
```

---

### Task 7: Add log writing helper in run_fix_pipeline.py

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py`

- [ ] **Step 1: Add imports and helper function after existing imports**

```python
from common import LOGS_DIR, get_selected_agent_provider_name

def write_chunk_execution_log(
    chunk_index: int,
    attempt: int,
    provider: str,
    command: str,
    cwd: str,
    staging_dir: str,
    prompt: str,
    stdout: str,
    stderr: str,
    returncode: int,
    error_kind: str,
    started_at: str,
    finished_at: str,
) -> Path:
    """Write execution log for a chunk attempt. Returns log path."""
    log_path = LOGS_DIR / f"chunk_{chunk_index:03d}.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # Append mode for retry scenarios
    mode = "a" if attempt > 1 else "w"
    with open(log_path, mode, encoding="utf-8") as f:
        if attempt > 1:
            f.write(f"\n--- ATTEMPT {attempt} ---\n")
        else:
            f.write(f"=== CHUNK {chunk_index:03d} EXECUTION LOG ===\n")
            f.write(f"Started: {started_at}\n")
            f.write(f"Provider: {provider}\n")
            f.write(f"Command: {command}\n")
            f.write(f"CWD: {cwd}\n")
            f.write(f"Staging: {staging_dir}\n")
            f.write(f"Prompt length: {len(prompt)} characters\n")
            f.write("\n--- STDOUT ---\n")
        f.write(stdout or "(empty)")
        f.write("\n--- STDERR ---\n")
        f.write(stderr or "(empty)")
        if attempt == 1 or mode == "w":
            f.write("\n--- END ---\n")
            f.write(f"Returncode: {returncode}\n")
            f.write(f"Error kind: {error_kind}\n")
            f.write(f"Finished: {finished_at}\n")

    return log_path
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat: add write_chunk_execution_log helper"
```

---

### Task 8: Add summary extraction helper in run_fix_pipeline.py

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py`

- [ ] **Step 1: Add extract_error_summary function**

```python
PROVIDER_ERROR_KEYWORDS = {
    "codex": ["usage limit", "upgrade to pro", "quota", "rate limit"],
    "claude": ["anthropic_api_key", "authentication", "rate limit", "429"],
    "opencode": ["zen/v1/messages", "api key", "credentials", "auth"],
}
COMMON_ERROR_KEYWORDS = ["ERROR:", "FATAL:", "failed to", "fatal error"]

def extract_error_summary(stdout: str, stderr: str, provider: str) -> str:
    """Extract key error lines from stdout/stderr output."""
    # Combine outputs, prioritize stdout (where most errors appear)
    combined = stdout or stderr or ""
    if not combined:
        return ""

    # Get last 50 lines
    lines = combined.strip().split("\n")[-50:]

    # Provider-specific keywords first
    provider_keywords = PROVIDER_ERROR_KEYWORDS.get(provider, [])
    all_keywords = provider_keywords + COMMON_ERROR_KEYWORDS

    # Find matching lines
    error_lines = []
    for line in lines:
        line_lower = line.lower()
        for keyword in all_keywords:
            if keyword.lower() in line_lower:
                error_lines.append(line.strip())
                break
        if len(error_lines) >= 3:
            break

    if error_lines:
        return "\n".join(error_lines)

    # Fallback: last 200 chars of stdout
    return (stdout or "")[-200:].strip()
```

- [ ] **Step 2: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat: add extract_error_summary helper"
```

---

### Task 9: Integrate log writing and improved failure output

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:233-279`

- [ ] **Step 1: Modify the retry loop to write logs and show improved summary**

Locate the `for attempt in range(1, max_attempts + 1):` loop. Replace the failure handling section:

```python
        for attempt in range(1, max_attempts + 1):
            config = load_json(CONFIG_DIR / "pipeline.json", {})
            chunk_payload = load_chunk_payload(idx)
            started_at = now_iso()
            result = run_chunk_agent(config, chunk_payload)
            finished_at = now_iso()
            rc = int(result.get("returncode", 1))
            last_rc = rc
            last_error_kind = str(result.get("error_kind", "")).strip()
            last_result = result  # Keep for final summary

            # Write execution log
            provider_name = get_selected_agent_provider_name(config)
            command_str = " ".join(result.get("prompt", "")[:100] if result.get("prompt") else "")
            spec = result.get("spec", {})
            log_path = write_chunk_execution_log(
                chunk_index=idx,
                attempt=attempt,
                provider=provider_name,
                command=command_str,
                cwd=str(ROOT),
                staging_dir=str(resolve_agent_staging_dir(config) / f"chunk_{idx:03d}"),
                prompt=result.get("prompt", ""),
                stdout=result.get("stdout", ""),
                stderr=result.get("stderr", ""),
                returncode=rc,
                error_kind=last_error_kind or ERROR_KIND_RUNTIME_ERROR,
                started_at=started_at,
                finished_at=finished_at,
            )

            result_json = RESULTS_DIR / f"chunk_{idx:03d}_result.json"
            imported_paths = result.get("imported_paths", {})
            imported_result_json = None
            if isinstance(imported_paths, dict):
                imported_path_value = imported_paths.get("chunk_result_json_path")
                if imported_path_value:
                    imported_result_json = Path(str(imported_path_value))
            success = rc == 0 and (
                (imported_result_json is not None and imported_result_json.exists())
                or result_json.exists()
            )

            if success:
                # ... (existing success handling unchanged)
                break

            exhausted = attempt >= max_attempts
            mark_failure(progress, idx, rc, attempt, exhausted)

            # Improved failure output
            if result.get("returncode") != 0:
                summary = extract_error_summary(
                    result.get("stdout", ""),
                    result.get("stderr", ""),
                    provider_name
                )
                print(f"[run] Chunk {idx} 失败: {last_error_kind or 'unknown'}")
                print(f"[run] 查看完整日志: {log_path}")
                if summary:
                    print(f"[run] 错误摘要: {summary}")

            save_json(progress_path, progress)

        # After loop, handle final failure
        if not success:
            # ... (existing final failure handling, but use last_result for verbose)
```

- [ ] **Step 2: Run quick smoke test**

Run: `python -c "from run_fix_pipeline import write_chunk_execution_log, extract_error_summary; print('imports OK')"`
Expected: "imports OK"

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat: integrate log writing and improved failure summary"
```

---

### Task 10: Add --verbose flag

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:14-61` (parse_args)
- Modify: `.agents/tools/run_fix_pipeline.py:281-292` (final failure output)

- [ ] **Step 1: Add --verbose argument to parse_args**

```python
parser.add_argument(
    "--verbose",
    action="store_true",
    help="Print full stdout/stderr after each chunk completes (last attempt only).",
)
```

- [ ] **Step 2: Add verbose output after final failure**

After the `if not success:` block, add verbose output:

```python
        if not success:
            progress["status"] = "failed"
            progress["last_chunk_finished_at"] = now_iso()
            progress["last_failure"] = {
                "chunk_index": idx,
                "returncode": last_rc,
                "retries": args.retry_failed,
                "error_kind": last_error_kind or ERROR_KIND_RUNTIME_ERROR,
            }
            save_json(progress_path, progress)

            # Verbose output (last attempt only)
            if args.verbose and last_result:
                print(f"\n=== CHUNK {idx:03d} STDOUT (verbose) ===")
                print(last_result.get("stdout", "(empty)"))
                print(f"\n=== CHUNK {idx:03d} STDERR (verbose) ===")
                print(last_result.get("stderr", "(empty)"))

            print(f"Chunk {idx} failed after {max_attempts} attempt(s).")
            return 1
```

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat: add --verbose flag for full output after failure"
```

---

### Task 11: Integration test with validate-real

**Files:**
- No file changes (testing only)

- [ ] **Step 1: Run validate-real to verify logs are created**

Run: `python .agents/tools/pipeline_cli.py validate-real --provider claude --keep-workdir`
Expected: Logs directory created with chunk_001.log

- [ ] **Step 2: Verify log file format**

Run: `cat /tmp/real-validate-claude-*/.agents/runtime/logs/chunk_001.log`
Expected: Log contains Started, Provider, STDOUT, STDERR, Returncode sections

- [ ] **Step 3: Test --verbose flag**

Run: `python .agents/tools/pipeline_cli.py validate-real --provider claude --verbose --keep-workdir`
Expected: Full stdout/stderr printed after chunk execution

- [ ] **Step 4: Final commit (if any adjustments needed)**

```bash
git add -A
git commit -m "test: verify execution log integration"
```

---

## Self-Review Checklist

| Spec Requirement | Task Coverage |
|------------------|---------------|
| LOGS_DIR constant | Task 1 Step 1 |
| ensure_dirs update | Task 1 Step 2 |
| reset_runtime_logs update | Task 1 Step 3 |
| copy_current_run_archive update | Task 1 Step 4 |
| ProviderProtocol signature | Task 2 |
| codex classify with stdout/quota | Task 3 |
| claude classify with stdout | Task 4 |
| opencode classify with stdout | Task 5 |
| agent_runner pass stdout | Task 6 |
| write_chunk_execution_log | Task 7 |
| extract_error_summary | Task 8 |
| Log integration in retry loop | Task 9 |
| --verbose flag | Task 10 |
| Integration test | Task 11 |

**Placeholder scan:** No TBD, TODO, or vague steps.

**Type consistency:** All classify_runtime_error signatures use `stderr: str, stdout: str = ""`.