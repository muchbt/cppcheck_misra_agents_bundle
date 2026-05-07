# 分布式 Chunk 导出/收集功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 `misra-pipeline export` 和 `misra-pipeline collect` 两个 CLI 子命令，支持多设备并行处理 chunk 后的结果打包与回收。

**Architecture:** 新增两个独立的 `.agents/tools/` 模块（`export_chunks.py` 负责 worker 端打包 staging delta 为 tar.gz，`collect_chunks.py` 负责 coordinator 端解包并复用 `import_chunk_staging_artifacts` 导入）。CLI 通过 `PIPELINE_COMMANDS` 注册转发，模块内部自包含参数解析。

**Tech Stack:** Python 3.8+, `tarfile`, `argparse`, `subprocess`, `tempfile`, `pytest`/`unittest`

---

## 文件结构

| 文件 | 类型 | 职责 |
|------|------|------|
| `.agents/tools/export_chunks.py` | 新建 | Worker 端：解析参数、生成 manifest、打包 tar.gz、生成 git patch（降级） |
| `.agents/tools/collect_chunks.py` | 新建 | Coordinator 端：解析参数、解包、校验、导入 staging delta、更新 progress |
| `cli/misra-pipeline-cli.py` | 修改 | 注册 `export`/`collect` 到 `PIPELINE_COMMANDS` 和 `cmd_help`，更新 docstring |
| `tests/test_export_chunks.py` | 新建 | `export_chunks` 单元测试（host_id、patch、manifest、bundle） |
| `tests/test_collect_chunks.py` | 新建 | `collect_chunks` 单元测试（import、冲突、幂等、校验） |
| `tests/test_misra_pipeline_cli.py` | 修改 | CLI 子命令解析测试 |

---

## Task 1: export_chunks 基础工具函数

**Files:**
- Create: `.agents/tools/export_chunks.py`
- Test: `tests/test_export_chunks.py`

### Step 1.1: 编写 `resolve_host_id` 的 failing test

创建 `tests/test_export_chunks.py`：

```python
"""Tests for export_chunks module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import export_chunks  # noqa: E402


def test_resolve_host_id_prefers_cli_flag():
    args = MagicMock()
    args.host_id = "my-host"
    with patch.dict("os.environ", {}, clear=True):
        with patch("export_chunks.socket.gethostname", return_value="socket-host"):
            result = export_chunks.resolve_host_id(args)
    assert result == "my-host"


def test_resolve_host_id_falls_back_to_env():
    args = MagicMock()
    args.host_id = None
    with patch.dict("os.environ", {"PIPELINE_HOST_ID": "env-host"}):
        with patch("export_chunks.socket.gethostname", return_value="socket-host"):
            result = export_chunks.resolve_host_id(args)
    assert result == "env-host"


def test_resolve_host_id_falls_back_to_socket():
    args = MagicMock()
    args.host_id = None
    with patch.dict("os.environ", {}, clear=True):
        with patch("export_chunks.socket.gethostname", return_value="socket-host"):
            result = export_chunks.resolve_host_id(args)
    assert result == "socket-host"


def test_try_generate_patch_returns_content_and_message(tmp_path):
    with patch("export_chunks.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "diff --git a/foo.c b/foo.c\n"
        content, msg = export_chunks.try_generate_patch(tmp_path)
    assert content == "diff --git a/foo.c b/foo.c\n"
    assert "已生成 source patch" in msg
```

### Step 1.2: 运行测试验证失败

```bash
cd /home/ubuntu/code/cppcheck_misra_agents_bundle_v2
python3 -m pytest tests/test_export_chunks.py -xvs
```

**Expected:** 4 FAILs — `AttributeError: module 'export_chunks' has no attribute 'resolve_host_id'` 等

### Step 1.3: 实现 `resolve_host_id` 和 `try_generate_patch`

创建 `.agents/tools/export_chunks.py`，写入骨架和这两个函数：

```python
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
```

