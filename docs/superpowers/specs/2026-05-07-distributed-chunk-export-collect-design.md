# 分布式多设备 Chunk 导出/收集设计文档

**日期**: 2026-05-07  
**主题**: `misra-pipeline export` / `collect` 子命令  
**状态**: 待审查  
**作者**: AI Agent (基于用户 outline 与澄清反馈)  

---

## 1. 背景与目标

当前 `misra-pipeline` 的 `run --stage agent` 支持 `--chunk-id N-M` 在单机上处理指定 chunk。为了支持**多设备并行处理**（例如多台工作站、笔记本、CI runner），需要一套轻量级的导出/收集机制：

- **Worker 设备**（设备 B/C/D/E）在处理完分配的 chunk 后，将产出物打包成一个 `.tar.gz`。
- **Coordinator 设备**（设备 A）回收所有 worker 的 bundle，将 chunk 的 staging delta 导入本地 runtime，最终执行 `run --stage merge` 生成报告。

本设计**不修改任何现有模块的行为**，仅新增两个 CLI 命令和对应的工具模块。

---

## 2. 架构总览

```
设备 A (coordinator)          设备 B/C/D/E (worker)
────────────────────          ──────────────────────
run --stage split
        │
        ├─── rsync/git ──────► 拿到完整项目副本
        │
        │                     run --stage agent --chunk-id N-M
        │                     misra-pipeline export
        │                            │
        ◄─── 回传 bundle ────────────┘
        │
misra-pipeline collect --from *.tar.gz
        │
run --stage merge
```

**核心设计原则**:
- 传递 **staging delta**（`issue_status_delta.json` / `file_change_delta.json`）而非累积后的全局文件，复用现有 `import_chunk_staging_artifacts` 逻辑。
- `export` / `collect` 是独立命令，不影响单机 `run` 全流模式。
- Source patch 是"有就用"的便利功能，不是必选路径；pipeline 只负责自身状态同步，源码同步是用户/git 的责任。

---

## 3. 涉及文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `.agents/tools/export_chunks.py` | **新建** | Worker 端打包逻辑 |
| `.agents/tools/collect_chunks.py` | **新建** | Coordinator 端导入逻辑 |
| `cli/misra-pipeline-cli.py` | 追加 | 注册 `export` / `collect` 子命令 |

---

## 4. 模块设计

### 4.1 `export` 命令（Worker 端）

```bash
misra-pipeline export [--output <path>] [--host-id <name>]
```

**打包内容**（一个 `.tar.gz`）：

```
export-<run_id>-<host_id>.tar.gz
├── manifest.json            # 元数据
├── patches/
│   └── source.patch         # git diff HEAD（可选，可能为空或不存在）
├── staging/
│   ├── chunk_003/           # 原样复制 .agents/staging/chunk_NNN/
│   │   ├── issue_status_delta.json
│   │   ├── file_change_delta.json
│   │   ├── chunk_result.json
│   │   └── chunk_result.md
│   └── chunk_004/
│       └── ...
└── logs/                    # 可选，便于排查
    ├── chunk_003.log
    └── chunk_004.log
```

**`manifest.json` 结构**：

```json
{
  "format_version": 1,
  "run_id": "20260507-001",
  "host_id": "device-B",
  "exported_at": "2026-05-07T19:00:00+08:00",
  "completed_chunks": [3, 4],
  "failed_chunks": [],
  "chunk_ids_requested": [3, 4],
  "has_source_patch": true,
  "source_patch_file": "patches/source.patch",
  "staging_dirs": ["staging/chunk_003", "staging/chunk_004"]
}
```

**Host ID 解析策略**（三级优先级）：
1. `--host-id` CLI flag
2. `PIPELINE_HOST_ID` 环境变量
3. `socket.gethostname()`

```python
def resolve_host_id(args) -> str:
    return (
        getattr(args, "host_id", None)
        or os.environ.get("PIPELINE_HOST_ID", "").strip()
        or socket.gethostname()
    )
```

**Source Patch 生成策略**（尝试 + 降级）：

```python
def try_generate_patch() -> Tuple[Optional[str], str]:
    """Returns (patch_content_or_None, message)."""
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=str(ROOT), timeout=30
        )
        if r.returncode != 0:
            return None, "git diff 失败，跳过 source patch"
        if not r.stdout.strip():
            return None, "无源码修改"
        return r.stdout, f"已生成 source patch ({len(r.stdout)} bytes)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "git 不可用或超时，跳过 source patch（请自行同步源码修改）"
```

