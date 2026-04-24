from __future__ import annotations

from typing import Any, Dict

from common import RUNTIME_DIR
from .base import build_chunk_prompt, build_chunk_staging_paths, get_selected_launch

PROVIDER_NAME = "opencode"
SUPPORTED_PROMPT_VIA = {"stdin", "arg"}
NON_INTERACTIVE_COMMAND_PREFIX = ["opencode"]
SANITIZED_ENV_KEYS = set()

OPENCODE_APPEND_SYSTEM_PROMPT = (
    "Use the local cppcheck-misra-fix skill from the current workspace when available. "
    "Follow the staging output format contract defined in the cppcheck-misra-fix SKILL.md file."
)


def prepare_launch_env(env: Dict[str, str]) -> None:
    """Prepare environment for OpenCode CLI.

    Sets XDG_DATA_HOME and XDG_STATE_HOME to workspace-local directories
    to keep OpenCode state isolated to the project workspace.
    """
    from common import ROOT
    env["XDG_DATA_HOME"] = str(ROOT / ".opencode" / "data")
    env["XDG_STATE_HOME"] = str(ROOT / ".opencode" / "state")


def classify_runtime_error(stderr: str) -> str:
    """Classify runtime errors from OpenCode CLI stderr output."""
    text = (stderr or "").lower()
    if "auth" in text or "login" in text:
        return "auth_error"
    if "network" in text or "timeout" in text:
        return "network_error"
    return "runtime_error"


def build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    """Build launch specification for OpenCode CLI.

    Args:
        config: Pipeline configuration dict
        chunk: Chunk information dict

    Returns:
        Launch specification dict with argv, prompt, and execution settings
    """
    launch = get_selected_launch(config)
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_paths = build_chunk_staging_paths(config, chunk_index)
    argv = list(launch["argv"])
    if "--add-dir" not in argv:
        argv.extend(["--add-dir", str(staging_paths["chunk_dir"])])
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