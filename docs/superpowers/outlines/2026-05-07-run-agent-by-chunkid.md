

# 最小修改方案：`--chunk-id` 支持

目标：`misra-pipeline run --stage agent --chunk-id <ID|RANGE>` 仅运行指定 chunk；未知 ID 警告；全部处理完后提示进入 merge。

涉及 3 个文件，单点改动：

## 1. `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py` —— 核心改动

### 1a. 新增参数（在 [parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:137:0-275:17) 内 `--include-failed` 之后）

```python
parser.add_argument(
    "--chunk-id",
    action="append",
    default=[],
    help=(
        "Only run specific chunk(s). Accepts single id (e.g. 5) or range "
        "(e.g. 3-7). Can be specified multiple times. Unknown ids are warned "
        "and skipped."
    ),
)
```

### 1b. 新增解析与校验辅助函数（放在 [normalize_rule_set](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:154:0-155:79) 旁边）

```python
def parse_chunk_id_specs(specs: Iterable[str], total: int) -> tuple[List[int], List[str]]:
    """Parse --chunk-id specs into (sorted unique valid ids, warnings)."""
    valid: Set[int] = set()
    warnings: List[str] = []
    for raw in specs:
        token = (raw or "").strip()
        if not token:
            continue
        if "-" in token:
            lo_s, hi_s = token.split("-", 1)
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                warnings.append(f"忽略无效 chunk-id 范围: '{token}'")
                continue
            if lo > hi:
                lo, hi = hi, lo
            for i in range(lo, hi + 1):
                if 1 <= i <= total:
                    valid.add(i)
                else:
                    warnings.append(f"chunk-id {i} 超出范围 (1..{total})，已跳过")
        else:
            try:
                i = int(token)
            except ValueError:
                warnings.append(f"忽略无效 chunk-id: '{token}'")
                continue
            if 1 <= i <= total:
                valid.add(i)
            else:
                warnings.append(f"chunk-id {i} 超出范围 (1..{total})，已跳过")
    return sorted(valid), warnings
```

### 1c. [next_chunk](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:190:0-203:15) 增加 `requested_ids` 过滤

```python
def next_chunk(progress: dict, selected_rules: Set[str], misra_only: bool,
               include_failed: bool, requested_ids: Optional[List[int]] = None) -> Optional[int]:
    done = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))
    total = int(progress.get("total_chunks", 0))

    candidates = requested_ids if requested_ids else range(1, total + 1)
    for idx in candidates:
        if idx in done:
            continue
        if not include_failed and idx in failed:
            continue
        if not chunk_matches_filters(idx, selected_rules, misra_only):
            continue
        return idx
    return None
```

### 1d. [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:225:0-429:42) 内：在加载 `progress` 后注入解析与告警，并把请求列表传入循环

```python
total_chunks_for_parse = int(progress.get("total_chunks", 0))
requested_ids, chunk_id_warnings = parse_chunk_id_specs(
    args.chunk_id, total_chunks_for_parse
)
for w in chunk_id_warnings:
    print(f"[run] 警告: {w}")
if args.chunk_id and not requested_ids:
    print("[run] 未提供任何有效 chunk-id，未执行 agent 阶段。"
          "如已完成所有 chunk，可继续：misra-pipeline run --stage merge")
    return 0
```

把循环里的调用改为：

```python
idx = next_chunk(progress, selected_rules, args.misra_only,
                 args.include_failed, requested_ids)
```

并在 `idx is None` 分支中，根据 `requested_ids` 区分提示：

```python
if idx is None:
    progress["status"] = "done" if not requested_ids else progress.get("status", "running")
    save_json(progress_path, progress)
    if requested_ids:
        print(f"[run] 指定的 chunk-id {requested_ids} 已全部处理完毕（或被过滤跳过）。")
        print("[run] 如需汇总报告，请继续：misra-pipeline run --stage merge")
    else:
        print("No more eligible chunks to process.")
    append_pipeline_event(...)  # 保留原事件
    return 0
```

并把 `last_run_filters` 加上 `"chunk_ids": requested_ids` 以便审计。

## 2. `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py` —— 转发参数

在 `build_run_args` 末尾追加：

```python
for cid in getattr(args, "chunk_id", []) or []:
    stage_args.extend(["--chunk-id", cid])
```

## 3. `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py` —— 顶层 CLI 暴露

在 `run` 子命令定义里（`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py:241-260` 区段）加一行：

```python
run_parser.add_argument("--chunk-id", action="append", default=[],
                        help="Run only this chunk id or range (e.g. 5 or 3-7). Repeatable.")
```

## 行为示例

- `misra-pipeline run --stage agent --chunk-id 5` → 仅跑 chunk 5。
- `misra-pipeline run --stage agent --chunk-id 3-7 --chunk-id 12` → 跑 3,4,5,6,7,12。
- `--chunk-id 999`（不存在）→ 输出 `警告: chunk-id 999 超出范围 (1..N)，已跳过`，无有效 ID 时直接退出并提示进入 merge。
- 全部处理完 → 提示 `请继续：misra-pipeline run --stage merge`。

## 兼容性

- 参数默认 `[]`，未传时行为完全等价于现有逻辑。
- 不改 `progress.json` schema（新增 `last_run_filters.chunk_ids` 是可选字段）。
- `--chunk-id` 可与 `--rule-id` / `--misra-only` / `--include-failed` 叠加：仍走原过滤函数，只是候选集合被缩小到指定 ID。

