# kimi-cli Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add kimi-cli as a provider option in the cppcheck/MISRA agent pipeline.

**Architecture:** Extend ProviderProtocol signature with optional `returncode` parameter, create new `kimi.py` provider module using kimi-cli exit codes for error classification, add doctor auth check, update CLI choices and config.

**Tech Stack:** Python 3.8+, unittest, kimi-cli (external tool), subprocess execution

---

## File Structure

| File | Action | Purpose |
|------|--------|---------|
| `.agents/tools/providers/base.py` | MODIFY | Protocol signature: add `Optional[int] returncode` param |
| `.agents/tools/providers/codex.py` | MODIFY | Signature update (param unused) |
| `.agents/tools/providers/claude.py` | MODIFY | Signature update (param unused) |
| `.agents/tools/providers/opencode.py` | MODIFY | Signature update (param unused) |
| `.agents/tools/providers/kimi.py` | CREATE | New provider module |
| `.agents/tools/agent_runner.py` | MODIFY | Pass returncode to classify_runtime_error |
| `.agents/tools/doctor.py` | MODIFY | Add check_kimi_auth + register_check |
| `.agents/tools/pipeline_cli.py` | MODIFY | Add "kimi" to choices |
| `.agents/tools/run_fix_pipeline.py` | MODIFY | Add "kimi" to PROVIDER_ERROR_KEYWORDS |
| `.agents/config/pipeline.json` | MODIFY | Add "kimi" provider config entry |
| `tests/test_agent_runner.py` | MODIFY | Add KimiProviderTests class |
| `tests/test_doctor.py` | MODIFY | Add kimi auth check tests |
| `tests/test_pipeline_cli.py` | MODIFY | Add "kimi" to provider_choices test |

---

### Task 1: Protocol Signature Extension (base.py)

**Files:**
- Modify: `.agents/tools/providers/base.py:39-45`

- [ ] **Step 1: Read base.py to find classify_runtime_error signature**

Run: `head -50 .agents/tools/providers/base.py`
Focus: Find the `classify_runtime_error` method in `ProviderProtocol` class

- [ ] **Step 2: Add Optional import and update signature**

```python
# At top of file, update typing import (line 4)
from typing import Any, Dict, Optional, Protocol

# Update classify_runtime_error signature in ProviderProtocol (line 39-41)
def classify_runtime_error(self, stderr: str, stdout: str = "", returncode: Optional[int] = None) -> str:
    """Classify runtime errors from stderr, stdout, and optional returncode.

    Args:
        stderr: Standard error output from agent execution
        stdout: Standard output from agent execution
        returncode: Optional process exit code. New providers can use this
                    for more accurate classification.

    Returns:
        Error kind string: ERROR_KIND_AUTH_ERROR, ERROR_KIND_NETWORK_ERROR,
        or ERROR_KIND_RUNTIME_ERROR
    """
    ...
```

- [ ] **Step 3: Run existing tests to verify no breakage**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_agent_runner.py -v`
Expected: All existing tests PASS

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/providers/base.py
git commit -m "feat(providers): extend classify_runtime_error signature with returncode param"
```

---

### Task 2: Update Existing Provider Signatures

**Files:**
- Modify: `.agents/tools/providers/codex.py`
- Modify: `.agents/tools/providers/claude.py`
- Modify: `.agents/tools/providers/opencode.py`

- [ ] **Step 1: Update codex.py signature**

Find the `classify_runtime_error` function (search for "def classify_runtime_error") and update:

```python
# Add Optional import if not present
from typing import Optional

# Update signature (returncode param added, unused)
def classify_runtime_error(stderr: str, stdout: str = "", returncode: Optional[int] = None) -> str:
    # Existing implementation unchanged
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    if "auth" in text or "login" in text or "api_key" in text:
        return ERROR_KIND_AUTH_ERROR
    # ... rest of existing logic unchanged ...
```

- [ ] **Step 2: Update claude.py signature**

Same pattern as codex.py - add `Optional` import and `returncode: Optional[int] = None` parameter.

- [ ] **Step 3: Update opencode.py signature**

Same pattern - add `Optional` import and `returncode` parameter.

