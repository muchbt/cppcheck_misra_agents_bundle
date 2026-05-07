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


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="export_chunks")
    parser.add_argument(
        "--output", "-o", dest="output", default=None,
        help="Output bundle path (default: export-<run_id>-<host_id>.tar.gz)",
    )
    parser.add_argument(
        "--host-id", dest="host_id", default=None,
        help="Override host identifier",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    progress = load_json(RUNTIME_DIR / "progress.json", {})
    run_id = progress.get("run_id", "unknown")
    completed = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))

    config = load_json(CONFIG_DIR / "pipeline.json", {})
    staging_base = resolve_agent_staging_dir(config)
    completed_export = []
    failed_export = []
    missing_staging = []

    for idx in sorted(completed):
        chunk_staging = staging_base / f"chunk_{idx:03d}"
        if (chunk_staging / "chunk_result.json").exists():
            completed_export.append(idx)
        else:
            missing_staging.append(idx)

    for idx in sorted(failed):
        chunk_staging = staging_base / f"chunk_{idx:03d}"
        if (chunk_staging / "chunk_result.json").exists():
            failed_export.append(idx)

    if missing_staging:
        print(f"[export] 警告: completed chunk {missing_staging} 的 staging 产出物缺失，将跳过")

    all_ids = sorted(completed | failed)
    if not all_ids:
        print("[export] 无已处理 chunk，无需导出。")
        return 0

    patch_content, patch_msg = try_generate_patch()
    print(f"[export] {patch_msg}")

    host_id = resolve_host_id(args)
    manifest = build_manifest(
        run_id=run_id,
        host_id=host_id,
        completed_chunks=completed_export,
        failed_chunks=sorted(failed),
        chunk_ids_requested=all_ids,
        has_source_patch=patch_content is not None,
        staging_dirs=[f"staging/chunk_{idx:03d}" for idx in completed_export],
    )

    output_path = Path(args.output) if args.output else Path(f"export-{run_id}-{host_id}.tar.gz")
    create_bundle(
        output_path=output_path,
        manifest=manifest,
        patch_content=patch_content,
        completed_export=completed_export,
        staging_base=staging_base,
        all_ids=all_ids,
        logs_dir=LOGS_DIR,
    )

    print(f"[export] 已导出 {len(completed_export)} completed + {len(failed_export)} failed chunk → {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
