# `--chunk-id` 参数设计规格

## 目标

为 `misra-pipeline run --stage agent` 添加 `--chunk-id` 参数，允许用户仅运行指定的 chunk，支持单个 ID 和范围语法，未知 ID 发出警告并跳过，全部处理完后提示进入 merge 阶段。

## 背景

当前 pipeline 的 `run --stage agent` 会按顺序处理所有未完成 chunk。在调试或重跑特定 chunk 时，需要一种方式仅运行指定 chunk 而非全量，以节省时间和资源。现有参数 `--rule-id` 和 `--misra-only` 能按规则过滤，但无法按 chunk 编号定位。

## 改动范围

涉及 3 个文件，均为单点追加式改动，不重构现有逻辑：

1. `.agents/tools/run_fix_pipeline.py` — 核心解析与过滤逻辑
2. `.agents/tools/oneshot.py` — 参数转发
3. `cli/misra-pipeline-cli.py` — 顶层 CLI 参数定义与转发

## 设计细节

### 1. 参数语法

`--chunk-id <ID|RANGE>`，可重复指定：

- 单个 ID：`--chunk-id 5`
- 范围：`--chunk-id 3-7`（包含 3、4、5、6、7）
- 混合：`--chunk-id 3-7 --chunk-id 12`（处理 chunk 3、4、5、6、7、12）
- 范围自动处理反序：`--chunk-id 7-3` 等价于 `--chunk-id 3-7`
- argparse 使用 `action="append"`，默认值为 `[]`

### 2. 解析与校验：`parse_chunk_id_specs`

新增辅助函数 `parse_chunk_id_specs(specs: Iterable[str], total: int) -> Tuple[List[int], List[str]]`：

- 输入：`--chunk-id` 的原始字符串列表和 `progress.json` 中的 `total_chunks`
- 输出：`(sorted_valid_ids: List[int], warnings: List[str])`
- 逻辑：
  - 遍历每个 spec，区分单个 ID 和范围（含 `-`）
  - 无效整数格式 → 警告并跳过
  - 超出 `[1, total]` 范围 → 警告并跳过
  - 反序范围自动纠正（`7-3` → `3-7`）
  - 自动去重并排序
- 放置位置：`run_fix_pipeline.py` 中 `normalize_rule_set` 旁边

### 3. `next_chunk` 函数修改

签名新增 `requested_ids: Optional[List[int]] = None` 参数：

- `requested_ids` 非空时，仅遍历这些 ID（而非 `range(1, total+1)`）
- `requested_ids` 为 `None` 或空列表时，行为与当前完全一致
- 其余过滤逻辑（done、failed、rule/misra）不变

### 4. `main()` 函数集成

在 `progress` 加载后、主循环前：

1. 调用 `parse_chunk_id_specs(args.chunk_id, total_chunks_for_parse)` 得到 `requested_ids` 和 `chunk_id_warnings`
2. 逐条打印警告：`print(f"[run] 警告: {w}")`
3. 若 `args.chunk_id` 非空但 `requested_ids` 为空 → 打印提示并 `return 0`（不进入 agent 阶段）
4. 将 `requested_ids` 传入 `next_chunk()` 调用
5. `idx is None` 分支：
   - 无 `requested_ids`：保持原行为（`status` 设为 `"done"`）
   - 有 `requested_ids`：`status` 设为 `"partial"`（复用现有 `--max-chunks` 截断时的语义），打印指定 chunk 已处理完毕提示
6. `last_run_filters` 新增 `"chunk_ids": requested_ids or None` 字段（可选字段，不改变 schema）
7. `run_started` 事件的 `data.filters` 也带上 `"chunk_ids"` 字段

### 5. `oneshot.py` 参数转发

- `parse_args`：新增 `--chunk-id` 参数（`action="append"`，默认 `[]`）
- `build_run_args`：末尾追加转发逻辑 `for cid in getattr(args, "chunk_id", []) or []: stage_args.extend(["--chunk-id", cid])`

### 6. `misra-pipeline-cli.py` 参数定义与转发

- `run_parser` 新增 `--chunk-id` 参数定义
- `cmd_run` 中 `--stage agent` 分支：追加 `for cid in args.chunk_id: stage_args.extend(["--chunk-id", cid])`
- `cmd_run` 中 oneshot 全流模式：追加 `for cid in args.chunk_id: oneshot_argv.extend(["--chunk-id", cid])`

## 边界行为

### `--chunk-id` 与 `--max-chunks` 的交互

`--max-chunks` 在 `--chunk-id` 确定的候选集合上独立生效：先按 `--chunk-id` 缩小候选范围，再在该范围内按 `--max-chunks` 限制处理数量。例如 `--chunk-id 3-10 --max-chunks 3` 会处理 chunk 3、4、5（前 3 个候选），然后停下并设 `status` 为 `"partial"`。