- [ ] **Step 4: Run provider tests to verify**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_agent_runner.py::CodexProviderTests ../../tests/test_agent_runner.py::ClaudeProviderTests ../../tests/test_agent_runner.py::OpenCodeProviderTests -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add .agents/tools/providers/codex.py .agents/tools/providers/claude.py .agents/tools/providers/opencode.py
git commit -m "feat(providers): add returncode param to existing provider signatures"
```

---

### Task 3: Update agent_runner.py Call Site

**Files:**
- Modify: `.agents/tools/agent_runner.py:117-122`

- [ ] **Step 1: Read agent_runner.py classify call site**

Run: `grep -n "classify_fn" .agents/tools/agent_runner.py`
Focus: Line ~119 where classify_runtime_error is called

- [ ] **Step 2: Update call to pass returncode**

```python
# Line 117-122, update the classify call
if completed.returncode != 0:
    classify_fn = getattr(provider, "classify_runtime_error", None)
    if callable(classify_fn):
        error_kind = classify_fn(completed.stderr, completed.stdout, completed.returncode)
    else:
        error_kind = ERROR_KIND_RUNTIME_ERROR
```

- [ ] **Step 3: Run agent_runner tests**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_agent_runner.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/agent_runner.py
git commit -m "feat(agent_runner): pass returncode to classify_runtime_error"
```

---

### Task 4: Create kimi.py Provider Module

**Files:**
- Create: `.agents/tools/providers/kimi.py`

- [ ] **Step 1: Write kimi.py module**

```python
from __future__ import annotations

from typing import Any, Dict, Optional

from common import ERROR_KIND_AUTH_ERROR, ERROR_KIND_NETWORK_ERROR, ERROR_KIND_RUNTIME_ERROR, RUNTIME_DIR
from .base import build_chunk_prompt, build_chunk_staging_paths, get_selected_launch

PROVIDER_NAME = "kimi"
SUPPORTED_PROMPT_VIA = {"stdin"}
NON_INTERACTIVE_COMMAND_PREFIX = ["kimi", "--print"]
SANITIZED_ENV_KEYS = set()


def prepare_launch_env(env: Dict[str, str]) -> None:
    """Prepare environment for kimi-cli.

    Sets KIMI_SHARE_DIR to workspace-local directory for isolation
    and disables auto-update for stable pipeline execution.
    """
    from common import ROOT
    env["KIMI_SHARE_DIR"] = str(ROOT / ".agents" / "runtime" / "kimi-home")
    env["KIMI_CLI_NO_AUTO_UPDATE"] = "1"


def classify_runtime_error(stderr: str, stdout: str = "", returncode: Optional[int] = None) -> str:
    """Classify runtime errors using kimi-cli exit codes.

    Kimi-cli print mode uses specific exit codes:
    - 0: Success
    - 1: Permanent failure (auth, config, quota exhausted)
    - 75: Retryable failure (rate limit, server error, timeout)

    Falls back to text patterns if returncode is None.
    """
    # Primary: use exit codes
    if returncode == 75:
        return ERROR_KIND_NETWORK_ERROR
    if returncode == 1:
        # Could be auth, config, or quota - check stderr/stdout for auth hints
        text = f"{stdout or ''}\n{stderr or ''}".lower()
        auth_keywords = ["auth", "login", "unauthorized", "api_key", "token", "quota", "credit"]
        if any(kw in text for kw in auth_keywords):
            return ERROR_KIND_AUTH_ERROR
        return ERROR_KIND_RUNTIME_ERROR

    # Fallback: text pattern matching (for when returncode unavailable)
    text = f"{stdout or ''}\n{stderr or ''}".lower()
    auth_keywords = ["auth", "login", "unauthorized", "api_key", "token", "forbidden", "401", "403"]
    if any(kw in text for kw in auth_keywords):
        return ERROR_KIND_AUTH_ERROR
    network_keywords = ["network", "timeout", "timed out", "connection", "econn", "socket"]
    if any(kw in text for kw in network_keywords):
        return ERROR_KIND_NETWORK_ERROR
    return ERROR_KIND_RUNTIME_ERROR


def build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Build launch specification for kimi-cli print mode."""
    launch = get_selected_launch(config)
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_paths = build_chunk_staging_paths(config, chunk_index)
    argv = list(launch["argv"])

    # Ensure required flags for non-interactive stdin mode
    if "--input-format" not in argv:
        argv.extend(["--input-format", "text"])
    if "--output-format" not in argv:
        argv.extend(["--output-format", "text"])
    if "--yolo" not in argv:
        argv.append("--yolo")

    return {
        "argv": argv,
        "prompt_via": launch.get("prompt_via", "stdin"),
        "cwd_mode": launch.get("cwd", "project_root"),
        "env": dict(launch.get("env", {})),
        "requires_tty": bool(launch.get("requires_tty", False)),
        "output_mode": launch.get("output", {}).get("mode", "exit_code"),
        "prompt": build_chunk_prompt(config, chunk),
        "chunk_index": chunk_index,
        "runtime_dir": str(RUNTIME_DIR),
        "staging_dir": str(staging_paths["chunk_dir"]),
    }
```