### Step 1.4: 运行测试验证通过

```bash
python3 -m pytest tests/test_export_chunks.py -xvs
```

**Expected:** 4 PASSed

### Step 1.5: Commit

```bash
git add tests/test_export_chunks.py .agents/tools/export_chunks.py
git commit -m "feat(export): add resolve_host_id and try_generate_patch utilities"
```

---

## Task 2: export_chunks 核心逻辑

**Files:**
- Modify: `.agents/tools/export_chunks.py`
- Modify: `tests/test_export_chunks.py`

### Step 2.1: 编写 `build_manifest` 和 `create_bundle` 的 failing test

在 `tests/test_export_chunks.py` 末尾追加：

```python
def test_build_manifest_contains_expected_fields():
    manifest = export_chunks.build_manifest(
        run_id="20260507-001",
        host_id="device-B",
        completed_chunks=[3, 4],
        failed_chunks=[5],
        chunk_ids_requested=[3, 4, 5],
        has_source_patch=True,
        staging_dirs=["staging/chunk_003", "staging/chunk_004"],
    )
    assert manifest["format_version"] == 1
    assert manifest["run_id"] == "20260507-001"
    assert manifest["host_id"] == "device-B"
    assert manifest["completed_chunks"] == [3, 4]
    assert manifest["failed_chunks"] == [5]
    assert manifest["has_source_patch"] is True
    assert manifest["source_patch_file"] == "patches/source.patch"
    assert "exported_at" in manifest


def test_create_bundle_writes_tar_gz(tmp_path):
    staging_base = tmp_path / "staging"
    chunk_dir = staging_base / "chunk_003"
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "chunk_result.json").write_text('{"ok": true}')
    (chunk_dir / "issue_status_delta.json").write_text('{}')
    (chunk_dir / "file_change_delta.json").write_text('{}')
    (chunk_dir / "chunk_result.md").write_text("# Result")

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "chunk_003.log").write_text("log line")

    output = tmp_path / "export.tar.gz"
    manifest = export_chunks.build_manifest(
        run_id="20260507-001",
        host_id="device-B",
        completed_chunks=[3],
        failed_chunks=[],
        chunk_ids_requested=[3],
        has_source_patch=False,
        staging_dirs=["staging/chunk_003"],
    )
    export_chunks.create_bundle(
        output_path=output,
        manifest=manifest,
        patch_content=None,
        completed_export=[3],
        staging_base=staging_base,
        all_ids=[3],
        logs_dir=log_dir,
    )
    assert output.exists()
    import tarfile
    with tarfile.open(output, "r:gz") as tar:
        names = tar.getnames()
    assert "manifest.json" in names
    assert "staging/chunk_003/chunk_result.json" in names
    assert "logs/chunk_003.log" in names
```

### Step 2.2: 运行测试验证失败

```bash
python3 -m pytest tests/test_export_chunks.py::test_build_manifest_contains_expected_fields tests/test_export_chunks.py::test_create_bundle_writes_tar_gz -xvs
```

**Expected:** 2 FAILs — `AttributeError: module 'export_chunks' has no attribute 'build_manifest'`

### Step 2.3: 实现 `build_manifest` 和 `create_bundle`

在 `.agents/tools/export_chunks.py` 中追加（`try_generate_patch` 之后）：

```python

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
```

### Step 2.4: 运行测试验证通过

```bash
python3 -m pytest tests/test_export_chunks.py::test_build_manifest_contains_expected_fields tests/test_export_chunks.py::test_create_bundle_writes_tar_gz -xvs
```

**Expected:** 2 PASSed

### Step 2.5: Commit

```bash
git add tests/test_export_chunks.py .agents/tools/export_chunks.py
git commit -m "feat(export): add build_manifest and create_bundle helpers"
```

---

## Task 3: export_chunks parse_args + main()

**Files:**
- Modify: `.agents/tools/export_chunks.py`
- Modify: `tests/test_export_chunks.py`

