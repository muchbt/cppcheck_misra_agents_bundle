# CLI 入口简化设计

## 目标

将 MISRA Pipeline CLI 从 14 个平级命令简化为分层结构，让常见工作流（init → policy init → run）只需 3 步，无需理解内部模块概念。

## 当前问题

1. `oneshot` 才是用户真正需要的全流程命令，名字不直觉
2. `split`/`run`/`merge` 是内部概念，不应暴露给新用户
3. `--dry-run`、`--strategy` 等常用参数需要 `--` 透传（已用 `parse_known_args` 修复，但仍非一级选项）
4. `policy init` 必须指定 `--template`，无交互默认值
5. 查询进度需要 `oneshot --status`，不直觉
6. 14 个命令的认知负担过重
7. oneshot.py 中 4 处引用旧命令 `python3 .agents/tools/pipeline_cli.py doctor`

## 变更概要

| 方向 | 描述 | 涉及文件 |
|------|------|-----------|
| 1+2 | `run` 吸收 oneshot + 常用参数提升 | cli/misra-pipeline-cli.py, .agents/tools/oneshot.py |
| 3 | policy init 交互式选择 | .agents/tools/policy_init.py |
| 4 | `status` 顶级命令 | cli/misra-pipeline-cli.py |
| 5 | 帮助分层 | cli/misra-pipeline-cli.py |
| 6 | 修复旧引用 | .agents/tools/oneshot.py |

---

## 详细设计

### 1. `run` 命令吸收 oneshot（方向1+2）

**当前行为**：`run` → dispatch 到 `run_fix_pipeline.py`（单阶段 agent）

**新行为**：`run` 成为全流程命令，内联 oneshot 逻辑：

```
misra-pipeline run                          # 全流程 (split→agent→merge)
misra-pipeline run --fresh                  # 强制重新开始
misra-pipeline run --dry-run                # 预览 chunk 摘要，不启动 agent
misra-pipeline run --status                 # 查询进度
misra-pipeline run --stage split            # 仅 split
misra-pipeline run --stage agent            # 仅 agent 执行（原 run 行为）
misra-pipeline run --stage merge            # 仅 merge
misra-pipeline run --provider claude
misra-pipeline run --strategy conservative
misra-pipeline run --max-chunks 10
misra-pipeline run --retry-failed 2
misra-pipeline run --rule-id misra-c2012-2.2
misra-pipeline run --misra-only
misra-pipeline run --include-failed
misra-pipeline run --run-id 20260506-001
```