- [ ] **Step 2: Verify auto-discovery works**

Run: `cd .agents/tools && python3 -c "from providers import PROVIDERS; print(list(PROVIDERS.keys()))"`
Expected: Output includes `"kimi"` in the list

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/providers/kimi.py
git commit -m "feat(providers): add kimi provider module"
```

---

### Task 5: Add kimi Provider Tests

**Files:**
- Modify: `tests/test_agent_runner.py`

- [ ] **Step 1: Add KimiProviderTests class to test_agent_runner.py**

```python
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / ".agents" / "tools"))

# Add after existing provider test classes (after OpenCodeProviderTests)
class KimiProviderTests(unittest.TestCase):
    def test_kimi_provider_import(self) -> None:
        """Verify kimi provider can be imported and has required attributes."""
        from providers import get_provider, PROVIDERS
        provider = get_provider("kimi")
        self.assertIsNotNone(provider, "kimi provider should be discoverable")
        self.assertEqual(provider.PROVIDER_NAME, "kimi")
        self.assertIn("kimi", PROVIDERS, "kimi should be in PROVIDERS dict")
        self.assertTrue(hasattr(provider, "SANITIZED_ENV_KEYS"))
        self.assertTrue(hasattr(provider, "prepare_launch_env"))
        self.assertTrue(hasattr(provider, "classify_runtime_error"))
        self.assertTrue(hasattr(provider, "build_launch_spec"))

    def test_kimi_provider_builds_launch_spec(self) -> None:
        """Verify build_launch_spec produces correct argv with required flags."""
        import common
        from providers.kimi import build_launch_spec
        config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
        config["agent"]["provider"] = "kimi"
        chunk = {"chunk_index": 1, "fix_strategy": "conservative", "contains_high_risk": False}
        spec = build_launch_spec(config, chunk)
        self.assertEqual(spec["argv"][0], "kimi")
        self.assertIn("--print", spec["argv"])
        self.assertIn("--input-format", spec["argv"])
        self.assertIn("--output-format", spec["argv"])
        self.assertIn("--yolo", spec["argv"])
        self.assertEqual(spec["prompt_via"], "stdin")

    def test_kimi_classify_runtime_error_by_exit_code(self) -> None:
        """Verify classify_runtime_error uses exit codes correctly."""
        from common import ERROR_KIND_AUTH_ERROR, ERROR_KIND_NETWORK_ERROR, ERROR_KIND_RUNTIME_ERROR
        from providers.kimi import classify_runtime_error

        # Exit code 75 -> network_error
        self.assertEqual(classify_runtime_error("", "", returncode=75), ERROR_KIND_NETWORK_ERROR)

        # Exit code 1 + auth keywords -> auth_error
        self.assertEqual(classify_runtime_error("unauthorized access", "", returncode=1), ERROR_KIND_AUTH_ERROR)
        self.assertEqual(classify_runtime_error("", "login required", returncode=1), ERROR_KIND_AUTH_ERROR)
        self.assertEqual(classify_runtime_error("quota exhausted", "", returncode=1), ERROR_KIND_AUTH_ERROR)

        # Exit code 1 + no auth keywords -> runtime_error
        self.assertEqual(classify_runtime_error("some config error", "", returncode=1), ERROR_KIND_RUNTIME_ERROR)

        # returncode=None -> text pattern fallback
        self.assertEqual(classify_runtime_error("auth error", ""), ERROR_KIND_AUTH_ERROR)
        self.assertEqual(classify_runtime_error("timeout", ""), ERROR_KIND_NETWORK_ERROR)
        self.assertEqual(classify_runtime_error("unknown error", ""), ERROR_KIND_RUNTIME_ERROR)
```

- [ ] **Step 2: Run new tests to verify they pass**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_agent_runner.py::KimiProviderTests -v`
Expected: All 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_agent_runner.py
git commit -m "test(agent_runner): add KimiProviderTests for kimi provider"
```

---

### Task 6: Add pipeline.json kimi Config Entry

**Files:**
- Modify: `.agents/config/pipeline.json`

- [ ] **Step 1: Read pipeline.json to find providers section**

Run: `cat .agents/config/pipeline.json`
Focus: Find the `agent.providers` section (line ~46-113)

- [ ] **Step 2: Add kimi entry after opencode**

```json
      "opencode": {
        "launch": {
          "argv": ["opencode", "run", "--dangerously-skip-permissions"],
          "prompt_via": "arg",
          "cwd": "project_root",
          "env": {},
          "requires_tty": false,
          "output": { "mode": "exit_code" }
        },
        "capabilities": {
          "non_interactive": true,
          "workspace_write_required": true
        }
      },
      "kimi": {
        "launch": {
          "argv": ["kimi", "--print"],
          "prompt_via": "stdin",
          "cwd": "project_root",
          "env": {},
          "requires_tty": false,
          "output": { "mode": "exit_code" }
        },
        "capabilities": {
          "non_interactive": true,
          "workspace_write_required": true
        }
      }
    },
