from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

from common import ROOT, RUNTIME_DIR
from providers import get_provider

SANITIZED_ENV_KEYS = {
    "CODEX_SANDBOX_NETWORK_DISABLED",
}


def resolve_env_path(value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return path


def _link_or_copy(src: Path, dest: Path) -> None:
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.symlink_to(src)
    except OSError:
        shutil.copy2(src, dest)


def prepare_codex_home(env: Dict[str, str]) -> None:
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


def build_launch_env(env_config: Dict[str, str]) -> Dict[str, str]:
    env = dict(os.environ)
    for key in SANITIZED_ENV_KEYS:
        env.pop(key, None)
    for key, value in env_config.items():
        env[key] = str(resolve_env_path(value))
    prepare_codex_home(env)
    return env


def resolve_cwd(cwd_mode: str, spec: Dict[str, Any]) -> Path:
    if cwd_mode == "project_root":
        return ROOT
    if cwd_mode == "runtime_dir":
        return RUNTIME_DIR
    if cwd_mode == "custom":
        custom = spec.get("cwd_path", "")
        path = Path(str(custom))
        if not path.is_absolute():
            path = ROOT / path
        return path
    return ROOT


def classify_runtime_error(stderr: str) -> str:
    text = (stderr or "").lower()
    if "failed to connect to websocket" in text or "api.openai.com/v1/responses" in text or "stream disconnected before completion" in text:
        return "network_error"
    if "auth" in text and ("login" in text or "token" in text or "credential" in text):
        return "auth_error"
    return "runtime_error"


def run_chunk_agent(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    provider_name = str(config.get("agent", {}).get("provider", "")).strip()
    provider = get_provider(provider_name)
    if provider is None:
        return {
            "returncode": 2,
            "stdout": "",
            "stderr": "unsupported provider",
            "error_kind": "config_error",
            "prompt": "",
        }

    spec = provider.build_launch_spec(config, chunk)
    prompt = str(spec.get("prompt", ""))
    prompt_via = str(spec.get("prompt_via", "stdin"))
    cwd = resolve_cwd(str(spec.get("cwd_mode", "project_root")), spec)
    env = build_launch_env(spec.get("env", {}))

    cmd = list(spec.get("argv", []))
    if prompt_via == "arg":
        cmd.append(prompt)

    try:
        completed = subprocess.run(
            cmd,
            input=prompt if prompt_via == "stdin" else None,
            text=True,
            capture_output=True,
            cwd=str(cwd),
            env=env,
            check=False,
        )
    except OSError as exc:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "error_kind": "spawn_error",
            "prompt": prompt,
        }

    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "error_kind": "" if completed.returncode == 0 else classify_runtime_error(completed.stderr),
        "prompt": prompt,
    }
