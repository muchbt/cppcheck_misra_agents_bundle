from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict

from common import ERROR_KIND_AUTH_ERROR, ERROR_KIND_NETWORK_ERROR, ERROR_KIND_RUNTIME_ERROR, RUNTIME_DIR
from .base import build_chunk_prompt, build_chunk_staging_paths, get_selected_launch

PROVIDER_NAME = "codex"
SUPPORTED_PROMPT_VIA = {"stdin", "arg"}
NON_INTERACTIVE_COMMAND_PREFIX = ["codex", "exec"]
SANITIZED_ENV_KEYS = {"CODEX_SANDBOX_NETWORK_DISABLED"}

def _link_or_copy(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.symlink_to(src)
    except OSError:
        shutil.copy2(src, dest)


def prepare_launch_env(env: Dict[str, str]) -> None:
    codex_home = env.get("CODEX_HOME", "")
    if not codex_home:
        return

    target_dir = Path(codex_home)
    target_dir.mkdir(parents=True, exist_ok=True)
    shared_home = Path.home() / ".codex"
    for name in ("auth.json", "config.toml"):
        source = shared_home / name
        if source.exists():
            _link_or_copy(source, target_dir / name)


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


def build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    launch = get_selected_launch(config)
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_paths = build_chunk_staging_paths(config, chunk_index)
    argv = list(launch["argv"])
    if "--skip-git-repo-check" not in argv:
        argv.append("--skip-git-repo-check")
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
