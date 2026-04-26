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