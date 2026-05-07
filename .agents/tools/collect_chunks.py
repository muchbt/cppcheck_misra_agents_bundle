from __future__ import annotations

import argparse
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    LOGS_DIR,
    RESULTS_DIR,
    ROOT,
    RUNTIME_DIR,
    import_chunk_staging_artifacts,
    load_json,
    save_json,
)


@dataclass
class CollectResult:
    host_id: str
    imported_chunks: List[int]
    skipped_conflicts: List[int]
    failed_chunks: List[int]


def import_one_bundle(bundle_path: Path) -> CollectResult:
    with tempfile.TemporaryDirectory() as tmp:
        with tarfile.open(bundle_path, "r:gz") as tar:
            tar.extractall(tmp)
        manifest = load_json(Path(tmp) / "manifest.json", {})

        if manifest.get("format_version", 0) != 1:
            raise SystemExit(
                f"不支持的 bundle 格式版本: {manifest.get('format_version')}"
            )

        local_progress = load_json(RUNTIME_DIR / "progress.json", {})
        if manifest["run_id"] != local_progress.get("run_id"):
            raise SystemExit(
                f"run_id 不匹配: 本地={local_progress.get('run_id')}, 远程={manifest['run_id']}"
            )

        local_completed = set(local_progress.get("completed_chunks", []))
        remote_completed = set(manifest.get("completed_chunks", []))
        conflicts = local_completed & remote_completed
        if conflicts:
            print(f"[collect] 警告: chunk {sorted(conflicts)} 本地已完成，跳过")
            remote_completed -= conflicts

        if manifest.get("has_source_patch"):
            patch_file = Path(tmp) / manifest.get("source_patch_file", "patches/source.patch")
            if patch_file.exists() and patch_file.stat().st_size > 0:
                result = subprocess.run(
                    ["git", "apply", "--3way", str(patch_file)],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    print(f"[collect] git apply 失败，请手动处理: {result.stderr}")

        for idx in sorted(remote_completed):
            src_staging = Path(tmp) / f"staging/chunk_{idx:03d}"
            if not src_staging.exists():
                print(f"[collect] 警告: chunk {idx} staging 不存在，跳过")
                continue
            import_chunk_staging_artifacts(
                src_staging,
                idx,
                runtime_dir=RUNTIME_DIR,
                results_dir=RESULTS_DIR,
            )

        local_progress["completed_chunks"] = sorted(
            set(local_progress.get("completed_chunks", [])) | remote_completed
        )
        remote_failed = set(manifest.get("failed_chunks", []))
        all_completed = set(local_progress["completed_chunks"])
        local_progress["failed_chunks"] = sorted(
            (set(local_progress.get("failed_chunks", [])) | remote_failed) - all_completed
        )
        save_json(RUNTIME_DIR / "progress.json", local_progress)

        for log_file in (Path(tmp) / "logs").glob("chunk_*.log"):
            shutil.copy2(log_file, LOGS_DIR / log_file.name)

    return CollectResult(
        host_id=manifest.get("host_id", "unknown"),
        imported_chunks=sorted(remote_completed),
        skipped_conflicts=sorted(conflicts),
        failed_chunks=sorted(remote_failed),
    )


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="collect_chunks")
    parser.add_argument(
        "--from",
        dest="bundles",
        action="append",
        required=True,
        help="Path to export bundle .tar.gz (repeatable)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    results = []
    for bundle in args.bundles:
        print(f"[collect] 正在导入 {bundle} ...")
        r = import_one_bundle(Path(bundle))
        results.append(r)
        print(
            f"[collect] {r.host_id}: 导入 {len(r.imported_chunks)} chunk, "
            f"跳过 {len(r.skipped_conflicts)} 冲突, "
            f"失败 {len(r.failed_chunks)}"
        )

    progress = load_json(RUNTIME_DIR / "progress.json", {})
    total = progress.get("total_chunks", 0)
    done = len(progress.get("completed_chunks", []))
    print(f"[collect] 汇总: {done}/{total} chunk 已完成")
    if done >= total and total > 0:
        print("[collect] 所有 chunk 已完成，可继续: misra-pipeline run --stage merge")
    else:
        remaining = total - done
        print(f"[collect] 还剩 {remaining} chunk 未完成")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
