Let me find and read both files.



Let me verify the current state of the files referenced by the plan to ensure accuracy.

Now let me check the existing `pipeline_cli.py` and its tests, as well as the `policy_init.py` interface.



Let me check the [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:43:0-68:59) signatures of the target modules to verify the dispatch calling convention.

Now I have enough context. Here is a comprehensive review.

---

# 审核报告：统一 CLI 入口方案与计划

## 一、设计方案审核 ([2026-05-06-unified-cli-entry-design.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/specs/2026-05-06-unified-cli-entry-design.md:0:0-0:0))

### ✅ 优点

1. **架构思路清晰** — 保留模块原地、仅废弃分发器的混合策略合理，避免了 `common.py` 路径计算和 `init` 分发流程的连锁修改。
2. **职责划分明确** — `env-check`（CLI 环境）vs `doctor`（pipeline 运行环境）的分拆逻辑清晰。
3. **风险识别到位** — `sys.path` 污染、`sys.argv` 全局状态、policy 参数同步等均已识别。

### 🔴 严重问题

#### 1. [module.main(args)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 调用约定不匹配

设计中 `_dispatch_pipeline_command` 统一调用 [module.main(args)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12)，但实际模块签名不一致：

| 模块 | 签名 | 传 `args` 会？ |
|---|---|---|
| `merge_results` | [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) — 无参数 | **TypeError** |
| `bootstrap_agents` | [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) — 无参数 | **TypeError** |
| `verify_chunk` | [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) — 无参数 | **TypeError** |
| `doctor` | [main(argv: Optional[List[str]])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) | ✅ |
| `split_cppcheck_xml` | [main(argv: Optional[List[str]])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) | ✅ |
| `run_fix_pipeline` | [main(argv: Optional[List[str]])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) | ✅ |
| `validate_real` | [main(argv: Optional[Sequence[str]])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) | ✅ |
| `oneshot` | [main(argv: Optional[List[str]])](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) | ✅ |

**修复建议**：用 `inspect.signature` 检测参数数量，或更简单地用 try/except 降级：

```python
import inspect
sig = inspect.signature(module.main)
if len(sig.parameters) > 0:
    result = module.main(args)
else:
    result = module.main()
```

#### 2. `--provider` 全局标志被静默丢弃

原 [pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:0:0-0:0) 支持 `--provider {codex,claude,opencode,kimi}`（设置 `PIPELINE_AGENT_PROVIDER` 环境变量），该功能在新设计中完全消失，且无废弃说明。相关测试（[test_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:0:0-0:0) 第92-173行）也被丢弃而非迁移。

**修复建议**：在统一 CLI 的 pipeline 命令分发前添加 `--provider` 支持，或在方案中显式说明废弃理由。

### 🟡 中等问题

#### 3. `sys.path` 不恢复

方案风险表提到 "使用 try/finally 确保恢复"，但代码实现只恢复 `sys.argv`，不恢复 `sys.path`。单进程中多次调用不同命令时，`.agents/tools/` 始终留在 `sys.path` 中。

**建议**：要么在 `finally` 中恢复 `sys.path`，要么在方案中明确说明 "追加一次、全局生效" 是有意为之。

#### 4. policy 参数回转（args → argv）脆弱

`_dispatch_policy_command` 将 argparse 解析后的结果逐字段拼回 argv 再传给 [policy_init.main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12)。任何 [policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/policy_init.py:0:0-0:0) 的参数变更都需要同步修改两处代码。

**替代方案**：policy 也可以像其他命令一样用 `REMAINDER` 转发，仅在 CLI help 层面提供子命令结构（通过 epilog 或自定义 help formatter），避免双重解析。

#### 5. 缺少 `importlib` import 声明

当前 [cli/misra-pipeline-cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:0:0-0:0) 没有 `import importlib`，方案和计划均未提及需要添加此 import。

### 🟢 小问题

- **docstring 更新遗漏**：文件头部 docstring（第2-8行）仍列出 `doctor` 而非 `env-check`，且未列出新命令。
- **`validate-real` → `validate` 改名缺乏向后兼容**：旧 [pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:0:0-0:0) 用 `validate-real`，用户/脚本迁移可能遗漏，建议在错误处理中给出提示。

---

## 二、实施计划审核 ([2026-05-06-unified-cli-entry-plan.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/plans/2026-05-06-unified-cli-entry-plan.md:0:0-0:0))

