from __future__ import annotations

import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict

from common import ERROR_KIND_CONFIG_ERROR, ERROR_KIND_RUNTIME_ERROR, ERROR_KIND_SPAWN_ERROR, ERROR_KIND_IMPORT_ERROR, ROOT, import_chunk_staging_artifacts, prepare_chunk_staging_dir
from providers import get_provider


def runtime_dir_for_root(root: Path = ROOT) -> Path:
    return root / ".agents" / "runtime"


def resolve_env_path(value: str, root: Path = ROOT) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


def build_launch_env(env_config: Dict[str, str], provider: Any, root: Path = ROOT) -> Dict[str, str]:
    env = dict(os.environ)
    for key in getattr(provider, "SANITIZED_ENV_KEYS", set()):
        env.pop(key, None)
    for key, value in env_config.items():
        env[key] = str(resolve_env_path(value, root=root))
    prepare_launch_env = getattr(provider, "prepare_launch_env", None)
    if callable(prepare_launch_env):
        prepare_launch_env(env)
    return env


def resolve_cwd(cwd_mode: str, spec: Dict[str, Any], root: Path = ROOT) -> Path:
    if cwd_mode == "project_root":
        return root
    if cwd_mode == "runtime_dir":
        return runtime_dir_for_root(root)
    if cwd_mode == "custom":
        custom = spec.get("cwd_path", "")
        path = Path(str(custom))
        if not path.is_absolute():
            path = root / path
        return path
    return root

def run_chunk_agent(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    current_root = ROOT
    provider_name = str(config.get("agent", {}).get("provider", "")).strip()
    provider = get_provider(provider_name)
    if provider is None:
        return {
            "returncode": 2,
            "stdout": "",
            "stderr": "unsupported provider",
            "error_kind": ERROR_KIND_CONFIG_ERROR,
            "prompt": "",
        }

    spec = provider.build_launch_spec(config, chunk)
    prompt = str(spec.get("prompt", ""))
    prompt_via = str(spec.get("prompt_via", "stdin"))
    cwd = resolve_cwd(str(spec.get("cwd_mode", "project_root")), spec, root=current_root)
    env = build_launch_env(spec.get("env", {}), provider, root=current_root)
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_dir = Path(str(spec.get("staging_dir", "")).strip()) if str(spec.get("staging_dir", "")).strip() else None
    if staging_dir is not None:
        prepare_chunk_staging_dir(staging_dir)

    cmd = list(spec.get("argv", []))
    if prompt_via == "arg":
        cmd.append(prompt)

    stdin_desc = "stdin=<prompt>" if prompt_via == "stdin" else "stdin=DEVNULL"
    print(f"[agent_runner] provider={provider_name} chunk={chunk_index} prompt_via={prompt_via} {stdin_desc}")
    print(f"[agent_runner] cwd={cwd}")
    print(f"[agent_runner] argv: {shlex.join(cmd)}")
    if len(cmd) != len([a for a in cmd if a == cmd[cmd.index(a)]]):
        print(f"[agent_runner] full_argv: {cmd}")

    # --- Popen + streaming stdout ---
    popen_kwargs: Dict[str, Any] = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd),
        env=env,
    )
    if prompt_via == "stdin":
        popen_kwargs["stdin"] = subprocess.PIPE
    else:
        popen_kwargs["stdin"] = subprocess.DEVNULL

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except OSError as exc:
        return {
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "error_kind": ERROR_KIND_SPAWN_ERROR,
            "prompt": prompt,
        }

    # Write prompt to stdin if needed, then close stdin
    if prompt_via == "stdin":
        try:
            proc.stdin.write(prompt)
            proc.stdin.close()
        except OSError:
            pass

    # Collect stderr in a background thread to avoid pipe deadlocks
    stderr_buf: list[str] = []

    def _read_stderr() -> None:
        for line in proc.stderr:
            stderr_buf.append(line)

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    # Stream stdout line-by-line to console while capturing it
    stdout_buf: list[str] = []
    prefix = f"[claude:chunk_{chunk_index:03d}] "
    for line in proc.stdout:
        stdout_buf.append(line)
        sys.stdout.write(f"{prefix}{line}")
        sys.stdout.flush()

    proc.wait()
    stderr_thread.join(timeout=5)

    returncode = proc.returncode
    stdout_text = "".join(stdout_buf)
    stderr_text = "".join(stderr_buf)

    if returncode == 0 and staging_dir is not None:
        try:
            runtime_dir = runtime_dir_for_root(current_root)
            imported_paths = import_chunk_staging_artifacts(
                staging_dir,
                chunk_index,
                runtime_dir=runtime_dir,
                results_dir=runtime_dir / "results",
            )
        except (FileNotFoundError, OSError, ValueError) as exc:
            return {
                "returncode": 1,
                "stdout": stdout_text,
                "stderr": str(exc),
                "error_kind": ERROR_KIND_IMPORT_ERROR,
                "prompt": prompt,
            }
    else:
        imported_paths = {}

    # Classify error if execution failed
    error_kind = ""
    if returncode != 0:
        classify_fn = getattr(provider, "classify_runtime_error", None)
        if callable(classify_fn):
            error_kind = classify_fn(stderr_text, stdout_text, returncode)
        else:
            error_kind = ERROR_KIND_RUNTIME_ERROR

    return {
        "returncode": returncode,
        "stdout": stdout_text,
        "stderr": stderr_text,
        "error_kind": error_kind,
        "prompt": prompt,
        "argv": cmd,
        "imported_paths": imported_paths,
    }
