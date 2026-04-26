# kimi-cli Provider Design

## Summary

Add kimi-cli as a provider in the cppcheck/MISRA agent pipeline, supporting non-interactive print mode with stdin prompt delivery.

## Architecture

### File Layout

```
.agents/tools/providers/
├── kimi.py              # NEW - kimi provider module
.agents/tools/
├── doctor.py             # Add check_kimi_auth + register_check
├── pipeline_cli.py       # Add "kimi" to --provider choices
├── agent_runner.py       # Pass returncode to classify_runtime_error
.agents/config/
└── pipeline.json         # Add "kimi" entry in agent.providers
```

### Data Flow

1. `pipeline_cli.py --provider kimi run` sets `PIPELINE_AGENT_PROVIDER=kimi`
2. `agent_runner.py` discovers kimi provider via `providers/__init__.py` glob
3. `prepare_launch_env()` sets `KIMI_SHARE_DIR` and `KIMI_CLI_NO_AUTO_UPDATE`
4. `build_launch_spec()` builds argv with required flags
5. Prompt delivered via stdin to `kimi --print`
6. On failure, `classify_runtime_error()` maps exit codes to error types

## kimi.py Provider Module

### Module Attributes

| Attribute | Value |
|-----------|-------|
| `PROVIDER_NAME` | `"kimi"` |
| `SUPPORTED_PROMPT_VIA` | `{"stdin"}` |
| `NON_INTERACTIVE_COMMAND_PREFIX` | `["kimi", "--print"]` |
| `SANITIZED_ENV_KEYS` | `set()` (empty) |

### `prepare_launch_env(env)`

Sets:
- `KIMI_SHARE_DIR` → `<ROOT>/.agents/runtime/kimi-home` (workspace isolation)
- `KIMI_CLI_NO_AUTO_UPDATE` → `"1"` (disable auto-update for stable CI)

### `classify_runtime_error(stderr, stdout, returncode=None)`

Uses kimi-cli exit codes as primary classification:

| Exit Code | Classification | Notes |
|-----------|----------------|-------|
| `75` | `ERROR_KIND_NETWORK_ERROR` | Retryable: 429, 5xx, timeout |
| `1` + auth keywords | `ERROR_KIND_AUTH_ERROR` | login, unauthorized, api_key, token, quota, credit |
| `1` + no auth keywords | `ERROR_KIND_RUNTIME_ERROR` | Config error, permanent failure |
| `None` (no returncode) | Text pattern fallback | Auth/network/runtime via stderr/stdout keywords |

### `build_launch_spec(config, chunk)`

Guard logic adds these flags if not already in argv:
- `--input-format text`
- `--output-format text`
- `--yolo`

pipeline.json contains only minimal argv: `["kimi", "--print"]`.

## Protocol Signature Extension

### `base.py` - ProviderProtocol

```python
def classify_runtime_error(self, stderr: str, stdout: str = "", returncode: int = None) -> str:
```

### `agent_runner.py` - Call Site

```python
error_kind = classify_fn(completed.stderr, completed.stdout, completed.returncode)
```

### Existing Providers

`claude.py`, `codex.py`, `opencode.py` add optional `returncode` parameter but do not use it. Fully backward compatible.

## pipeline.json Configuration

```json
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
```

## Doctor Check

### `check_kimi_auth(config, root)`

1. Check `KIMI_API_KEY` environment variable → ok
2. Check `~/.kimi/credentials/kimi-code.json` file exists → ok
3. Neither found → warning ("manual check required")

## Test Plan

### test_agent_runner.py

- `KimiProviderTests.test_kimi_provider_import` — import + auto-discovery
- `KimiProviderTests.test_kimi_provider_builds_launch_spec` — argv flags
- `KimiProviderTests.test_kimi_classify_runtime_error_by_exit_code` — exit code + text fallback

### test_doctor.py

- `test_check_kimi_auth_env_var` — KIMI_API_KEY detected
- `test_check_kimi_auth_credential_file` — credential file detected
- `test_check_kimi_auth_manual_check` — neither found → warning

### test_pipeline_cli.py

- Modify existing `test_parse_args_provider_choices` to include `"kimi"`

## Notes from Previous Plan Review (2026-04-26-add-kimi-provider.md)

All identified issues resolved in this design:

| Issue | Resolution |
|-------|-----------|
| P1: `Path.rmtree()` bug in tests | Use `tempfile.TemporaryDirectory()` context manager |
| P2-1: Unused `from pathlib import Path` | Import `ROOT` locally inside `prepare_launch_env` |
| P2-2: Redundant argv guard | pipeline.json minimal argv, guard adds flags |
| P2-3: Duplicate test code | Modify existing test, don't add duplicates |
| 遗漏-1: Missing test_agent_runner.py tests | Add `KimiProviderTests` class |
| 遗漏-2: Missing auto-discovery validation | Included in `test_kimi_provider_import` |