| 场景 | export 行为 | manifest.has_source_patch |
|------|-------------|---------------------------|
| 有 git，有改动 | 生成 `source.patch`，设为 `true` | `true` |
| 有 git，无改动 | 不打包 patch | `false` |
| 无 git / git 失败 | 不打包 patch，打印降级提示 | `false` |

**核心逻辑**（`export_chunks.py`）：

```python
def main(argv=None):
    args = parse_args(argv)
    progress = load_json(RUNTIME_DIR / "progress.json", {})
    run_id = progress.get("run_id", "unknown")
    completed = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))

    # 校验 staging artifacts 存在性，并区分 completed / failed
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
        # failed chunk 的 staging 缺失是预期行为，不告警

    if missing_staging:
        print(f"[export] 警告: completed chunk {missing_staging} 的 staging 产出物缺失，将跳过")

    # 只有 completed 的 staging 会被 collect 导入；failed 仅用于日志打包
    staging_ids = sorted(completed_export + failed_export)
    all_ids = sorted(completed | failed)
    if not all_ids:
        print("[export] 无已处理 chunk，无需导出。")
        return 0

    # 生成 source patch（尝试 + 降级）
    patch_content, patch_msg = try_generate_patch()
    print(f"[export] {patch_msg}")

    # 构建 manifest
    host_id = resolve_host_id(args)
    manifest = {
        "format_version": 1,
        "run_id": run_id,
        "host_id": host_id,
        "exported_at": now_iso(),
        "completed_chunks": completed_export,
        "failed_chunks": sorted(failed),
        "chunk_ids_requested": all_ids,
        "has_source_patch": patch_content is not None,
        "source_patch_file": "patches/source.patch" if patch_content else None,
        "staging_dirs": [f"staging/chunk_{idx:03d}" for idx in completed_export],
    }

    # 打包 tar.gz
    output_path = args.output or f"export-{run_id}-{host_id}.tar.gz"
    with tarfile.open(output_path, "w:gz") as tar:
        _add_json(tar, manifest, "manifest.json")
        if patch_content:
            _add_text(tar, patch_content, "patches/source.patch")
        # staging 只打包 completed（collect 侧只会导入 completed_chunks 的 staging）
        for idx in completed_export:
            src = staging_base / f"chunk_{idx:03d}"
            for f in src.iterdir():
                tar.add(f, arcname=f"staging/chunk_{idx:03d}/{f.name}")
        # logs 打包所有已处理 chunk（completed + failed，均用于排查）
        for idx in all_ids:
            log = LOGS_DIR / f"chunk_{idx:03d}.log"
            if log.exists():
                tar.add(log, arcname=f"logs/chunk_{idx:03d}.log")

    print(f"[export] 已导出 {len(completed_export)} completed + {len(failed_export)} failed chunk → {output_path}")
    return 0
```

---

### 4.2 `collect` 命令（Coordinator 端）

```bash
misra-pipeline collect --from device-B.tar.gz [--from device-C.tar.gz ...]
```

**核心逻辑**（`collect_chunks.py`）：

