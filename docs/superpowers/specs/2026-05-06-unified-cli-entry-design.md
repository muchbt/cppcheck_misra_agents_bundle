# misra-pipeline 统一 CLI 入口设计

**日期**: 2026-05-06
**状态**: Draft (v2 — 修复审核问题)

## 1. 目标

将 `cli/misra-pipeline-cli.py` 打造为**唯一**的 CLI 入口，废弃 `.agents/tools/pipeline_cli.py`，同时把 `misra-pipeline-cli.py` 中原有的 `doctor` 改名为 `env-check` 以避免与 pipeline 诊断命令冲突。

## 2. 当前架构

```
cli/misra-pipeline-cli.py          (项目级 CLI：init/upgrade/version/doctor/config)
.agents/tools/pipeline_cli.py      (pipeline 级 CLI 调度器)
    ├── split      → split_cppcheck_xml.py
    ├── run        → run_fix_pipeline.py
    ├── merge      → merge_results.py
    ├── verify     → verify_chunk.py
    ├── bootstrap  → bootstrap_agents.py
    ├── doctor     → doctor.py
    ├── validate-real → validate_real.py
    ├── oneshot    → oneshot.py
    └── policy     → policy_init.py
```

## 3. 目标架构

```
cli/misra-pipeline-cli.py          (唯一统一入口)
    │
    ├── init        (原有：初始化 .agents/)
    ├── upgrade     (原有：升级 .agents/)
    ├── version     (原有：显示版本)
    ├── env-check   (改名：原 doctor，CLI 环境检查)
    ├── config      (原有：管理 CLI 配置)
    │
    ├── split       (新增：拆分 cppcheck.xml)
    ├── run         (新增：执行 agent pipeline)
    ├── merge       (新增：合并结果生成报告)
    ├── verify      (新增：验证单个 chunk)
    ├── bootstrap   (新增：生成兼容层)
    ├── doctor      (新增：pipeline 运行环境诊断)
    ├── validate    (新增：Provider 验收，原 validate-real)
    ├── oneshot     (新增：一键执行 split→run→merge)
    └── policy      (新增：策略管理 init/list/test/add)
```

## 4. 模块迁移策略

采用**混合策略**：

- **统一入口**：所有命令注册在 `cli/misra-pipeline-cli.py` 中
- **功能模块保留原地**：`.agents/tools/` 下的 `split_cppcheck_xml.py`、`doctor.py` 等核心模块**不迁移**
- **废弃分发器**：移除 `.agents/tools/pipeline_cli.py`

**不物理迁移模块的原因**：

1. `.agents/tools/common.py` 通过 `Path(__file__).resolve().parents[2]` 计算项目根目录，迁移到 `cli/` 后该计算会失效
2. `.agents/tools/` 是 `misra-pipeline init` 分发到新项目的一部分，搬空后 init 流程需要大幅调整
3. 各模块间存在复杂的内部导入关系（`common.py`、`agent_runner.py`、`providers/` 等），迁移会牵一发而动全身

**调用方式**：`misra-pipeline-cli.py` 在运行时动态将当前工作目录下的 `.agents/tools/` 加入 `sys.path`，通过 `importlib` 导入对应模块并调用其 `main()`。

## 5. 命令映射详情

| misra-pipeline 命令 | 目标模块 | main() 签名 | 参数解析方式 | 说明 |
|---------------------|----------|-------------|--------------|------|
| `init` | 内置 | N/A | 完整定义 | 初始化 `.agents/` |
| `upgrade` | 内置 | N/A | 完整定义 | 升级 `.agents/` |
| `version` | 内置 | N/A | 完整定义 | 显示 CLI 和项目版本 |
| `env-check` | 内置 | N/A | 完整定义 | 原 `doctor`，检查 CLI 安装环境 |
| `config` | 内置 | N/A | 完整定义 | 管理 CLI 配置（show/set/reset）|
| `split` | `split_cppcheck_xml` | `main(argv=None)` | Remainder 转发 | 拆分 cppcheck.xml |
| `run` | `run_fix_pipeline` | `main(argv=None)` | Remainder 转发 | 执行修复流水线 |
| `merge` | `merge_results` | `main()` 无参数 | Remainder 转发 | 合并 chunk 结果 |
| `verify` | `verify_chunk` | `main()` 无参数 | Remainder 转发 | 验证单个 chunk |
| `bootstrap` | `bootstrap_agents` | `main()` 无参数 | Remainder 转发 | 生成 agent 兼容层 |
| `doctor` | `doctor` | `main(argv=None)` | Remainder 转发 | pipeline 运行环境诊断 |
| `validate` | `validate_real` | `main(argv=None)` | Remainder 转发 | Provider 验收测试（原 `validate-real`）|
| `oneshot` | `oneshot` | `main(argv=None)` | Remainder 转发 | 一键执行 |
| `policy` | `policy_init` | `main(argv=None)` | 子命令+Remainder 转发 | 策略管理 |

### 5.1 平铺命令转发逻辑（含 main() 签名适配）

