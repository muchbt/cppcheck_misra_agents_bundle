from __future__ import annotations

import os
import subprocess
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
            "error_kind": ERROR_KIND_SPAWN_ERROR,
            "prompt": prompt,
        }

    if completed.returncode == 0 and staging_dir is not None:
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
                "stdout": completed.stdout,
                "stderr": str(exc),
                "error_kind": ERROR_KIND_IMPORT_ERROR,
                "prompt": prompt,
            }
    else:
        imported_paths = {}

    # Classify error if execution failed
    error_kind = ""
    if completed.returncode != 0:
        classify_fn = getattr(provider, "classify_runtime_error", None)
        if callable(classify_fn):
            error_kind = classify_fn(completed.stderr, completed.stdout)
        else:
            # Fallback for providers without classify_runtime_error method
            error_kind = ERROR_KIND_RUNTIME_ERROR

    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "error_kind": error_kind,
        "prompt": prompt,
        "argv": cmd,
        "imported_paths": imported_paths,
    }