```python
@dataclass
class CollectResult:
    host_id: str
    imported_chunks: List[int]
    skipped_conflicts: List[int]
    failed_chunks: List[int]


def import_one_bundle(bundle_path: Path) -> CollectResult:
    """导入单个 export bundle，返回处理结果。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 1. 解包
        extract(bundle_path, tmp)
        manifest = load_json(Path(tmp) / "manifest.json", {})

        # 2. 校验 manifest 格式版本
        if manifest.get("format_version", 0) != 1:
            raise SystemExit(
                f"不支持的 bundle 格式版本: {manifest.get('format_version')}"
            )

        # 3. 校验 run_id 一致性
        local_progress = load_json(RUNTIME_DIR / "progress.json", {})
        if manifest["run_id"] != local_progress.get("run_id"):
            raise SystemExit(
                f"run_id 不匹配: 本地={local_progress.get('run_id')}, 远程={manifest['run_id']}"
            )

        # 4. 检查 chunk 冲突（本地已 completed 的 chunk 不应被覆盖）
        local_completed = set(local_progress.get("completed_chunks", []))
        remote_completed = set(manifest.get("completed_chunks", []))
        conflicts = local_completed & remote_completed
        if conflicts:
            print(f"[collect] 警告: chunk {sorted(conflicts)} 本地已完成，跳过")
            remote_completed -= conflicts

        # 5. 应用 source patch（如果存在且本地有 git）
        if manifest.get("has_source_patch"):
            patch_file = Path(tmp) / manifest.get("source_patch_file", "patches/source.patch")
            if patch_file.exists() and patch_file.stat().st_size > 0:
                result = subprocess.run(
                    ["git", "apply", "--3way", str(patch_file)],
                    cwd=str(ROOT), capture_output=True, text=True
                )
                if result.returncode != 0:
                    print(f"[collect] git apply 失败，请手动处理: {result.stderr}")
                    # 不中止，继续导入元数据

        # 6. 逐 chunk 重新导入 staging artifacts
        for idx in sorted(remote_completed):
            src_staging = Path(tmp) / f"staging/chunk_{idx:03d}"
            if not src_staging.exists():
                print(f"[collect] 警告: chunk {idx} staging 不存在，跳过")
                continue
            import_chunk_staging_artifacts(
                src_staging, idx,
                runtime_dir=RUNTIME_DIR,
                results_dir=RESULTS_DIR,
            )

        # 7. 更新 progress.json
        local_progress["completed_chunks"] = sorted(
            set(local_progress.get("completed_chunks", [])) | remote_completed
        )
        remote_failed = set(manifest.get("failed_chunks", []))
        all_completed = set(local_progress["completed_chunks"])
        local_progress["failed_chunks"] = sorted(
            (set(local_progress.get("failed_chunks", [])) | remote_failed) - all_completed
        )
        save_json(RUNTIME_DIR / "progress.json", local_progress)

        # 8. 复制 logs（可选）
        for log_file in (Path(tmp) / "logs").glob("chunk_*.log"):
            shutil.copy2(log_file, LOGS_DIR / log_file.name)

    return CollectResult(
        host_id=manifest.get("host_id", "unknown"),
        imported_chunks=sorted(remote_completed),
        skipped_conflicts=sorted(conflicts),
        failed_chunks=sorted(remote_failed),
    )


def main(argv=None):
    args = parse_args(argv)  # --from (repeatable)
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

    # 最终汇总
    progress = load_json(RUNTIME_DIR / "progress.json", {})
    total = progress.get("total_chunks", 0)
    done = len(progress.get("completed_chunks", []))
    print(f"[collect] 汇总: {done}/{total} chunk 已完成")
    if done >= total:
        print("[collect] 所有 chunk 已完成，可继续: misra-pipeline run --stage merge")
    else:
        remaining = total - done
        print(f"[collect] 还剩 {remaining} chunk 未完成")
    return 0
```

---

### 4.3 CLI 注册

在 `cli/misra-pipeline-cli.py` 中：

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

`collect` 需要自定义参数：

```python
collect_parser = subparsers.add_parser("collect", help="Import chunk results from remote workers")
collect_parser.add_argument(
    "--from", dest="bundles", action="append", required=True,
    help="Path to export bundle .tar.gz (repeatable)"
)
```

`export` 需要自定义参数：

```python
export_parser = subparsers.add_parser("export", help="Export processed chunk results to a bundle")
export_parser.add_argument(
    "--output", "-o", dest="output", default=None,
    help="Output bundle path (default: export-<run_id>-<host_id>.tar.gz)"
)
export_parser.add_argument(
    "--host-id", dest="host_id", default=None,
    help="Override host identifier (default: env PIPELINE_HOST_ID, then socket.gethostname)"
)
```

---

## 5. 关键设计决策

| 决策 | 理由 |
|------|------|
| **传递 staging delta 而非累积后的全局文件** | 利用现有 `import_chunk_staging_artifacts` 逻辑，无需重写 merge；delta 是幂等的（按 issue_key 分区，chunk 间不交叉） |
| **source patch 用 `git diff HEAD`** | 所有设备 split 后有相同 HEAD；`git apply --3way` 支持冲突解决 |
| **source patch 是可选便利功能** | Pipeline 只负责自身状态同步，源码同步是用户/git 的责任；无 git 时降级跳过，不增加硬依赖 |
| **run_id 一致性校验** | 防止误导入不同 split 轮次的产物 |
| **chunk 冲突检测而非覆盖** | 避免 coordinator 自己跑的 chunk 被远程结果覆盖 |
| **collect 可多次调用** | 每个 bundle 独立导入，支持设备陆续回传 |
| **Host ID 三级解析** | `--host-id` > `PIPELINE_HOST_ID` > `socket.gethostname()`，覆盖容器/CI 随机 hostname 问题 |

---

## 6. 完整操作流程

