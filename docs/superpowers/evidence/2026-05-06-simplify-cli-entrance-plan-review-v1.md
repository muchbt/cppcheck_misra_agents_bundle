

Now let me cross-check the plan's code against the actual oneshot.py to verify a key detail:
Confirmed the issue. Now let me also verify the policy_init template ordering:

# 计划审核报告

## 与设计文档对照

| 设计要求 | 计划覆盖 | 状态 |
|----------|----------|------|
| `run` 吸收 oneshot + 14 个一级参数 | Task 2 + Task 3 | ✅ |
| `status` 顶级命令 | Task 2 Step 2 + Task 3 Step 1 | ✅ |
| `oneshot` deprecated alias | Task 2 Step 2 + Task 3 Step 2 | ✅ |
| `policy init` 交互式 | Task 5 | ✅ |
| 帮助分层 | Task 2 Step 4 | ✅ |
| 修复 oneshot.py 旧引用 | Task 1 | ✅ |
| oneshot.py deprecated 标记 | Task 1 Step 1 | ✅ |
| 集成测试 | Task 6 | ✅ |

---

## 发现的问题

### 🔴 P0: `--verbose` 未传播到 oneshot.py — 全流程模式会报错

`cmd_run()` 全流程分支在第386-387行构建 `oneshot_argv` 时加入了 `--verbose`：

```python
if getattr(args, "verbose", False):
    oneshot_argv.append("--verbose")
```

但 [oneshot.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:0:0-0:0) 的 [parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:133:0-222:17) **不支持 `--verbose`**：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:31-44
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键执行 split -> run -> merge，可自动续跑。")
    parser.add_argument("--fresh", action="store_true", help="忽略已有运行状态，强制从 split 重新开始。")
    parser.add_argument("--resume", action="store_true", help="显式续跑模式，与默认续跑行为一致，用于脚本中表达意图。")
    parser.add_argument("--strategy", choices=sorted(VALID_STRATEGIES), default=None)
    parser.add_argument("--run-id", default=None, help="仅 fresh 模式允许传入，格式 YYYYMMDD-XXX。")
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--retry-failed", type=int, default=None)
    parser.add_argument("--rule-id", action="append", default=[])
    parser.add_argument("--misra-only", action="store_true")
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="预览模式：split 后打印 chunk 摘要，不启动 agent。")
    parser.add_argument("--status", action="store_true", help="查询当前运行进度并输出人类可读摘要。")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)
```

[build_run_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:184:0-198:21) 也不转发 `--verbose`：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:185-199
def build_run_args(args: argparse.Namespace, resume_status: str) -> List[str]:
    stage_args: List[str] = []
    if args.strategy:
        stage_args.extend(["--strategy", args.strategy])
    if args.max_chunks is not None:
        stage_args.extend(["--max-chunks", str(args.max_chunks)])
    if args.retry_failed is not None:
        stage_args.extend(["--retry-failed", str(args.retry_failed)])
    for rule_id in args.rule_id:
        stage_args.extend(["--rule-id", rule_id])
    if args.misra_only:
        stage_args.append("--misra-only")
    if args.include_failed or resume_status == "failed":
        stage_args.append("--include-failed")
    return stage_args
```

**后果**：`misra-pipeline run --verbose` 会导致 [oneshot.parse_args(["--verbose"])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:133:0-222:17) 抛出 argparse 错误退出。

**修复**：在 Task 1 中增加一步，给 [oneshot.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:0:0-0:0) 添加 `--verbose` 支持：
1. [parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:133:0-222:17) 中加 `parser.add_argument("--verbose", action="store_true")`
2. [build_run_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:184:0-198:21) 中加 `if args.verbose: stage_args.append("--verbose")`

### 🟡 P1: 计划包含已知有 bug 的第一版 `cmd_run()`

Task 3 Step 1（第176-272行）包含一个已知错误的 `cmd_run()` 版本，然后在第272行说"Wait — the above approach has an issue"再给出修正版（第276-408行）。实施者可能误用第一版。

**修复**：删除第176-272行的错误版本，只保留修正版。

### 🟡 P2: 非 TTY 默认模板与设计不一致

Task 5 Step 1 中 `_select_template_interactive()` 非 TTY 分支（第548-550行）：

```python
if not sys.stdin.isatty():
    default = template_list[0][0]  # → misra_c2012_conservative
```

但设计文档明确要求默认 `misra_c2012_relaxed`（`AVAILABLE_TEMPLATES` 中 index 1）：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\policy_init.py:26-31
AVAILABLE_TEMPLATES = {
    "misra_c2012_conservative": "MISRA C:2012 conservative policy - all rules require manual review",
    "misra_c2012_relaxed": "MISRA C:2012 relaxed policy - low risk auto_fix, medium risk careful_fix",
    "autosar_baseline": "AUTOSAR baseline policy - RTE/MCAL/BSW require manual review",
    "cppcheck_common": "Cppcheck native rule policy - common error/warning strategies",
}
```

**修复**：改为显式指定 `default = "misra_c2012_relaxed"`，不依赖列表索引。

### 🟡 P2: `_import_oneshot_helpers()` 缺少 tools_dir 存在性检查

计划第277-283行：

```python
def _import_oneshot_helpers():
    tools_dir = Path.cwd() / ".agents" / "tools"
    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)
    return importlib.import_module("oneshot")
```

未检查 `.agents/tools/` 是否存在。[_dispatch_pipeline_command](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:883:0-930:59) 有此检查（CLI 第868-874行），这里也应一致。

**修复**：加上存在性检查和友好提示：

```python
def _import_oneshot_helpers():
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.", file=sys.stderr)
        raise SystemExit(1)
    ...
```

### 🟢 P3: Task 4 Step 3 缺少具体测试代码

其他 Task 均有完整代码片段，但 Task 4 Step 3（第508-518行）仅列了 6 条测试描述，无具体代码。建议补充至少 `cmd_run --status` 和 `cmd_run --fresh --resume` 的测试代码。

---

## 总结

| 优先级 | 问题 | 修复方式 |
|--------|------|----------|
| **P0** | `--verbose` 未加入 oneshot.py，全流程 `run --verbose` 会崩溃 | Task 1 增加 oneshot.py 的 `--verbose` 支持 |
| **P1** | 计划含两版 cmd_run()，第一版有 bug | 删除错误版本 |
| **P2** | 非 TTY 默认模板用了 index 0（conservative），应为 relaxed | 改为 `"misra_c2012_relaxed"` 显式指定 |
| **P2** | `_import_oneshot_helpers` 缺 tools_dir 检查 | 加存在性检查 |
| **P3** | Task 4 Step 3 无具体测试代码 | 补充关键测试 |