### Step 3.1: 编写 main() 的 failing 集成测试

在 `tests/test_export_chunks.py` 末尾追加：

```python
def test_main_no_chunks_prints_message(tmp_path, capsys):
    with patch("export_chunks.RUNTIME_DIR", tmp_path / "runtime"):
        with patch("export_chunks.CONFIG_DIR", tmp_path / "config"):
            with patch("export_chunks.LOGS_DIR", tmp_path / "logs"):
                runtime_dir = tmp_path / "runtime"
                runtime_dir.mkdir(parents=True)
                config_dir = tmp_path / "config"
                config_dir.mkdir(parents=True)
                (runtime_dir / "progress.json").write_text(
                    '{"run_id": "20260507-001", "completed_chunks": [], "failed_chunks": []}'
                )
                (config_dir / "pipeline.json").write_text(
                    '{"agent": {"staging_dir": ".agents/staging"}}'
                )
                rc = export_chunks.main(["--output", str(tmp_path / "out.tar.gz")])
    assert rc == 0
    captured = capsys.readouterr()
    assert "无已处理 chunk" in captured.out


def test_main_exports_completed_chunk(tmp_path, capsys):
    with patch("export_chunks.RUNTIME_DIR", tmp_path / "runtime"):
        with patch("export_chunks.CONFIG_DIR", tmp_path / "config"):
            with patch("export_chunks.LOGS_DIR", tmp_path / "logs"):
                with patch("export_chunks.ROOT", tmp_path):
                    with patch("export_chunks.subprocess.run") as mock_git:
                        mock_git.return_value.returncode = 0
                        mock_git.return_value.stdout = ""
                        runtime_dir = tmp_path / "runtime"
                        runtime_dir.mkdir(parents=True)
                        config_dir = tmp_path / "config"
                        config_dir.mkdir(parents=True)
                        staging_base = tmp_path / ".agents" / "staging"
                        staging_base.mkdir(parents=True)
                        chunk_dir = staging_base / "chunk_003"
                        chunk_dir.mkdir()
                        (chunk_dir / "chunk_result.json").write_text('{"ok": true}')
                        (chunk_dir / "issue_status_delta.json").write_text('{}')
                        (chunk_dir / "file_change_delta.json").write_text('{}')
                        (chunk_dir / "chunk_result.md").write_text("# Result")
                        (runtime_dir / "progress.json").write_text(
                            '{"run_id": "20260507-001", "completed_chunks": [3], "failed_chunks": []}'
                        )
                        (config_dir / "pipeline.json").write_text(
                            '{"agent": {"staging_dir": ".agents/staging"}}'
                        )
                        output = tmp_path / "out.tar.gz"
                        rc = export_chunks.main(["--output", str(output)])
    assert rc == 0
    assert output.exists()
    captured = capsys.readouterr()
    assert "已导出" in captured.out
```

### Step 3.2: 运行测试验证失败

```bash
python3 -m pytest tests/test_export_chunks.py::test_main_no_chunks_prints_message tests/test_export_chunks.py::test_main_exports_completed_chunk -xvs
```

**Expected:** 2 FAILs — `AttributeError: module 'export_chunks' has no attribute 'main'`

### Step 3.3: 实现 `parse_args` 和 `main`

在 `.agents/tools/export_chunks.py` 末尾追加：

```python

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
```

### Step 3.4: 运行测试验证通过

```bash
python3 -m pytest tests/test_export_chunks.py -xvs
```

**Expected:** 全部 PASS（当前共 8 个测试）

### Step 3.5: Commit

```bash
git add tests/test_export_chunks.py .agents/tools/export_chunks.py
git commit -m "feat(export): implement parse_args and main()"
```

---

## Task 4: collect_chunks 核心模块

**Files:**
- Create: `.agents/tools/collect_chunks.py`
- Create: `tests/test_collect_chunks.py`

### Step 4.1: 编写 `CollectResult` 和 `import_one_bundle` 的 failing test