对于 `split`、`run`、`merge`、`verify`、`bootstrap`、`doctor`、`validate`、`oneshot`，采用极简 parser + 剩余参数转发模式。**关键**：由于 `merge_results`、`bootstrap_agents`、`verify_chunk` 的 `main()` 不接受参数，需要用 `inspect.signature` 检测并适配调用约定：

```python
import inspect

PIPELINE_COMMANDS = {
    "split": "split_cppcheck_xml",
    "run": "run_fix_pipeline",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "doctor": "doctor",
    "validate": "validate_real",
    "oneshot": "oneshot",
}

# Note: --provider handling is shown separately in §6.
def _dispatch_pipeline_command(command: str, args: list[str], provider: Optional[str] = None) -> int:
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.", file=sys.stderr)
        return 1

    tools_dir_str = str(tools_dir.resolve())
if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)
    # Note: sys.path is intentionally not restored — see §12 risk table.
```

### 5.2 policy 子命令处理

`policy` 在 `misra-pipeline-cli.py` 中定义为子命令结构（init/list/test/add），以提供良好的 `--help` 体验：

```bash
misra-pipeline policy init [--template TEMPLATE] [--output PATH] [--force]
misra-pipeline policy list [--rule-id PATTERN]
misra-pipeline policy test --rule-id ID --file PATH
misra-pipeline policy add --rule-id ID --action ACTION [--risk-level LEVEL] ...
```

为避免双重解析的脆弱性，policy 子命令解析后**将剩余参数原样转发给 `policy_init.main()`**，不在 CLI 层做 args→argv 回转。argparse 的子命令结构仅用于 `--help` 展示，实际参数通过 `nargs=argparse.REMAINDER` 透传：

```python
policy_parser = subparsers.add_parser(
    "policy",
    help="Manage policy configuration",
    epilog=(
        "Examples:\n"
        "  misra-pipeline policy init --template misra_c2012_relaxed\n"
        "  misra-pipeline policy list\n"
        "  misra-pipeline policy list --rule-id misra*\n"
        "  misra-pipeline policy test --rule-id R1.1 --file test.c\n"
        "  misra-pipeline policy add --rule-id R1.1 --action auto_fix\n"
        "\n"
        "Use 'misra-pipeline policy -- --help' to see policy_init's full help."
    ),
    formatter_class=argparse.RawDescriptionHelpFormatter,
)
policy_parser.add_argument("policy_args", nargs=argparse.REMAINDER,
                           help="Arguments passed to policy_init")
```

**注意**：由于 argparse 的 `REMAINDER` 与子命令解析存在互斥问题，policy 采用纯 REMAINDER 转发模式。`misra-pipeline policy --help` 通过 `epilog` 展示常用用法示例，弥补缺失子命令帮助的体验降级。

## 6. `--provider` 全局参数

原 `pipeline_cli.py` 支持 `--provider {codex,claude,opencode,kimi}` 全局参数（设置 `PIPELINE_AGENT_PROVIDER` 环境变量）。新设计中**迁移此功能**：

在 `parse_args()` 中为所有 pipeline 子命令添加 `--provider` 参数：

```python
for cmd_name in PIPELINE_COMMANDS:
    cmd_parser = subparsers.add_parser(cmd_name, ...)
    cmd_parser.add_argument("--provider", "-P",
                           choices=["codex", "claude", "opencode", "kimi"],
                           default=None,
                           help="Override agent provider (sets PIPELINE_AGENT_PROVIDER env var)")
    cmd_parser.add_argument("args", nargs=argparse.REMAINDER, ...)
```

在 `_dispatch_pipeline_command()` 中，执行模块前设置环境变量，执行后恢复：

```python
import os
original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")

try:
    if args.provider:
        os.environ["PIPELINE_AGENT_PROVIDER"] = args.provider
    elif original_provider is not None:
        os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
    # ... call module
finally:
    if original_provider is not None:
        os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
    else:
        os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
```

注意：`--provider` 需要与 `nargs=REMAINDER` 配合使用。argparse 中 `--provider` 必须出现在 REMAINDER 参数之前，即 `misra-pipeline run --provider claude -- args...`。

## 7. doctor / env-check 处理

- `misra-pipeline-cli.py` 中原 `cmd_doctor` 函数改名为 `cmd_env_check`
- `parse_args()` 中 `doctor` parser 改为 `env-check` parser
- 新增 `doctor` 命令，映射到 `.agents/tools/doctor.py` 模块
- **文件头部 docstring 更新**：列出新命令列表，`doctor` 改为 `env-check`

职责划分：
- `misra-pipeline env-check`：检查 CLI 安装环境（Python 版本、Git 可用性、CLI 安装状态、项目初始化状态）
- `misra-pipeline doctor`：诊断 pipeline 运行环境（cppcheck.xml、pipeline.json、rule_policy.json、agent 配置、认证、网络等）

## 8. `validate-real` → `validate` 改名兼容

