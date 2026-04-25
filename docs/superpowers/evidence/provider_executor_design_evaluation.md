# Provider (Executor) Abstraction Layer Design Evaluation

**Document ID:** U-C4
**Date:** 2026-04-24
**Status:** Final

## 1. Executive Summary

**Conclusion: Keep the Provider (Executor) abstraction layer.**

The current provider abstraction provides essential value for multi-agent orchestration, unified error handling, and environment isolation. Removing it would sacrifice operational flexibility and increase maintenance complexity across different agent CLI implementations.

---

## 2. Current Design Analysis

The provider abstraction layer is implemented in `.agents/tools/providers/`:

| Module | Role |
|--------|------|
| `base.py` | Protocol definition, shared utilities (`ProviderProtocol`, `build_chunk_prompt`, `build_chunk_staging_paths`) |
| `claude.py` | Claude Code CLI provider |
| `codex.py` | OpenAI Codex CLI provider |
| `opencode.py` | OpenCode CLI provider |

Each provider module implements five contract members:

1. `PROVIDER_NAME` - Unique identifier for configuration lookup
2. `SANITIZED_ENV_KEYS` - Environment keys to strip before logging (security)
3. `prepare_launch_env(env)` - Provider-specific environment setup
4. `classify_runtime_error(stderr)` - Error kind classification for retry/recovery logic
5. `build_launch_spec(config, chunk)` - Build execution specification (argv, cwd, env, prompt_via)

The `agent_runner.py` consumes this abstraction via `get_provider(name)` and executes subprocess calls generically.

---

## 3. Provider-Specific Differences

### 3.1 Environment Variable Isolation

| Provider | Strategy |
|----------|----------|
| **Claude** | No special env preparation. Auth via `ANTHROPIC_API_KEY` or `claude auth login` global state. |
| **Codex** | Requires `CODEX_HOME` pointing to workspace-local directory. Copies `auth.json` and `config.toml` from `~/.codex/` to workspace. Sanitizes inherited `CODEX_SANDBOX_NETWORK_DISABLED` from user environment. |
| **OpenCode** | Sets `XDG_DATA_HOME` and `XDG_STATE_HOME` to `.opencode/data` and `.opencode/state` within workspace. Isolates CLI state from global `~/.local/share/` and `~/.local/state/`. |

**Implication:** Each provider has distinct state isolation requirements that cannot be handled by a generic SDK.

### 3.2 Error Classification Patterns

| Provider | Auth Error Patterns | Network Error Patterns |
|----------|--------------------|-----------------------|
| **Claude** | `anthropic_api_key`, `authentication`, `login`, `unauthorized` | `network`, `timed out`, `econn`, `socket` |
| **Codex** | `auth` + (`login`|`token`|`credential`) | `failed to connect to websocket`, `stream disconnected`, `api.openai.com/v1/responses` |
| **OpenCode** | `auth`, `login` | `network`, `timeout` |

**Implication:** Error classification logic is provider-specific and cannot be derived from a generic SDK error type hierarchy.

### 3.3 CLI Invocation Differences

| Provider | Command Prefix | Special CLI Arguments |
|----------|---------------|----------------------|
| **Claude** | `["claude", "-p"]` | `--append-system-prompt` for skill injection |
| **Codex** | `["codex", "exec"]` | `--full-auto`, `--add-dir` |
| **OpenCode** | `["opencode"]` | `--add-dir` |

**Implication:** CLI argument construction varies significantly; the `build_launch_spec` abstraction handles this cleanly.

---

## 4. Arguments for Keeping the Abstraction

### 4.1 Multi-Agent Switching

The abstraction enables runtime provider switching with a single config change:

```json
"agent": {
  "provider": "codex"  // Change to "claude" or "opencode"
}
```

Without the abstraction, switching would require:
- Rewriting CLI invocation logic
- Changing error handling patterns
- Modifying environment setup code
- Updating documentation

### 4.2 TTY/Non-TTY Execution Handling

The `launch.requires_tty` flag is provider-dependent:
- Some CLI tools require interactive TTY for authentication flows
- The pipeline runs in non-interactive mode (`subprocess.run` with `capture_output=True`)
- The abstraction centralizes this decision in configuration, not code

### 4.3 Unified Error Classification

The pipeline needs consistent error kinds for retry logic:
- `auth_error` - Prompt user to re-authenticate
- `network_error` - Retry with exponential backoff
- `timeout` - Extend timeout or retry
- `runtime_error` - Log and continue

Provider-specific classification maps stderr patterns to these unified categories.

### 4.4 Security - Environment Sanitization

`SANITIZED_ENV_KEYS` ensures sensitive environment variables are stripped before logging:
- Codex: `CODEX_SANDBOX_NETWORK_DISABLED` (could expose network policy)
- Future providers may have additional secrets

This cannot be handled by generic SDK logging.

### 4.5 Workspace Isolation

Each provider has different requirements for keeping state isolated to the project workspace:
- Codex: `CODEX_HOME` directory
- OpenCode: `XDG_DATA_HOME` / `XDG_STATE_HOME`

The abstraction ensures workspace isolation without polluting global user directories.

---

## 5. Arguments for Removing the Abstraction

### 5.1 Reduced Abstraction Complexity

Direct use of agent SDKs (e.g., Anthropic SDK) would:
- Eliminate intermediate layer
- Provide richer API features (streaming, conversation history, tool definitions)

### 5.2 SDK-Native Features

SDKs offer:
- Structured error types with more detail
- Built-in retry logic
- Type-safe configuration

### 5.3 Counterpoint

These benefits assume:
1. **All target agents have SDKs** - OpenCode and Codex CLI do not have Python SDKs with equivalent features
2. **SDKs support CLI-mode execution** - The current pipeline uses CLI subprocess mode, not SDK API calls
3. **SDKs handle environment isolation** - SDKs typically use global state, not workspace-local isolation

The pipeline's subprocess execution model is incompatible with SDK-based invocation. The CLI mode is required for:
- Workspace isolation (per-provider state directories)
- Skill injection via CLI arguments (`--append-system-prompt`)
- Non-interactive execution (`--permission-mode acceptEdits`)

---

## 6. Decision

**Keep the Provider (Executor) abstraction layer.**

### Rationale

1. **Multi-provider support is a core requirement** - The pipeline must support Claude Code, Codex, and OpenCode without code changes.

2. **Provider-specific behaviors cannot be abstracted by SDKs** - Environment isolation, error classification, and CLI argument construction are unique per provider.

3. **CLI subprocess execution is the correct model** - Workspace isolation and skill injection require CLI mode, not SDK API calls.

4. **Abstraction complexity is justified** - The current design is simple (module-level functions, not class hierarchies) and provides measurable value.

### Recommended Enhancements

1. Add a `timeout` field to `launch` spec for provider-specific timeout handling
2. Consider adding `retry_config` for network errors with provider-specific defaults
3. Document `ProviderProtocol` contract more explicitly in code comments

---

## 7. Related Files

- `.agents/tools/providers/base.py` - Protocol definition
- `.agents/tools/providers/claude.py` - Claude provider
- `.agents/tools/providers/codex.py` - Codex provider
- `.agents/tools/providers/opencode.py` - OpenCode provider
- `.agents/tools/agent_runner.py` - Executor consumer
- `README.md` - User-facing provider configuration documentation