创建 `tests/test_collect_chunks.py`：

```python
"""Tests for collect_chunks module."""

import json
import sys
import tarfile
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import collect_chunks  # noqa: E402


def test_collect_result_dataclass():
    r = collect_chunks.CollectResult(
        host_id="device-B",
        imported_chunks=[3, 4],
        skipped_conflicts=[],
        failed_chunks=[5],
    )
    assert r.host_id == "device-B"
    assert r.imported_chunks == [3, 4]


def _make_bundle(tmp_path: Path, manifest: dict, patch_content: str = None, staging_files: dict = None):
    """Helper to create a fake export bundle tar.gz."""
    bundle = tmp_path / "bundle.tar.gz"
    with tarfile.open(bundle, "w:gz") as tar:
        import io
        data = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        info = tarfile.TarInfo(name="manifest.json")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
        if patch_content:
            pdata = patch_content.encode("utf-8")
            pinfo = tarfile.TarInfo(name="patches/source.patch")
            pinfo.size = len(pdata)
            tar.addfile(pinfo, io.BytesIO(pdata))
        if staging_files:
            for arcname, content in staging_files.items():
                cdata = content.encode("utf-8")
                cinfo = tarfile.TarInfo(name=arcname)
                cinfo.size = len(cdata)
                tar.addfile(cinfo, io.BytesIO(cdata))
    return bundle


def test_import_one_bundle_run_id_mismatch_raises(tmp_path):
    manifest = {
        "format_version": 1,
        "run_id": "remote-id",
        "host_id": "device-B",
        "completed_chunks": [3],
        "failed_chunks": [],
    }
    bundle = _make_bundle(tmp_path, manifest)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "progress.json").write_text('{"run_id": "local-id"}')

    with patch("collect_chunks.RUNTIME_DIR", runtime_dir):
        with patch("collect_chunks.RESULTS_DIR", tmp_path / "results"):
            with patch("collect_chunks.LOGS_DIR", tmp_path / "logs"):
                with patch("collect_chunks.import_chunk_staging_artifacts"):
                    with pytest.raises(SystemExit) as exc_info:
                        collect_chunks.import_one_bundle(bundle)
    assert "run_id 不匹配" in str(exc_info.value)


def test_import_one_bundle_format_version_mismatch_raises(tmp_path):
    manifest = {
        "format_version": 99,
        "run_id": "local-id",
        "host_id": "device-B",
        "completed_chunks": [3],
        "failed_chunks": [],
    }
    bundle = _make_bundle(tmp_path, manifest)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "progress.json").write_text('{"run_id": "local-id"}')

    with patch("collect_chunks.RUNTIME_DIR", runtime_dir):
        with patch("collect_chunks.RESULTS_DIR", tmp_path / "results"):
            with patch("collect_chunks.LOGS_DIR", tmp_path / "logs"):
                with pytest.raises(SystemExit) as exc_info:
                    collect_chunks.import_one_bundle(bundle)
    assert "不支持的 bundle 格式版本" in str(exc_info.value)
```

注意：需要在文件顶部 `import sys` 之后添加 `import pytest`。

### Step 4.2: 运行测试验证失败

```bash
python3 -m pytest tests/test_collect_chunks.py -xvs
```

**Expected:** FAILs — `ModuleNotFoundError: No module named 'collect_chunks'` 以及 `AttributeError`

### Step 4.3: 实现 `collect_chunks.py` 骨架 + `CollectResult` + `import_one_bundle`

创建 `.agents/tools/collect_chunks.py`：

```python
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
```

### Step 4.4: 运行测试验证通过

```bash
python3 -m pytest tests/test_collect_chunks.py -xvs
```

**Expected:** 4 PASSed（假设 pytest 已导入）

### Step 4.5: Commit

```bash
git add tests/test_collect_chunks.py .agents/tools/collect_chunks.py
git commit -m "feat(collect): implement CollectResult and import_one_bundle"
```

---