旧 `pipeline_cli.py` 使用 `validate-real` 作为命令名，新 CLI 改为 `validate`。为帮助迁移，在 `validate` 命令的 help 文本中注明原名：

```python
subparsers.add_parser("validate", help="Provider validation test (formerly 'validate-real')")
```

如果用户输入 `validate-real`，argparse 会报错并提示可用命令。

## 9. 向后兼容与废弃策略

1. **废弃 `pipeline_cli.py`**：移除 `.agents/tools/pipeline_cli.py` 文件
2. **测试迁移**：`tests/test_pipeline_cli.py` 中有价值的测试迁移到 `tests/test_misra_pipeline_cli.py`，包括：
   - dispatch + argv 传递验证（第27-41行）
   - `--provider` 环境变量管理（第92-173行）
   - 无效命令拒绝（第51-53行）
3. **文档更新**：相关文档中的命令示例从 `python .agents/tools/pipeline_cli.py <command>` 更新为 `misra-pipeline <command>`
4. **init 分发**：`misra-pipeline init` 的 `AGENTS_DIRS_TO_COPY` 中仍然包含 `tools` 目录（功能模块保留原地，只是移除了 `pipeline_cli.py` 这个分发器）

## 10. 测试策略

### 10.1 parse_args 测试

为每个新增命令添加 `parse_args` 测试。

### 10.2 转发逻辑测试（含签名适配）

`FakeModule` 需要模拟两种签名：

```python
class FakeModuleWithArgs:
    """Module whose main() accepts argv."""
    def main(self, argv=None):
        seen["argv"] = list(sys.argv)
        return 0

class FakeModuleNoArgs:
    """Module whose main() takes no arguments (merge_results, bootstrap_agents, verify_chunk)."""
    def main(self):
        seen["called"] = True
        return 0
```

测试 `_dispatch_pipeline_command` 对两种签名都能正确调用。

**重要**：所有涉及 `.agents/tools/` 路径检查的测试必须创建临时目录并 mock `Path.cwd`，不能使用链式 MagicMock 模拟路径操作：

```python
with tempfile.TemporaryDirectory() as tmp:
    tools_dir = Path(tmp) / ".agents" / "tools"
    tools_dir.mkdir(parents=True)
    with patch.object(misra_pipeline_cli.Path, "cwd", return_value=Path(tmp)):
        # ... test code ...
```

断言时使用 `seen["provider"]` 而非 `seen.get("provider")`，以确保回调确实被执行。

### 10.3 `--provider` 测试

迁移 `test_pipeline_cli.py` 中的 provider 相关测试，验证：
- `--provider codex` 设置 `PIPELINE_AGENT_PROVIDER` 环境变量
- 无 `--provider` 时不设置环境变量
- 连续调用时，第二次无 `--provider` 不应保留第一次的值

### 10.4 env-check 测试

迁移原 `doctor` 相关的测试到 `env-check`。

### 10.5 policy 子命令测试

验证 policy 的 REMAINDER 转发。

### 10.6 测试文件 import 要求

`tests/test_misra_pipeline_cli.py` 顶部需确保以下导入存在：

```python
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
```

`tempfile` 和 `MagicMock` 是新增依赖（用于临时目录创建和 mock），必须添加。

## 11. 错误处理

1. **`.agents/tools/` 不存在**：如果执行 pipeline 命令时当前目录下没有 `.agents/tools/`，提示用户先运行 `misra-pipeline init`
2. **模块导入失败**：捕获 `ImportError`，提示用户检查 `.agents/` 安装完整性
3. **目标模块返回非整数**：视为成功（返回 0）
4. **`main()` 签名不匹配**：使用 `inspect.signature` 检测参数数量，适配有参数和无参数两种签名

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| `main()` 签名不一致 | 3个模块不接受argv，直接传参会 TypeError | 使用 `inspect.signature` 检测参数数量并适配 |
| `sys.path` 污染 | 动态添加 `.agents/tools/` 可能影响其他导入 | 有意为之：追加一次、全局生效，无需恢复（同一进程可能多次调用） |
| `sys.argv` 全局状态 | 修改 `sys.argv` 可能影响其他代码 | 使用 `try/finally` 确保恢复原始 `sys.argv` |
| policy 参数同步 | policy_init.py 的参数变更需要同步到 misra-pipeline-cli.py | policy 采用 REMAINDER 转发，避免双重解析；仅 help 文本需同步 |
| `--provider` 功能丢失 | 原 pipeline_cli.py 的 --provider 被静默丢弃 | 迁移 --provider 到新 CLI，含环境变量管理和恢复逻辑 |
| `pipeline_cli.py` 被外部脚本引用 | 移除后外部脚本失效 | 在 CHANGELOG 中明确说明，提供迁移指南 |
| `validate-real` → `validate` 改名 | 用户/脚本迁移可能遗漏 | 在 help 文本中注明原名 |
| `import importlib` 缺失 | 运行时报 NameError | 在文件顶部 import 区添加 `import importlib` 和 `import inspect` |