### `--chunk-id` 与 `--include-failed` 的交互

当用户显式指定 `--chunk-id N` 而 chunk N 在 `failed_chunks` 中时：
- 默认行为：chunk N 被跳过（与当前过滤逻辑一致）
- 新增提示：输出 `[run] chunk N 在 failed_chunks 中，使用 --include-failed 可重跑`
- 加 `--include-failed`：正常重跑该 chunk

### `--chunk-id` 空候选集时的处理

**`--stage agent` 模式**：若 `args.chunk_id` 非空但解析后 `requested_ids` 为空，打印警告并 `return 0`，提示可继续到 merge。

**oneshot 全流模式**：若 `args.chunk_id` 非空但解析后 `requested_ids` 为空，在 agent 阶段打印警告后 `return 0`（不继续到 merge），避免合并空结果。这意味着上层 oneshot 会看到 agent 阶段的非零/零退出码并决定是否继续。具体地：`run_fix_pipeline.main` 在空候选时 `return 0`，但会打印提示 `未提供任何有效 chunk-id`；oneshot 的 `execute_stage("run", ...)` 收到 `rc=0` 后继续到 merge。为避免此问题，在 `run_fix_pipeline` 中空候选时改为 `return 0` 但输出明确提示；oneshot 侧不做特殊处理——如果用户传了无效 `--chunk-id`，merge 阶段会合并已有的全部结果（不限于本次），这是合理行为。

简化决策：空候选时 `run_fix_pipeline` 正常 `return 0`，oneshot 流程照常继续到 merge。用户看到警告信息后可自行判断。

### 完成时 `status` 语义

有 `requested_ids` 且所有指定 chunk 处理完毕时，`progress["status"]` 设为 `"partial"`，复用现有 `--max-chunks` 截断时的语义。这样后续 `merge` 或 `--resume` 无需新增状态值，且 `partial` 的含义（"还有其他 chunk 未处理"）在此场景下也准确——用户只处理了部分 chunk。

### 事件日志

`run_started` 事件的 `data.filters` 中新增 `"chunk_ids"` 字段（与 `last_run_filters` 一致），便于 `events.jsonl` 回溯用户指定的筛选条件。

## 行为示例

| 命令 | 行为 |
|------|------|
| `run --stage agent`（未传 `--chunk-id`） | 行为完全等价于现有逻辑，无任何变化 |
| `run --stage agent --chunk-id 5` | 仅处理 chunk 5 |
| `run --stage agent --chunk-id 3-7 --chunk-id 12` | 处理 chunk 3、4、5、6、7、12 |
| `run --stage agent --chunk-id 999` | 警告超出范围，无有效 ID 时退出 |
| `run --stage agent --chunk-id abc` | 警告无效格式，无有效 ID 时退出 |
| `run --chunk-id 5` (全流模式) | oneshot 先 split 再仅跑 chunk 5 再 merge |
| `run --stage agent --chunk-id 5`（chunk 5 已 failed） | 跳过并提示 `使用 --include-failed 可重跑` |
| `run --stage agent --chunk-id 3-10 --max-chunks 3` | 处理 chunk 3、4、5 后停下，status=`partial` |
| 所有指定 chunk 处理完 | `status`=`partial`，提示 `如需汇总报告，请继续：misra-pipeline run --stage merge` |

## 兼容性

- 参数默认 `[]`，未传时行为完全等价于现有逻辑
- 不改变 `progress.json` schema（`last_run_filters.chunk_ids` 是可选字段）
- `--chunk-id` 可与 `--rule-id` / `--misra-only` / `--include-failed` 叠加：仍走原过滤函数，只是候选集合被缩小到指定 ID
- `--max-chunks` 在 `--chunk-id` 候选集合上独立生效，先到先停
- 不影响 `--retry-failed` 等现有参数行为

## 测试策略

1. **单元测试：`parse_chunk_id_specs`** — 覆盖单个 ID、范围、多规格、去重、越界、无效格式、空输入等场景
2. **单元测试：`next_chunk` 带 `requested_ids`** — 验证过滤逻辑：跳过已完成、跳过失败（除非 `include_failed`）、遵循 rule/misra 过滤
3. **集成测试：`run_fix_pipeline.main(["--chunk-id", "2"])`** — 在 mock 环境中验证仅处理指定 chunk
4. **回归测试：** 确保不加 `--chunk-id` 时所有现有行为不变
5. **CLI 参数测试：** 验证 `misra-pipeline-cli.py` 正确解析并转发 `--chunk-id`
6. **已完成 chunk 跳过测试：** 验证 `--chunk-id 5` 指定已完成 chunk 时不重复执行，正常跳过
7. **边界测试：** 验证 `--chunk-id` 指定 failed chunk 时输出提示信息