```

- [ ] **Step 3: Verify JSON is valid**

Run: `python3 -c "import json; json.load(open('.agents/config/pipeline.json'))"`
Expected: No error output

- [ ] **Step 4: Commit**

```bash
git add .agents/config/pipeline.json
git commit -m "feat(config): add kimi provider entry in pipeline.json"
```

---

### Task 7: Update pipeline_cli.py Choices

**Files:**
- Modify: `.agents/tools/pipeline_cli.py:27-29`

- [ ] **Step 1: Update --provider choices**

```python
# Line 26-30
parser.add_argument(
    "--provider",
    choices=["codex", "claude", "opencode", "kimi"],  # Add "kimi"
    default=None,
    help="Override agent provider from pipeline.json.",
)
```

- [ ] **Step 2: Update test_parse_args_provider_choices in test_pipeline_cli.py**

```python
# Line 77-80, update the provider list
def test_parse_args_provider_choices(self) -> None:
    for provider in ["codex", "claude", "opencode", "kimi"]:  # Add "kimi"
        args = pipeline_cli.parse_args(["--provider", provider, "doctor"])
        self.assertEqual(args.provider, provider)
```

- [ ] **Step 3: Run pipeline_cli tests**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_pipeline_cli.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add .agents/tools/pipeline_cli.py tests/test_pipeline_cli.py
git commit -m "feat(pipeline_cli): add kimi to provider choices"
```

---

### Task 8: Add run_fix_pipeline.py PROVIDER_ERROR_KEYWORDS

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py:59-63`

- [ ] **Step 1: Add kimi entry to PROVIDER_ERROR_KEYWORDS**

```python
# Line 59-63
PROVIDER_ERROR_KEYWORDS = {
    "codex": ["usage limit", "upgrade to pro", "quota", "rate limit"],
    "claude": ["anthropic_api_key", "authentication", "rate limit", "429"],
    "opencode": ["zen/v1/messages", "api key", "credentials", "auth"],
    "kimi": ["login", "unauthorized", "api_key", "token", "quota", "credit", "rate limit"],
}
```

- [ ] **Step 2: Run run_fix_pipeline tests**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_run_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add .agents/tools/run_fix_pipeline.py
git commit -m "feat(run_fix_pipeline): add kimi error keywords"
```

---

### Task 9: Add Doctor kimi Auth Check

**Files:**
- Modify: `.agents/tools/doctor.py`

- [ ] **Step 1: Add check_kimi_auth function after check_opencode_auth**

Find `check_opencode_auth` function (around line 684-737), add new function after it:

```python
def check_kimi_auth(config: Any, root: Path = ROOT) -> Dict[str, Any]:
    """Check kimi-cli authentication status."""
    provider_name = _get_agent_provider_name(config)
    if provider_name != "kimi":
        return make_result(
            "ok",
            "kimi_auth_not_applicable",
            "当前 provider 不是 kimi，跳过认证检查。",
            f"provider: {provider_name or '未设置'}",
        )

    # Check environment variable
    if os.environ.get("KIMI_API_KEY"):
        return make_result(
            "ok",
            "kimi_auth_env_ok",
            "检测到 kimi 可用的环境认证变量。",
            "已检测到 KIMI_API_KEY。",
        )

    # Check credential file
    cred_file = Path.home() / ".kimi" / "credentials" / "kimi-code.json"
    if cred_file.exists():
        return make_result(
            "ok",
            "kimi_auth_credential_ok",
            "检测到 kimi 认证文件。",
            f"路径: {cred_file}",
        )

    return make_result(
        "warning",
        "kimi_auth_manual_check",
        "kimi-cli 认证状态需要人工确认。",
        "请确认已设置 KIMI_API_KEY 环境变量，或运行 `kimi login` 完成认证。",
    )
```

- [ ] **Step 2: Add register_check for kimi at bottom of file**

Find the `register_check` calls at bottom (around line 863-881), add:

```python
# Kimi-specific checks
register_check("kimi", check_kimi_auth)
```