## Task 5: collect_chunks parse_args + main() + 冲突/幂等测试

**Files:**
- Modify: `.agents/tools/collect_chunks.py`
- Modify: `tests/test_collect_chunks.py`

### Step 5.1: 编写 main() 和冲突检测的 failing test

在 `tests/test_collect_chunks.py` 末尾追加：

```python
def test_import_one_bundle_skips_conflicts_and_imports_others(tmp_path):
    manifest = {
        "format_version": 1,
        "run_id": "local-id",
        "host_id": "device-B",
        "completed_chunks": [3, 4],
        "failed_chunks": [5],
    }
    staging_files = {
        "staging/chunk_003/chunk_result.json": '{"ok": true}',
        "staging/chunk_003/issue_status_delta.json": '{"k1": {"status": "fixed"}}',
        "staging/chunk_003/file_change_delta.json": '{"k1": []}',
        "staging/chunk_003/chunk_result.md": "# Result",
        "staging/chunk_004/chunk_result.json": '{"ok": true}',
        "staging/chunk_004/issue_status_delta.json": '{}',
        "staging/chunk_004/file_change_delta.json": '{}',
        "staging/chunk_004/chunk_result.md": "# Result",
    }
    bundle = _make_bundle(tmp_path, manifest, staging_files=staging_files)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (runtime_dir / "progress.json").write_text(
        '{"run_id": "local-id", "completed_chunks": [3], "failed_chunks": [], "total_chunks": 10}'
    )
    (runtime_dir / "issue_status.json").write_text('{}')
    (runtime_dir / "file_change_index.json").write_text('{}')

    mock_import = MagicMock()
    with patch("collect_chunks.RUNTIME_DIR", runtime_dir):
        with patch("collect_chunks.RESULTS_DIR", results_dir):
            with patch("collect_chunks.LOGS_DIR", logs_dir):
                with patch("collect_chunks.import_chunk_staging_artifacts", mock_import):
                    result = collect_chunks.import_one_bundle(bundle)

    assert result.imported_chunks == [4]
    assert result.skipped_conflicts == [3]
    assert result.failed_chunks == [5]
    mock_import.assert_called_once()
    args_pos, kwargs = mock_import.call_args
    assert args_pos[1] == 4  # chunk_index is the 2nd positional arg

    updated_progress = json.loads((runtime_dir / "progress.json").read_text())
    assert 3 in updated_progress["completed_chunks"]
    assert 4 in updated_progress["completed_chunks"]
    assert 5 in updated_progress["failed_chunks"]


def test_main_collects_multiple_bundles(tmp_path, capsys):
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    (runtime_dir / "progress.json").write_text(
        '{"run_id": "local-id", "completed_chunks": [], "failed_chunks": [], "total_chunks": 2}'
    )
    (runtime_dir / "issue_status.json").write_text('{}')
    (runtime_dir / "file_change_index.json").write_text('{}')

    bundle = _make_bundle(
        tmp_path,
        {
            "format_version": 1,
            "run_id": "local-id",
            "host_id": "device-B",
            "completed_chunks": [1],
            "failed_chunks": [],
        },
        staging_files={
            "staging/chunk_001/chunk_result.json": '{"ok": true}',
            "staging/chunk_001/issue_status_delta.json": '{}',
            "staging/chunk_001/file_change_delta.json": '{}',
            "staging/chunk_001/chunk_result.md": "# Result",
        },
    )

    mock_import = MagicMock()
    with patch("collect_chunks.RUNTIME_DIR", runtime_dir):
        with patch("collect_chunks.RESULTS_DIR", results_dir):
            with patch("collect_chunks.LOGS_DIR", logs_dir):
                with patch("collect_chunks.import_chunk_staging_artifacts", mock_import):
                    rc = collect_chunks.main(["--from", str(bundle)])

    assert rc == 0
    captured = capsys.readouterr()
    assert "1/2 chunk 已完成" in captured.out or "所有 chunk 已完成" in captured.out
```

