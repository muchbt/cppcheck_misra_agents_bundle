## 上轮问题修复验证

| 上轮问题 | 修复位置 | 状态 |
|----------|----------|------|
| P0: `--verbose` 未加入 oneshot.py | Task 1 Step 2（第27-42行） | ✅ |
| P1: 含两版 cmd_run()，第一版有 bug | 已删除错误版本 | ✅ |
| P2: 非 TTY 默认模板用了 index 0 | Task 5 第536行，显式 `"misra_c2012_relaxed"` | ✅ |
| P2: `_import_oneshot_helpers` 缺 tools_dir 检查 | Task 3 第197-202行 | ✅ |
| P3: Task 4 Step 3 无具体测试代码 | 第450-507行，6 个具体测试 | ✅ |

---

## 新发现的问题

### 🟡 P1: `_import_oneshot_helpers()` 重复出现两次

Task 3 Step 1 中函数定义出现了两份（第193-206行和第208-221行），是编辑遗留。两份内容相同，但会误导实施者。

**修复**：删除第193-207行的第一份（含其未闭合的 ` ``` `），只保留第208-221行那份。

### 🟡 P2: `cmd_run()` 中参数校验在 import 之后，导致测试失败

当前 `cmd_run()` 逻辑顺序（第224-235行）：

```python
def cmd_run(args):
    oneshot = _import_oneshot_helpers()     # ← 先 import（需要 .agents/tools/ 存在）
    if args.status: ...
    if args.fresh and args.resume:          # ← 后校验
        return 2
```

`test_run_fresh_resume_conflict`（第468-472行）没有创建 temp dir 或 mock `Path.cwd`，所以 `_import_oneshot_helpers()` 会在到达 `--fresh`/`--resume` 校验之前因找不到 `.agents/tools/` 而 `SystemExit(1)`。

**修复**：将纯参数校验移到 import 之前：

```python
def cmd_run(args):
    if args.fresh and args.resume:
        print("[run] --fresh and --resume cannot be used together.", file=sys.stderr)
        return 2

    oneshot = _import_oneshot_helpers()
    if args.status:
        return oneshot.print_status_summary()
    ...
```

### 🟡 P2: `test_run_stage_split_dispatches` 缺少 oneshot.py stub

第474-487行的测试只创建了 [split_cppcheck_xml.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:0:0-0:0) stub，但 `cmd_run()` 第226行首先调用 `_import_oneshot_helpers()` 导入 oneshot 模块。缺少 oneshot.py stub 会导致 `ImportError`。

**修复**：要么在 temp dir 中补充 oneshot.py stub，要么 mock `_import_oneshot_helpers`：

```python
with patch.object(misra_pipeline_cli, "_import_oneshot_helpers"):
    with patch.object(misra_pipeline_cli, "_call_module_main", return_value=0) as mock_call:
        result = misra_pipeline_cli.cmd_run(args)
```

如果采用 P2 上面的修复（参数校验前移），`--stage` 分支仍然需要 import oneshot（因为 `_import_oneshot_helpers()` 在 stage 分支之前调用）。实际上 `--stage` 模式不需要 oneshot，可以将 `_import_oneshot_helpers()` 延迟到真正需要时：

```python
def cmd_run(args):
    if args.fresh and args.resume:
        return 2

    if args.stage:
        # Single-stage: doesn't need oneshot
        ...

    # Full-flow: needs oneshot
    oneshot = _import_oneshot_helpers()
    if args.status:
        return oneshot.print_status_summary()
    ...
```

这同时修复了 P2 的两个问题，并优化了 `--stage` 路径不依赖 oneshot。

### 🟢 P3: `test_oneshot_deprecated_message` 有未使用变量

第504行 [args = misra_pipeline_cli.parse_args(["oneshot"])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:30:0-43:68) 未使用，因为第505行 [main(["oneshot"])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:225:0-429:42) 内部会重新 parse。建议删除第504行。

---

## 总结

| 优先级 | 问题 | 修复方式 |
|--------|------|----------|
| **P1** | `_import_oneshot_helpers()` 重复两份 | 删除第一份（第193-207行） |
| **P2** | `cmd_run()` import 在参数校验前 + `--stage` 不需要 oneshot | 重排 cmd_run() 逻辑：校验 → stage 分支 → import oneshot → 全流程 |
| **P2** | `test_run_stage_split_dispatches` 缺 oneshot stub | mock `_import_oneshot_helpers`（重排后不再需要） |
| **P3** | `test_oneshot_deprecated_message` 未使用变量 | 删除第504行 |

**核心建议**：将 `cmd_run()` 重排为：
1. 参数互斥校验（`--fresh`/`--resume`）
2. `--stage` 单阶段分支（无需 oneshot import）
3. `_import_oneshot_helpers()`
4. `--status` 早期返回
5. 全流程 oneshot 委托

这样 3 个测试问题同时解决，且 `--stage` 路径更轻量。
