





Now I have the complete picture. Let me write the design spec.

Key insight: each chunk's **staging dir** (`.agents/staging/chunk_NNN/`) contains the per-chunk deltas and is preserved across chunks. We can leverage [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) directly on the coordinator, avoiding manual JSON merging.

---

# 分布式多设备工作流设计方案

## 架构总览

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

## 涉及文件

新增 2 个工具模块 + CLI 注册，不改动现有模块逻辑：

| 文件 | 改动类型 |
|------|----------|
| `.agents/tools/export_chunks.py` | **新建** |
| `.agents/tools/collect_chunks.py` | **新建** |
| [cli/misra-pipeline-cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:0:0-0:0) | 追加 `export`/`collect` 子命令 |
| [.agents/tools/oneshot.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:0:0-0:0) | 不改 |

## 设计细节

### 1. `export` 命令

运行在 worker 设备上，在 agent 阶段完成后执行。打包本设备处理过的 chunk 的产出物。

```bash
misra-pipeline export [--output <path>]
```

**打包内容**（一个 `.tar.gz`）：

```
export-<run_id>-<hostname>.tar.gz
├── manifest.json            # 元数据
├── patches/
│   └── source.patch         # git diff HEAD（源码修改）
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
  "hostname": "device-B",
  "exported_at": "2026-05-07T19:00:00+08:00",
  "completed_chunks": [3, 4],
  "failed_chunks": [],
  "chunk_ids_requested": [3, 4],
  "source_patch_file": "patches/source.patch",
  "staging_dirs": ["staging/chunk_003", "staging/chunk_004"]
}
```

**核心逻辑**（`export_chunks.py`）：

```python
def main(argv=None):
    args = parse_args(argv)
    progress = load_json(RUNTIME_DIR / "progress.json", {})
    run_id = progress.get("run_id", "unknown")
    completed = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))

    # 确定要导出的 chunk
    export_ids = sorted(completed | failed)
    if not export_ids:
        print("[export] 无已处理 chunk，无需导出。")
        return 0

    # 校验 staging artifacts 存在性
    config = load_json(CONFIG_DIR / "pipeline.json", {})
    staging_base = resolve_agent_staging_dir(config)
    missing = []
    for idx in export_ids:
        chunk_staging = staging_base / f"chunk_{idx:03d}"
        if idx in completed and not (chunk_staging / "chunk_result.json").exists():
            missing.append(idx)
    if missing:
        print(f"[export] 警告: chunk {missing} 的 staging 产出物缺失，将跳过")
        export_ids = [i for i in export_ids if i not in missing]

    # 生成 source patch
    patch_content = subprocess.run(
        ["git", "diff", "HEAD"], capture_output=True, text=True, cwd=str(ROOT)
    ).stdout

    # 构建 manifest
    manifest = { ... }

    # 打包 tar.gz
    output_path = args.output or f"export-{run_id}-{hostname}.tar.gz"
    with tarfile.open(output_path, "w:gz") as tar:
        # add manifest.json, patches/source.patch, staging/chunk_NNN/*, logs/*
        ...

    print(f"[export] 已导出 {len(export_ids)} 个 chunk → {output_path}")
    return 0
```

### 2. `collect` 命令

运行在 coordinator（设备 A）上，在 merge 之前执行。导入一个或多个 worker 的 export bundle。

```bash
misra-pipeline collect --from device-B.tar.gz [--from device-C.tar.gz ...]
```

**核心逻辑**（`collect_chunks.py`）：