### Step 5.2: 运行测试验证失败

```bash
python3 -m pytest tests/test_collect_chunks.py::test_import_one_bundle_skips_conflicts_and_imports_others tests/test_collect_chunks.py::test_main_collects_multiple_bundles -xvs
```

**Expected:** 2 FAILs — `AttributeError: module 'collect_chunks' has no attribute 'main'`

### Step 5.3: 实现 `parse_args` 和 `main`

在 `.agents/tools/collect_chunks.py` 末尾追加：

```python

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
```

### Step 5.4: 运行测试验证通过

```bash
python3 -m pytest tests/test_collect_chunks.py -xvs
```

**Expected:** 全部 PASS（当前共 6 个测试）

### Step 5.5: Commit

```bash
git add tests/test_collect_chunks.py .agents/tools/collect_chunks.py
git commit -m "feat(collect): implement parse_args, main(), conflict and idempotency handling"
```

---

## Task 6: CLI 注册（misra-pipeline-cli.py）

**Files:**
- Modify: `cli/misra-pipeline-cli.py`
- Modify: `tests/test_misra_pipeline_cli.py`

### Step 6.1: 修改 PIPELINE_COMMANDS、cmd_help、docstring

在 `cli/misra-pipeline-cli.py` 中进行以下精确修改：

**修改 1 — 顶部 docstring**（约第 12-23 行），在 `Deprecated:` 之前插入两行：

```python
Advanced commands:
  split         Split cppcheck XML (use 'run --stage split')
  merge         Merge results (use 'run --stage merge')
  verify        Verify one chunk result
  bootstrap     Generate agent compatibility files
  validate      Provider validation test
  export        Export processed chunk results to a bundle
  collect       Import chunk results from remote workers
  config        Manage CLI configuration
```

**修改 2 — PIPELINE_COMMANDS 字典**（约第 61-68 行）：

```python
PIPELINE_COMMANDS: Dict[str, str] = {
    "split": "split_cppcheck_xml",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "doctor": "doctor",
    "validate": "validate_real",
    "export": "export_chunks",
    "collect": "collect_chunks",
}
```

**修改 3 — cmd_help 字典**（约第 211-219 行，在 `for cmd_name, module_name in PIPELINE_COMMANDS.items():` 循环内）：

```python
        cmd_help = {
            "split": "Split cppcheck XML into runtime chunks (advanced)",
            "merge": "Merge runtime results into reports (advanced)",
            "verify": "Verify one chunk result (advanced)",
            "bootstrap": "Generate agent compatibility files (advanced)",
            "doctor": "Run pipeline diagnostics",
            "validate": "Provider validation test (advanced)",
            "export": "Export processed chunk results to a bundle",
            "collect": "Import chunk results from remote workers",
        }.get(cmd_name, f"Run {module_name}")
```

### Step 6.2: 编写 CLI 解析测试

在 `tests/test_misra_pipeline_cli.py` 末尾追加：

```python
    def test_parse_args_export_subcommand(self):
        """Test parse_args for 'export' subcommand."""
        args = misra_pipeline_cli.parse_args(["export"])
        self.assertEqual(args.subcommand, "export")

    def test_parse_args_export_with_output(self):
        """Test parse_args for 'export --output path'."""
        args = misra_pipeline_cli.parse_args(["export", "--output", "/tmp/out.tar.gz"])
        self.assertEqual(args.subcommand, "export")
        # forwarded args should include --output
        self.assertIn("--output", args.args)

    def test_parse_args_collect_subcommand(self):
        """Test parse_args for 'collect' subcommand."""
        args = misra_pipeline_cli.parse_args(["collect", "--from", "/tmp/bundle.tar.gz"])
        self.assertEqual(args.subcommand, "collect")
        self.assertIn("--from", args.args)
```