**一级参数定义**（在 CLI argparse 中，不再透传）：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--stage {split,agent,merge}` | choice | None（全流程） | 单阶段执行 |
| `--fresh` | flag | False | 强制全新开始 |
| `--resume` | flag | False | 显式续跑 |
| `--strategy {conservative,all_auto}` | choice | None | 修复策略 |
| `--dry-run` | flag | False | 预览模式 |
| `--status` | flag | False | 查询进度 |
| `--max-chunks N` | int | None | 最大 chunk 数 |
| `--retry-failed N` | int | None | 重试失败 chunk |
| `--rule-id ID` | append | [] | 指定规则 ID |
| `--misra-only` | flag | False | 仅 MISRA 规则 |
| `--include-failed` | flag | False | 包含失败 chunk |
| `--run-id ID` | str | None | 指定 run ID |
| `--verbose` | flag | False | 打印每个 chunk 完整 stdout/stderr |
| `--provider` | choice | None | Agent provider（已有） |

**参数互斥规则**：

- `--status` 与所有其他运行参数互斥：`--status` 时忽略 `--fresh`、`--resume`、`--dry-run`、`--stage`、`--strategy`、`--max-chunks`、`--retry-failed`、`--rule-id`、`--misra-only`、`--include-failed`、`--run-id`、`--verbose`（与 oneshot.py 当前行为一致：`--status` 早期返回，仅打印进度摘要）
- `--fresh` 和 `--resume` 不能同时使用
- `--stage` 与 `--fresh`/`--resume` 不冲突但 `--fresh` 仅在全流程模式下有效

**无效参数组合处理**：

不校验 `--stage` 与参数的冗余组合（如 `--stage split --max-chunks 10`），保持简单。多余参数会被 dispatch 到的阶段模块自行处理——无法识别的参数被 argparse 忽略或报错，此行为与直接调用阶段模块一致。

**`--stage` 映射**：

- `--stage split` → dispatch 到 `split_cppcheck_xml`（与原 `split` 命令相同）
- `--stage agent` → dispatch 到 `run_fix_pipeline`（与原 `run` 命令相同）
- `--stage merge` → dispatch 到 `merge_results`（与原 `merge` 命令相同）
- 不带 `--stage` → 执行完整 oneshot 逻辑（split→agent→merge，含续跑检测）

**内联策略**：将 oneshot.py 的核心逻辑（precheck、续跑检测、阶段编排、状态管理、dry-run、status）复制到 CLI 的 `cmd_run()` 函数中。oneshot.py 中的辅助函数（`collect_precheck_results`、`safe_load_progress`、`has_unfinished_runtime`、`print_status_summary`、`print_dry_run_summary`、`build_split_args`、`build_run_args`、`filter_blockers`、`run_module_stage`、`execute_stage`、`compute_user_status`、`get_current_commit_sha`）通过 import 从 oneshot 模块复用，不重复实现。

**续跑检测逻辑**（与 oneshot 一致）：
1. 检查 `progress.json` 是否有未完成运行
2. 有 → `mode = "resume"`，策略/run_id 冲突时报错
3. 无 或 `--fresh` → `mode = "fresh"`
4. `--fresh` 和 `--resume` 不能同时使用

**common/doctor 等模块的 import 方式**：通过 `_dispatch_pipeline_command` 已建立的 `sys.path` 机制，在 `cmd_run()` 中 dynamic import oneshot 模块获取工具函数。

### 2. `status` 顶级命令（方向4）

从 `run --status` 内部逻辑提取，新增顶级命令：

```
misra-pipeline status
```

等同于 `run --status`，但语义更清晰。

实现：`cmd_status()` 调用 oneshot 的 `print_status_summary()`。

### 3. `policy init` 交互式（方向3）

**当前行为**：`policy init --template misra_c2012_relaxed` 必须显式指定 template。

**新行为**：

- `misra-pipeline policy init` → 不带 `--template` 时，在终端（TTY）中显示模板列表让用户交互选择
- `misra-pipeline policy init --template misra_c2012_relaxed` → 非交互，直接使用指定模板（CI/脚本）
- 非 TTY 环境（管道、CI）且未指定 `--template` → 使用默认模板 `misra_c2012_relaxed` 并打印 warning

交互选择界面：
```
Available templates:
  [1] misra_c2012_conservative - MISRA C:2012 conservative policy - all rules require manual review
  [2] misra_c2012_relaxed     - MISRA C:2012 relaxed policy - low risk auto_fix, medium risk careful_fix
  [3] autosar_baseline        - AUTOSAR baseline policy - RTE/MCAL/BSW require manual review
  [4] cppcheck_common         - Cppcheck native rule policy - common error/warning strategies

Select template number [2]:
```

默认值选 `[2]`（misra_c2012_relaxed），回车即可确认。

**改动范围**：仅 `.agents/tools/policy_init.py` 的 `init_policy()` 函数和调用处。CLI 层不需要改动（`parse_known_args` 已可透传所有参数给 policy_init）。

### 4. 命令分层（方向5）

`--help` 输出：

```
usage: misra-pipeline [-h] {init,run,status,policy,doctor,env-check,split,merge,verify,bootstrap,validate,config,upgrade,version} ...

MISRA Pipeline CLI