```python
def import_one_bundle(bundle_path: Path) -> CollectResult:
    """导入单个 export bundle，返回处理结果。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 1. 解包
        extract(bundle_path, tmp)
        manifest = load_json(Path(tmp) / "manifest.json", {})

        # 2. 校验 run_id 一致性
        local_progress = load_json(RUNTIME_DIR / "progress.json", {})
        if manifest["run_id"] != local_progress.get("run_id"):
            raise SystemExit(f"run_id 不匹配: 本地={local_progress.get('run_id')}, 远程={manifest['run_id']}")

        # 3. 检查 chunk 冲突（本地已 completed 的 chunk 不应被覆盖）
        local_completed = set(local_progress.get("completed_chunks", []))
        remote_completed = set(manifest.get("completed_chunks", []))
        conflicts = local_completed & remote_completed
        if conflicts:
            print(f"[collect] 警告: chunk {sorted(conflicts)} 本地已完成，跳过")
            remote_completed -= conflicts

        # 4. 应用 source patch
        patch_file = Path(tmp) / manifest.get("source_patch_file", "patches/source.patch")
        if patch_file.exists() and patch_file.stat().st_size > 0:
            result = subprocess.run(
                ["git", "apply", "--3way", str(patch_file)],
                cwd=str(ROOT), capture_output=True, text=True
            )
            if result.returncode != 0:
                print(f"[collect] git apply 失败，请手动处理: {result.stderr}")
                # 不中止，继续导入元数据

        # 5. 逐 chunk 重新导入 staging artifacts
        for idx in sorted(remote_completed):
            src_staging = Path(tmp) / f"staging/chunk_{idx:03d}"
            if not src_staging.exists():
                print(f"[collect] 警告: chunk {idx} staging 不存在，跳过")
                continue
            # 复用现有的 import_chunk_staging_artifacts
            import_chunk_staging_artifacts(
                src_staging, idx,
                runtime_dir=RUNTIME_DIR,
                results_dir=RESULTS_DIR,
            )

        # 6. 更新 progress.json
        local_progress["completed_chunks"] = sorted(
            set(local_progress.get("completed_chunks", [])) | remote_completed
        )
        remote_failed = set(manifest.get("failed_chunks", []))
        # failed 中移除已在任何设备上 completed 的
        all_completed = set(local_progress["completed_chunks"])
        local_progress["failed_chunks"] = sorted(
            (set(local_progress.get("failed_chunks", [])) | remote_failed) - all_completed
        )
        save_json(RUNTIME_DIR / "progress.json", local_progress)

        # 7. 复制 logs（可选）
        for log_file in (Path(tmp) / "logs").glob("chunk_*.log"):
            shutil.copy2(log_file, LOGS_DIR / log_file.name)

    return CollectResult(
        hostname=manifest.get("hostname", "unknown"),
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
        print(f"[collect] {r.hostname}: 导入 {len(r.imported_chunks)} chunk, "
              f"跳过 {len(r.skipped_conflicts)} 冲突, "
              f"失败 {len(r.failed_chunks)}")

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

### 3. CLI 注册

在 [cli/misra-pipeline-cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:0:0-0:0) 中：

```python
# PIPELINE_COMMANDS 增加
PIPELINE_COMMANDS: Dict[str, str] = {
    ...
    "export": "export_chunks",
    "collect": "collect_chunks",
}

# collect 需要自定义参数
collect_parser = subparsers.add_parser("collect", help="Import chunk results from remote workers")
collect_parser.add_argument("--from", dest="bundles", action="append", required=True,
                            help="Path to export bundle .tar.gz (repeatable)")
```

## 关键设计决策

| 决策 | 理由 |
|------|------|
| **传递 staging delta 而非累积后的全局文件** | 利用现有 [import_chunk_staging_artifacts](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:939:0-982:5) 逻辑，无需重写 merge；delta 是幂等的（按 issue_key 分区，chunk 间不交叉） |
| **source patch 用 `git diff HEAD`** | 所有设备 split 后有相同 HEAD；`git apply --3way` 支持冲突解决 |
| **run_id 一致性校验** | 防止误导入不同 split 轮次的产物 |
| **chunk 冲突检测而非覆盖** | 避免 coordinator 自己跑的 chunk 被远程结果覆盖 |
| **collect 可多次调用** | 每个 bundle 独立导入，支持设备陆续回传 |

## 完整操作流程

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

## 边界行为

- **设备 A 未跑任何 chunk 也可 collect**：`issue_status.json` / `file_change_index.json` 保持 split 后的初始状态，import delta 正常工作
- **同一 chunk 在多个 bundle 中出现**：第一个导入成功后标记 completed，后续 bundle 中同一 chunk 被跳过（冲突检测）
- **bundle 中有 failed chunk**：仅更新 `failed_chunks` 列表，不导入 staging（staging 不存在或不完整）
- **git apply 冲突**：`--3way` 产生 conflict markers，打印警告但不中止 collect，元数据照常导入；用户手动 resolve 后再 merge
- **多次 collect**：幂等，重复导入同一 bundle 不会破坏状态（已 completed 的 chunk 被跳过）

## 测试策略

1. **`export_chunks` 单元测试**：mock staging 目录，验证 tar.gz 内容和 manifest 正确性
2. **`collect_chunks` 单元测试**：构造 mock bundle，验证 import 后 progress/issue_status/file_change_index 正确
3. **冲突测试**：本地已完成 chunk 3，导入包含 chunk 3 的 bundle，验证跳过并警告
4. **run_id 不匹配测试**：验证 SystemExit
5. **端到端测试**：split → export(mock) → collect → merge 全流程

## 兼容性

- 不修改任何现有模块的行为
- `export` / `collect` 是独立的新命令，不影响单机 `run` 全流模式
- `manifest.json` 带 `format_version` 字段，便于后续版本升级