### Step 6.3: 运行 CLI 测试

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py::MisraPipelineCliTests::test_parse_args_export_subcommand tests/test_misra_pipeline_cli.py::MisraPipelineCliTests::test_parse_args_export_with_output tests/test_misra_pipeline_cli.py::MisraPipelineCliTests::test_parse_args_collect_subcommand -xvs
```

**Expected:** 3 PASSed

### Step 6.4: Commit

```bash
git add cli/misra-pipeline-cli.py tests/test_misra_pipeline_cli.py
git commit -m "feat(cli): register export and collect subcommands"
```

---

## Task 7: 端到端集成测试

**Files:**
- Create: `tests/test_export_collect_integration.py`

### Step 7.1: 编写集成测试

创建 `tests/test_export_collect_integration.py`：

```python
"""End-to-end test: export -> collect roundtrip."""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / ".agents" / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import export_chunks
import collect_chunks


def test_export_then_collect_roundtrip(tmp_path):
    """Simulate worker export + coordinator collect with mocked filesystem."""
    # --- Setup worker filesystem ---
    worker_runtime = tmp_path / "worker" / "runtime"
    worker_runtime.mkdir(parents=True)
    worker_config = tmp_path / "worker" / "config"
    worker_config.mkdir(parents=True)
    worker_staging = tmp_path / "worker" / ".agents" / "staging"
    worker_staging.mkdir(parents=True)
    worker_logs = tmp_path / "worker" / "logs"
    worker_logs.mkdir()

    chunk_dir = worker_staging / "chunk_003"
    chunk_dir.mkdir()
    (chunk_dir / "chunk_result.json").write_text('{"fixed": 2}')
    (chunk_dir / "issue_status_delta.json").write_text('{"k1": {"status": "fixed"}}')
    (chunk_dir / "file_change_delta.json").write_text('{"k1": []}')
    (chunk_dir / "chunk_result.md").write_text("# Chunk 3 Result")
    (worker_logs / "chunk_003.log").write_text("agent stdout")
    (worker_runtime / "progress.json").write_text(
        json.dumps({"run_id": "20260507-001", "completed_chunks": [3], "failed_chunks": []})
    )
    (worker_config / "pipeline.json").write_text(
        json.dumps({"agent": {"staging_dir": str(tmp_path / "worker" / ".agents" / "staging")}})
    )

    # --- Worker export ---
    bundle_path = tmp_path / "export-20260507-001-worker.tar.gz"
    with patch("export_chunks.RUNTIME_DIR", worker_runtime):
        with patch("export_chunks.CONFIG_DIR", worker_config):
            with patch("export_chunks.LOGS_DIR", worker_logs):
                with patch("export_chunks.ROOT", tmp_path / "worker"):
                    with patch("export_chunks.subprocess.run") as mock_git:
                        mock_git.return_value.returncode = 0
                        mock_git.return_value.stdout = ""
                        rc = export_chunks.main(["--output", str(bundle_path), "--host-id", "worker"])
    assert rc == 0
    assert bundle_path.exists()

    # --- Setup coordinator filesystem ---
    coord_runtime = tmp_path / "coord" / "runtime"
    coord_runtime.mkdir(parents=True)
    coord_results = tmp_path / "coord" / "results"
    coord_results.mkdir(parents=True)
    coord_logs = tmp_path / "coord" / "logs"
    coord_logs.mkdir()
    (coord_runtime / "progress.json").write_text(
        json.dumps({"run_id": "20260507-001", "completed_chunks": [], "failed_chunks": [], "total_chunks": 5})
    )
    (coord_runtime / "issue_status.json").write_text('{}')
    (coord_runtime / "file_change_index.json").write_text('{}')

    mock_import = MagicMock()
    with patch("collect_chunks.RUNTIME_DIR", coord_runtime):
        with patch("collect_chunks.RESULTS_DIR", coord_results):
            with patch("collect_chunks.LOGS_DIR", coord_logs):
                with patch("collect_chunks.import_chunk_staging_artifacts", mock_import):
                    rc = collect_chunks.main(["--from", str(bundle_path)])
    assert rc == 0
    mock_import.assert_called_once()
    args_pos, kwargs = mock_import.call_args
    assert args_pos[1] == 3  # chunk_index is the 2nd positional arg

    progress = json.loads((coord_runtime / "progress.json").read_text())
    assert 3 in progress["completed_chunks"]
