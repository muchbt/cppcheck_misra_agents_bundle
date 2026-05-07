from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from common import (
    CONFIG_DIR,
    LOGS_DIR,
    ROOT,
    RUNTIME_DIR,
    load_json,
    now_iso,
    resolve_agent_staging_dir,
    save_json,
)


def resolve_host_id(args: argparse.Namespace) -> str:
    """三级优先级解析 host identifier：--host-id > PIPELINE_HOST_ID > socket.gethostname()"""
    return (
        getattr(args, "host_id", None)
        or os.environ.get("PIPELINE_HOST_ID", "").strip()
        or socket.gethostname()
    )


def try_generate_patch(root: Path = ROOT) -> Tuple[Optional[str], str]:
    """尝试生成 git diff patch。失败则降级返回 None 和提示信息。"""
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=30,
        )
        if r.returncode != 0:
            return None, "git diff 失败，跳过 source patch"
        if not r.stdout.strip():
            return None, "无源码修改"
        return r.stdout, f"已生成 source patch ({len(r.stdout)} bytes)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "git 不可用或超时，跳过 source patch（请自行同步源码修改）"


def build_manifest(
    run_id: str,
    host_id: str,
    completed_chunks: List[int],
    failed_chunks: List[int],
    chunk_ids_requested: List[int],
    has_source_patch: bool,
    staging_dirs: List[str],
) -> Dict[str, Any]:
    return {
        "format_version": 1,
        "run_id": run_id,
        "host_id": host_id,
        "exported_at": now_iso(),
        "completed_chunks": completed_chunks,
        "failed_chunks": failed_chunks,
        "chunk_ids_requested": chunk_ids_requested,
        "has_source_patch": has_source_patch,
        "source_patch_file": "patches/source.patch" if has_source_patch else None,
        "staging_dirs": staging_dirs,
    }


def _add_json(tar: tarfile.TarFile, data: Any, arcname: str) -> None:
    import io
    content = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    info = tarfile.TarInfo(name=arcname)
    info.size = len(content)
    tar.addfile(info, io.BytesIO(content))


def _add_text(tar: tarfile.TarFile, content: str, arcname: str) -> None:
    import io
    data = content.encode("utf-8")
    info = tarfile.TarInfo(name=arcname)
    info.size = len(data)
    tar.addfile(info, io.BytesIO(data))


def create_bundle(
    output_path: Path,
    manifest: Dict[str, Any],
    patch_content: Optional[str],
    completed_export: List[int],
    staging_base: Path,
    all_ids: List[int],
    logs_dir: Path,
) -> None:
    with tarfile.open(output_path, "w:gz") as tar:
        _add_json(tar, manifest, "manifest.json")
        if patch_content:
            _add_text(tar, patch_content, "patches/source.patch")
        for idx in completed_export:
            src = staging_base / f"chunk_{idx:03d}"
            if src.exists():
                for f in src.iterdir():
                    tar.add(f, arcname=f"staging/chunk_{idx:03d}/{f.name}")
        for idx in all_ids:
            log = logs_dir / f"chunk_{idx:03d}.log"
            if log.exists():
                tar.add(log, arcname=f"logs/chunk_{idx:03d}.log")