### ✅ 优点

1. **任务拆分合理** — 5 个 Task 按依赖关系排列，每步包含完整代码和验证命令。
2. **Self-Review Checklist 完备** — Spec 覆盖表、Placeholder Scan、Type Consistency 均已检查。
3. **Commit 粒度恰当** — 每个逻辑单元一个 commit，便于回滚。

### 🔴 严重问题（继承自设计方案）

#### 1. Task 2 Step 2: `_dispatch_pipeline_command` 会对 3 个模块抛 TypeError

同上，[module.main(args)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 对 `merge_results`、`bootstrap_agents`、`verify_chunk` 会失败。

#### 2. Task 3 Step 3: 测试 [FakeModule.main(self, argv)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 掩盖了真实 bug

测试中 [FakeModule.main](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 接受 `argv` 参数，因此测试会通过。但真实模块 [merge_results.main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 不接受参数，测试无法暴露问题。

### 🟡 中等问题

#### 3. Task 2 Step 3: `policy_add_parser` 中 `-f` 和 `-t` 短选项冲突

```python
policy_add_parser.add_argument("--force", "-f", ...)
policy_add_parser.add_argument("--risk-tags", "-t", ...)
```

虽然与其他 sub-parser 不冲突，但 **`policy_add_parser` 本身内部** `-f` 被 `--force` 占用，而 `-t` 被 `--risk-tags` 占用。需确认这是有意设计。实际上 [policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/policy_init.py:0:0-0:0) 原生参数可能使用不同的短选项——应对照源码确认。

#### 4. Task 3: 缺少 `--provider` 相关测试迁移

[test_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:0:0-0:0) 中有 4 个 provider 相关测试（第66-80、92-173行），计划中未提及迁移或废弃决定。

#### 5. Task 2 Step 1: `PIPELINE_COMMANDS` 类型标注位置

计划说"在 `MIN_PYTHON` 之后、`if sys.version_info < MIN_PYTHON:` 之前添加"。但 `MIN_PYTHON` 后紧接 Python 版本检查（模块级早退逻辑），在此之间插入常量定义不影响功能，但从代码组织来看，放在版本检查 **之后** 更合理。

#### 6. Task 4: 旧测试中有价值的测试未迁移

[test_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:0:0-0:0) 包含以下值得迁移的测试逻辑：
- **dispatch + argv 传递验证**（第27-41行）
- **provider 环境变量管理**（第92-173行）
- **无效命令拒绝**（第51-53行）

计划仅说 "有用的测试迁移到 test_misra_pipeline_cli.py"，但实际 Task 3 中只写了新测试，没有迁移旧测试。

### 🟢 小问题

- **缺少 `import importlib`** — Task 2 代码中使用 `importlib.import_module` 但未在任何步骤中添加 import 语句。
- **缺少 `import tempfile`** — Task 3 Step 3 的 `test_dispatch_import_error` 使用了 `tempfile.TemporaryDirectory` 但未添加 import。
- **`test_dispatch_missing_tools_dir`** 的 mock 可能不工作 — `patch.object(misra_pipeline_cli.Path, "cwd", ...)` 需要确认 `Path.cwd` 是否可以被 patch（它是 classmethod）。

---

## 三、总结与建议

| 优先级 | 问题 | 建议 |
|---|---|---|
| **P0** | [main(args)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 调用约定不匹配，3个模块会 TypeError | 检测签名或统一模块接口 |
| **P0** | `--provider` 功能静默丢失 | 显式迁移或记录废弃 |
| **P1** | 缺少 `import importlib` | 在 Task 2 Step 1 追加 import |
| **P1** | policy args→argv 回转脆弱 | 考虑改用 REMAINDER 转发 |
| **P1** | 旧测试未实质迁移 | 在 Task 3 中明确列出要迁移的测试 |
| **P2** | `sys.path` 不恢复 | 在方案中说明设计意图或添加 cleanup |
| **P2** | docstring / help text 未更新 | 追加步骤 |

**结论**：方案整体架构设计合理，但 **P0 级的 [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:788:0-803:12) 签名不匹配问题**会导致 `split`/`run`/`doctor`/`validate`/`oneshot` 以外的 3 个命令在运行时直接崩溃，必须在实施前修复。建议修复上述问题后再启动执行。