```bash
# ── 设备 A ──────────────────────────────────
misra-pipeline run --stage split
# 同步项目到所有设备（git push 或 rsync）

# ── 设备 A（自己也跑 2 个 chunk）────────────
misra-pipeline run --stage agent --chunk-id 1-2

# ── 设备 B ──────────────────────────────────
misra-pipeline run --stage agent --chunk-id 3-4
misra-pipeline export                          # → export-20260507-001-deviceB.tar.gz

# ── 设备 C/D/E 类似 ─────────────────────────
misra-pipeline run --stage agent --chunk-id 5-6
misra-pipeline export
# ...

# ── 设备 A（回收）──────────────────────────
misra-pipeline collect \
  --from export-*-deviceB.tar.gz \
  --from export-*-deviceC.tar.gz \
  --from export-*-deviceD.tar.gz \
  --from export-*-deviceE.tar.gz

# ── 设备 A（最终 merge）────────────────────
misra-pipeline run --stage merge
```

---

## 7. 边界行为

- **设备 A 未跑任何 chunk 也可 collect**：`issue_status.json` / `file_change_index.json` 保持 split 后的初始状态，import delta 正常工作。
- **同一 chunk 在多个 bundle 中出现**：第一个导入成功后标记 completed，后续 bundle 中同一 chunk 被跳过（冲突检测）。
- **bundle 中有 failed chunk**：仅更新 `failed_chunks` 列表，不导入 staging（staging 不存在或不完整）。
- **git apply 冲突**：`--3way` 产生 conflict markers，打印警告但不中止 collect，元数据照常导入；用户手动 resolve 后再 merge。
- **多次 collect**：幂等，重复导入同一 bundle 不会破坏状态。幂等性由 §4.2 Step 4 冲突检测保证：已 completed 的 chunk 被提前跳过，不会重入 `import_chunk_staging_artifacts`。
- **无 git 的 worker**：export 跳过 patch，打印降级提示；collect 跳过 apply；merge 只读 runtime JSON 不受影响。
- **manifest format_version 不匹配**：未来版本若升级格式，collect 侧可据此拒绝或走兼容路径（当前 version=1）。

---

## 8. 测试策略

1. **`export_chunks` 单元测试**：mock staging 目录，验证 tar.gz 内容和 manifest 正确性；验证 host_id 三级解析。
2. **`collect_chunks` 单元测试**：构造 mock bundle，验证 import 后 progress/issue_status/file_change_index 正确。
3. **冲突测试**：本地已完成 chunk 3，导入包含 chunk 3 的 bundle，验证跳过并警告。
4. **run_id 不匹配测试**：验证 SystemExit。
5. **patch 降级测试**：无 git 环境下 export，验证 `has_source_patch=false` 且流程不中断。
6. **端到端测试**：split → export(mock) → collect → merge 全流程。

---

## 9. 兼容性

- 不修改任何现有模块的行为。
- `export` / `collect` 是独立的新命令，不影响单机 `run` 全流模式。
- `manifest.json` 带 `format_version` 字段，便于后续版本升级。
- 新增模块仅依赖 `common.py` 中的公开工具函数（`load_json`, `save_json`, `resolve_agent_staging_dir`, `import_chunk_staging_artifacts`, `RUNTIME_DIR`, `RESULTS_DIR`, `LOGS_DIR`, `CONFIG_DIR`, `ROOT`）。

---

## 10. 风险与注意事项

- **Source patch 冲突**：`git apply --3way` 可能产生冲突标记，用户需在 merge 前手动 resolve。collect 会打印明确警告。
- **Staging 目录配置不一致**：若 worker 与 coordinator 的 `agent.staging_dir` 配置不同，collect 的 `import_chunk_staging_artifacts` 会按 coordinator 配置写入，这是预期行为（runtime 和 results 路径由 coordinator 决定）。
- **大 patch 文件**：若 worker 修改了大量文件，patch 可能很大；tar.gz 压缩通常可缓解，但极端情况下可能影响传输效率。

---

## 11. 附录：Host ID 解析伪代码

```python
import os
import socket

def resolve_host_id(args) -> str:
    """
    三级优先级解析 host identifier。
    """
    return (
        getattr(args, "host_id", None)
        or os.environ.get("PIPELINE_HOST_ID", "").strip()
        or socket.gethostname()
    )
```

---

## 12. 附录：Patch 降级伪代码

```python
import subprocess
from typing import Optional, Tuple

def try_generate_patch(root: Path) -> Tuple[Optional[str], str]:
    """
    尝试生成 git diff patch。失败则降级返回 None 和提示信息。
    """
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, cwd=str(root), timeout=30
        )
        if r.returncode != 0:
            return None, "git diff 失败，跳过 source patch"
        if not r.stdout.strip():
            return None, "无源码修改"
        return r.stdout, f"已生成 source patch ({len(r.stdout)} bytes)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "git 不可用或超时，跳过 source patch（请自行同步源码修改）"
```