Primary commands:
  init         Initialize .agents/ directory
  run          Run the MISRA fix pipeline (split→agent→merge)
  status       Show current pipeline run progress
  policy       Manage rule policy configuration
  doctor       Diagnose pipeline environment
  env-check    Check CLI installation

Advanced commands:
  split        Split cppcheck XML (use 'run --stage split')
  merge        Merge results (use 'run --stage merge')
  verify       Verify one chunk result
  bootstrap    Generate agent compatibility files
  validate     Provider validation test
  config       Manage CLI configuration
  upgrade      Upgrade .agents/ to a new version
  version      Show CLI and project version
```

实现方式：argparser 的 `description` 包含格式化的命令列表，子命令的 `help` 标注 `(advanced)` 后缀。

### 5. 修复旧引用（方向6）

oneshot.py 中 4 处 `python3 .agents/tools/pipeline_cli.py doctor` 改为 `misra-pipeline doctor`：

- 行 322
- 行 349
- 行 375
- 行 389

### 6. oneshot 处理

- `oneshot` 从 `PIPELINE_COMMANDS` 映射中移除，新增 deprecated alias：用户输入 `misra-pipeline oneshot` 时打印友好提示并退出
  ```
  'oneshot' has been merged into 'run'. Use 'misra-pipeline run' instead.
  ```
  实现方式：在 `parse_args` 的子命令列表中保留 `oneshot` 作为特殊子命令，添加 `help="(deprecated) Use 'run' instead"`，`main()` 中捕获后打印提示并 `return 1`
- `oneshot.py` 保留在 `.agents/tools/` 中，标记为 deprecated（文件头注释加 `DEPRECATED: Use 'misra-pipeline run' instead.`）
- CLI 的 `cmd_run()` 通过 dynamic import 调用 oneshot 模块的辅助函数
- `run` 在 `PIPELINE_COMMANDS` 中的映射从 `run_fix_pipeline` 改为指向 `cmd_run` 内置函数（不再走 dispatch）

### 7. 不做的事

- 不改 policy 子命令的 `parse_known_args` 透传行为
- 不删除 `.agents/tools/oneshot.py`（保留作向后兼容）
- 不改 `split`、`merge`、`verify`、`bootstrap`、`validate`、`doctor` 的 dispatch 行为
- 不改 install.sh

---

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `cli/misra-pipeline-cli.py` | 修改 | 新增 `cmd_run()`、`cmd_status()`；`run` 从 PIPELINE_COMMANDS 移除；`oneshot` 从 PIPELINE_COMMANDS 移除；新参数定义；帮助分层；`status` 顶级命令 |
| `.agents/tools/oneshot.py` | 修改 | 标记 deprecated；修复 4 处旧命令引用；提取 `print_status_summary` 等为可 import 函数 |
| `.agents/tools/policy_init.py` | 修改 | `init_policy()` 无 template 时交互选择 |
| `tests/test_misra_pipeline_cli.py` | 修改 | 新增 `cmd_run` 测试、`status` 测试；更新 `run` 从 PIPELINE_COMMANDS 移除的测试 |
| `docs/superpowers/specs/2026-05-06-simplify-cli-entrance-design.md` | 新增 | 本文档 |

---

## 测试策略

1. `cmd_run()` 全流程：mock dispatch 测试 split→agent→merge 编排
2. `cmd_run()` 单阶段：`--stage split`/`--stage agent`/`--stage merge` 正确 dispatch
3. `cmd_run()` 状态管理：fresh/resume 检测、续跑逻辑
4. `cmd_run()` 参数传递：常用参数正确传递到各阶段模块
5. `cmd_status()`：等同于 `run --status`
6. `policy init` 交互式：TTY 模拟选择、非 TTY 默认值、显式 `--template` 非交互
7. 帮助输出：Primary/Advanced 分层可见
8. 旧命令兼容：`split`、`merge` 仍可通过 dispatch 工作
9. `oneshot.py` deprecated 标记和旧引用修复