```

### Step 7.2: 运行集成测试

```bash
python3 -m pytest tests/test_export_collect_integration.py -xvs
```

**Expected:** 1 PASSed

### Step 7.3: Commit

```bash
git add tests/test_export_collect_integration.py
git commit -m "test(integration): add export->collect roundtrip test"
```

---

## Task 8: 全量回归验证

### Step 8.1: 运行全部新增测试

```bash
python3 -m pytest tests/test_export_chunks.py tests/test_collect_chunks.py tests/test_export_collect_integration.py -v
```

**Expected:** 全部 PASS（test_export_chunks: 8, test_collect_chunks: 6, integration: 1 = 15 total）

### Step 8.2: 运行现有 CLI 测试确保无回归

```bash
python3 -m pytest tests/test_misra_pipeline_cli.py -v
```

**Expected:** 全部 PASS（当前约 68 个）

### Step 8.3: 运行全量测试套件

```bash
python3 -m pytest tests/ -v --tb=short
```

**Expected:** 全部 PASS（无新增失败）

### Step 8.4: Commit（如有未提交的改动）

```bash
git status
# 如有未提交文件：
git add -A
git commit -m "test: verify no regressions across full test suite"
```

---

## Self-Review

### 1. Spec coverage

| Spec 章节 | 实现任务 |
|-----------|----------|
| §4.1 export — host_id 三级解析 | Task 1 Step 1.3 |
| §4.1 export — patch 降级 | Task 1 Step 1.3 |
| §4.1 export — manifest 结构 | Task 2 Step 2.3 |
| §4.1 export — tar.gz 打包 | Task 2 Step 2.3 |
| §4.1 export — completed/failed 分治 | Task 3 Step 3.3 |
| §4.2 collect — format_version 校验 | Task 4 Step 4.3 |
| §4.2 collect — run_id 校验 | Task 4 Step 4.3 |
| §4.2 collect — 冲突检测 | Task 5 Step 5.3 |
| §4.2 collect — git apply | Task 4 Step 4.3 |
| §4.2 collect — import_chunk_staging_artifacts 复用 | Task 4 Step 4.3 |
| §4.2 collect — progress 合并 | Task 4 Step 4.3 |
| §4.3 CLI 注册 | Task 6 Step 6.1 |
| §7 边界 — 幂等性 | Task 5 Step 5.1 + 5.3 |
| §7 边界 — 无 git 降级 | Task 1 Step 1.3（try_generate_patch）|
| §8 测试策略 — 全部 6 类 | 覆盖在 Task 1-7 |

**Gap check:** 无遗漏。

### 2. Placeholder scan

- 无 "TBD"、"TODO"、"implement later"
- 无 "Add appropriate error handling" 等模糊描述
- 每个测试步骤包含完整可执行代码
- 每个运行步骤包含 exact command 和 expected output

### 3. Type 一致性检查

- `resolve_host_id(args: argparse.Namespace)` — Task 1 定义，Task 3 使用 ✅
- `try_generate_patch(root: Path = ROOT)` — Task 1 定义，返回 `Tuple[Optional[str], str]` ✅
- `build_manifest(...)` — Task 2 定义，参数与设计文档一致 ✅
- `CollectResult` — Task 4 定义，字段名与设计文档一致 ✅
- `import_one_bundle(bundle_path: Path) -> CollectResult` — Task 4 定义 ✅
- `main(argv: Optional[List[str]] = None) -> int` — 两个模块一致 ✅
- CLI `cmd_help` 键名与 `PIPELINE_COMMANDS` 键名一致 ✅

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-07-distributed-chunk-export-collect.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