- [ ] **Step 3: Add CHECK_REGISTRY entry**

Find `CHECK_REGISTRY` dict (line 35-40), add `"kimi"` key:

```python
CHECK_REGISTRY: Dict[str, List[CheckFunc]] = {
    "_common": [],
    "claude": [],
    "codex": [],
    "opencode": [],
    "kimi": [],  # Add this
}
```

- [ ] **Step 4: Add doctor tests for kimi auth**

Add to `tests/test_doctor.py`:

```python
class KimiAuthTests(unittest.TestCase):
    def test_check_kimi_auth_env_var(self) -> None:
        """KIMI_API_KEY env var detected."""
        config = {"agent": {"provider": "kimi"}}
        with patch.dict(os.environ, {"KIMI_API_KEY": "test-key"}, clear=True):
            result = doctor.check_kimi_auth(config, root=REPO_ROOT)
        self.assertEqual(result["level"], "ok")
        self.assertEqual(result["code"], "kimi_auth_env_ok")

    def test_check_kimi_auth_credential_file(self) -> None:
        """Credential file detected."""
        config = {"agent": {"provider": "kimi"}}
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            cred_dir = fake_home / ".kimi" / "credentials"
            cred_dir.mkdir(parents=True)
            (cred_dir / "kimi-code.json").write_text("{}")
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(doctor.Path, "home", return_value=fake_home):
                    result = doctor.check_kimi_auth(config, root=REPO_ROOT)
        self.assertEqual(result["level"], "ok")
        self.assertEqual(result["code"], "kimi_auth_credential_ok")

    def test_check_kimi_auth_manual_check(self) -> None:
        """Neither env var nor credential file found."""
        config = {"agent": {"provider": "kimi"}}
        with tempfile.TemporaryDirectory() as tmp:
            fake_home = Path(tmp)
            with patch.dict(os.environ, {}, clear=True):
                with patch.object(doctor.Path, "home", return_value=fake_home):
                    result = doctor.check_kimi_auth(config, root=REPO_ROOT)
        self.assertEqual(result["level"], "warning")
        self.assertEqual(result["code"], "kimi_auth_manual_check")

    def test_check_kimi_auth_not_applicable(self) -> None:
        """Provider is not kimi, skip check."""
        config = {"agent": {"provider": "claude"}}
        result = doctor.check_kimi_auth(config, root=REPO_ROOT)
        self.assertEqual(result["level"], "ok")
        self.assertEqual(result["code"], "kimi_auth_not_applicable")
```

- [ ] **Step 5: Run doctor tests**

Run: `cd .agents/tools && python3 -m pytest ../../tests/test_doctor.py::KimiAuthTests -v`
Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
git add .agents/tools/doctor.py tests/test_doctor.py
git commit -m "feat(doctor): add check_kimi_auth for kimi provider"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run all tests**

Run: `cd .agents/tools && python3 -m pytest ../../tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify provider auto-discovery**

Run: `cd .agents/tools && python3 -c "from providers import PROVIDERS; print(sorted(PROVIDERS.keys()))"`
Expected: `['claude', 'codex', 'kimi', 'opencode']`

- [ ] **Step 3: Verify doctor runs with kimi provider**

Run: `cd .agents/tools && PIPELINE_AGENT_PROVIDER=kimi python3 doctor.py --format json | python3 -c "import sys,json; r=json.load(sys.stdin); print(any(c['code'].startswith('kimi_') for c in r))"`
Expected: `True` (at least one kimi_* check code appears)

- [ ] **Step 4: Final commit (if any remaining changes)**

```bash
git status
# If clean, no action needed
# If uncommitted changes, add and commit
```

---

## Self-Review Checklist

**Spec coverage:**
- [x] Protocol signature extension → Task 1, Task 2
- [x] kimi.py provider module → Task 4
- [x] agent_runner.py call site → Task 3
- [x] pipeline.json config → Task 6
- [x] pipeline_cli.py choices → Task 7
- [x] run_fix_pipeline.py PROVIDER_ERROR_KEYWORDS → Task 8
- [x] doctor.py auth check → Task 9
- [x] test_agent_runner.py KimiProviderTests → Task 5
- [x] test_doctor.py kimi auth tests → Task 9
- [x] test_pipeline_cli.py provider choices → Task 7

**Placeholder scan:** None found - all code blocks complete

**Type consistency:**
- `Optional[int]` used consistently across base.py, codex.py, claude.py, opencode.py, kimi.py
- `classify_runtime_error` signature matches across all files
- `PROVIDER_NAME`, `SANITIZED_ENV_KEYS`, etc. match Protocol attributes