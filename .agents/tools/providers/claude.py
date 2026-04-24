from __future__ import annotations

from typing import Any, Dict

from common import RUNTIME_DIR
from .base import build_chunk_prompt, build_chunk_staging_paths, get_selected_launch

SUPPORTED_PROMPT_VIA = {"stdin", "arg"}
NON_INTERACTIVE_COMMAND_PREFIX = ["claude", "-p"]
SANITIZED_ENV_KEYS = set()
CLAUDE_APPEND_SYSTEM_PROMPT = (
    "Use the local cppcheck-misra-fix skill from the current workspace when available. "
    "Follow the staging output format contract defined in the cppcheck-misra-fix SKILL.md file."
)


def prepare_launch_env(env: Dict[str, str]) -> None:
    return None


def classify_runtime_error(stderr: str) -> str:
    text = (stderr or "").lower()
    if "anthropic_api_key" in text or "authentication" in text or "login" in text or "unauthorized" in text:
        return "auth_error"
    if "network" in text or "timed out" in text or "econn" in text or "socket" in text:
        return "network_error"
    return "runtime_error"


def build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    launch = get_selected_launch(config)
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_paths = build_chunk_staging_paths(config, chunk_index)
    argv = list(launch["argv"])
    if "--add-dir" not in argv:
        argv.extend(["--add-dir", str(staging_paths["chunk_dir"])])
    if "--append-system-prompt" not in argv:
        argv.extend(["--append-system-prompt", CLAUDE_APPEND_SYSTEM_PROMPT])
    return {
        "argv": argv,
        "prompt_via": launch["prompt_via"],
        "cwd_mode": launch["cwd"],
        "env": dict(launch.get("env", {})),
        "requires_tty": bool(launch["requires_tty"]),
        "output_mode": launch.get("output", {}).get("mode", "exit_code"),
        "prompt": build_chunk_prompt(config, chunk),
        "chunk_index": chunk_index,
        "runtime_dir": str(RUNTIME_DIR),
        "staging_dir": str(staging_paths["chunk_dir"]),
    }
