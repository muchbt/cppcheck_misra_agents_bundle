from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict

from common import ROOT, RUNTIME_DIR
from providers import get_provider


def build_launch_env(env_config: Dict[str, str]) -> Dict[str, str]:
    env = dict(os.environ)
    for key, value in env_config.items():
        path = Path(value)
        if not path.is_absolute():
            path = ROOT / path
        env[key] = str(path)
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
        "error_kind": "" if completed.returncode == 0 else "runtime_error",
        "prompt": prompt,
    }
