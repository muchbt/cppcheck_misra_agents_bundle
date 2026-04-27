# misra-pipeline CLI 完全替代方案设计

**日期**: 2026-04-27
**状态**: Draft

## 1. 目标

将 `.agents/tools/pipeline_cli.py` 的所有功能移植到 `cli/misra-pipeline-cli.py`，使其成为**单一统一入口**，废弃 `pipeline_cli.py`。

## 2. 当前架构

```
.agents/tools/pipeline_cli.py  (调度入口)
    │
    ├── split → split_cppcheck_xml.py
    ├── run → run_fix_pipeline.py
    ├── merge → merge_results.py
    ├── verify → verify_chunk.py
    ├── bootstrap → bootstrap_agents.py
    ├── doctor → doctor.py
    ├── validate-real → validate_real.py
    ├── oneshot → oneshot.py
    └── policy → policy_init.py
```

## 3. 目标架构

```
cli/misra-pipeline-cli.py  (统一入口)
    │
    ├── init        (新增：初始化 .agents/)
    ├── upgrade     (新增：升级 .agents/)
    ├── version     (新增：显示版本)
    ├── doctor      (移植：环境诊断 + Provider 检查)
    ├── split       (移植：拆分 cppcheck.xml)
    ├── run         (移植：执行 agent pipeline)
    ├── merge       (移植：合并结果生成报告)
    ├── verify      (移植：验证单个 chunk)
    ├── bootstrap   (移植：生成兼容层)
    ├── validate    (移植：Provider 验收)
    ├── oneshot     (移植：一键执行 split→run→merge)
    └── policy      (移植：策略管理 init/list/test/add)

.agents/tools/*.py  (保留：核心实现模块)
    │
    ├── split_cppcheck_xml.py
    ├── run_fix_pipeline.py
    ├── merge_results.py
    ├── verify_chunk.py
    ├── bootstrap_agents.py
    ├── doctor.py
    ├── validate_real.py
    ├── oneshot.py
    └── policy_init.py
```

**关键决策：**
- CLI 入口统一到 `misra-pipeline-cli.py`
- 核心实现模块保留在 `.agents/tools/`（代码复用）
- CLI 通过 importlib 调用模块（与现有 pipeline_cli.py 相同模式）
- 废弃 `.agents/tools/pipeline_cli.py`

## 4. 命令对比

| 命令 | pipeline_cli.py | misra-pipeline-cli.py | 变化 |
|------|-----------------|----------------------|------|
| `init` | 无 | ✅ 新增 | 初始化 .agents/ |
| `upgrade` | 无 | ✅ 新增 | 升级 .agents/ |
| `version` | 无 | ✅ 新增 | 显示版本 |
| `doctor` | ✅ | ✅ 移植 | 合并现有 doctor.py |
| `split` | ✅ | ✅ 移植 | 无变化 |
| `run` | ✅ | ✅ 移植 | 无变化 |
| `merge` | ✅ | ✅ 移植 | 无变化 |
| `verify` | ✅ | ✅ 移植 | 无变化 |
| `bootstrap` | ✅ | ✅ 移植 | 无变化 |
| `validate-real` | ✅ | → `validate` | 命令名简化 |
| `oneshot` | ✅ | ✅ 移植 | 无变化 |
| `policy` | ✅ | ✅ 移植 | 子命令 init/list/test/add |

## 5. 全局选项

| 选项 | 说明 |
|------|------|
| `--provider {codex,claude,opencode,kimi}` | 覆盖 pipeline.json 中的 agent provider |
| `--help` | 显示帮助 |
| `--version` | 显示 CLI 版本（与 version 子命令不同） |

**环境变量处理：**
- `--provider` 设置 `PIPELINE_AGENT_PROVIDER` 环境变量
- 子命令执行后恢复原环境变量状态

## 6. doctor 命令合并

现有两个 doctor 实现：

| 来源 | 检查项 |
|------|--------|
| `misra-pipeline doctor` | Python 版本、CLI 安装、Git、.agents 目录 |
| `pipeline_cli.py doctor` | Python 版本、Git、**Provider 认证状态** |

**合并后的 doctor 检查项：**

```
  Python version (>=3.8): OK/FAIL
  Git available: OK/FAIL
  .agents directory: OK/FAIL
  Agent Provider (codex): OK/SKIP/FAIL
  Agent Provider (claude): OK/SKIP/FAIL
  Agent Provider (opencode): OK/SKIP/FAIL
  Agent Provider (kimi): OK/SKIP/FAIL
```

**Provider 检查逻辑（移植 doctor.py）：**
- 检查可执行文件是否存在
- 检查认证状态（codex: ~/.codex/auth.json, claude: ANTHROPIC_API_KEY, etc.）
- SKIP：可执行文件不存在
- FAIL：可执行文件存在但认证缺失
- OK：可执行文件存在且认证有效

**输出格式：**
- `--format text`：人类可读（默认）
- `--format json`：JSON 数组（便于脚本消费）

## 7. 子命令详细设计

### 7.1 split

```bash
misra-pipeline split [--strategy {all_auto,conservative}] [--run-id RUN_ID]
```

调用 `split_cppcheck_xml.py`，拆分 cppcheck.xml 为 chunks。

### 7.2 run

```bash
misra-pipeline run [--max-chunks N] [--retry-failed N] [--rule-id RULE] [--misra-only] [--include-failed] [--strategy MODE] [--verbose]
```

调用 `run_fix_pipeline.py`，执行 agent pipeline。

### 7.3 merge

```bash
misra-pipeline merge
```

调用 `merge_results.py`，合并结果生成报告和归档。

### 7.4 verify

```bash
misra-pipeline verify <chunk_index>
```

调用 `verify_chunk.py`，验证单个 chunk 结果。

### 7.5 bootstrap

```bash
misra-pipeline bootstrap [--mode {merge,overwrite}] [--dry-run]
```

调用 `bootstrap_agents.py`，生成兼容层文件。

### 7.6 validate

```bash
misra-pipeline validate [--provider {codex,claude,opencode,kimi,all}] [--report PATH] [--keep-workdir] [--run-id RUN_ID]
```

调用 `validate_real.py`，执行真实 Provider 验收。

（命令名从 `validate-real` 简化为 `validate`）

### 7.7 oneshot

```bash
misra-pipeline oneshot [--fresh] [--resume] [--strategy MODE] [--run-id RUN_ID] [--max-chunks N] [--retry-failed N] [--rule-id RULE] [--misra-only] [--include-failed] [--dry-run] [--status]
```

调用 `oneshot.py`，一键执行 split→run→merge。

### 7.8 policy

```bash
misra-pipeline policy init [--template TEMPLATE] [--template TEMPLATE] [--policy-file PATH]
misra-pipeline policy list [--templates] [--rules] [--pattern PATTERN]
misra-pipeline policy test <rule_id>
misra-pipeline policy add <rule_id> [--action {auto_fix,careful_fix,needs_manual_review}] [--risk-level {high,medium,low}]
```

调用 `policy_init.py`，策略管理。

### 7.9 doctor

```bash
misra-pipeline doctor [--format {text,json}]
```

合并现有两个 doctor 实现。

### 7.10 init（已有）

```bash
misra-pipeline init [--force] [--version vX.Y.Z]
```

初始化 .agents/ 目录。

### 7.11 upgrade（已有）

```bash
misra-pipeline upgrade [--version vX.Y.Z]
```

升级 .agents/ 目录。

### 7.12 version（已有）

```bash
misra-pipeline version
```

显示 CLI 和项目版本。

## 8. 代码结构

**cli/misra-pipeline-cli.py 结构：**

```python
#!/usr/bin/env python3
"""MISRA Pipeline CLI - Unified entry point for cppcheck/MISRA agent pipeline.

Commands:
  init        Initialize .agents/ directory
  upgrade     Upgrade .agents/ to latest version
  version     Show CLI and project version
  doctor      Check environment and provider status
  split       Split cppcheck.xml into chunks
  run         Run agent fixing pipeline
  merge       Merge results into reports
  verify      Verify one chunk result
  bootstrap   Generate compatibility files
  validate    Validate provider with real execution
  oneshot     One-shot split→run→merge
  policy      Manage policy configuration
"""

# ... imports ...

# Constants
REPO_URL = "https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
MIN_PYTHON = (3, 8)

# Command modules mapping (移植 pipeline_cli.py 的 COMMANDS)
COMMAND_MODULES = {
    "split": "split_cppcheck_xml",
    "run": "run_fix_pipeline",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "validate": "validate_real",
    "oneshot": "oneshot",
    "policy": "policy_init",
}

def parse_args():
    parser = argparse.ArgumentParser(...)
    parser.add_argument("--provider", choices=[...])

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # init/upgrade/version/doctor (内置实现)
    # split/run/merge/verify/bootstrap/validate/oneshot/policy (调用模块)

    return parser.parse_args()

def main():
    args = parse_args()

    # Handle --provider env var
    # ...

    if args.subcommand in COMMAND_MODULES:
        # 调用模块（与 pipeline_cli.py 相同模式）
        module = importlib.import_module(COMMAND_MODULES[args.subcommand])
        sys.argv = [module.__name__, *args.args]
        return module.main()
    elif args.subcommand == "init":
        return cmd_init(args)
    elif args.subcommand == "upgrade":
        return cmd_upgrade(args)
    elif args.subcommand == "version":
        return cmd_version(args)
    elif args.subcommand == "doctor":
        return cmd_doctor(args)
```

## 9. doctor 实现合并

**合并策略：**

1. 保留 `misra-pipeline-cli.py` 中的基础检查（Python/Git/.agents）
2. 调用 `doctor.py` 模块进行 Provider 检查
3. 合并输出

```python
def cmd_doctor(args):
    # 1. 基础检查（内置）
    basic_checks = [
        ("Python version (>=3.8)", check_python_version()),
        ("Git available", check_git_available()),
        (".agents directory", check_project_initialized()),
    ]

    # 2. Provider 检查（调用 doctor.py）
    import doctor
    provider_checks = doctor.check_all_providers()

    # 3. 合并输出
    all_checks = basic_checks + provider_checks

    if args.format == "json":
        print(json.dumps(all_checks))
    else:
        for name, status in all_checks:
            print(f"  {name}: {status}")
```

## 10. 废弃 pipeline_cli.py

**废弃步骤：**

1. 移植完成后，在 `.agents/tools/pipeline_cli.py` 顶部添加废弃警告：
   ```python
   print("Warning: pipeline_cli.py is deprecated. Use 'misra-pipeline' instead.", file=sys.stderr)
   ```

2. 更新 README，移除 pipeline_cli.py 相关文档

3. 更新兼容层（AGENTS.md, SKILL.md），使用 `misra-pipeline` 命令

4. 保留 pipeline_cli.py 文件（向后兼容），但标记废弃

## 11. 测试策略

| 测试项 | 方法 |
|--------|------|
| 所有子命令参数解析 | 单元测试 parse_args |
| init/upgrade/version/doctor | 单元测试（已有） |
| split/run/merge/verify/bootstrap/validate/oneshot/policy | 调用模块测试（已有） |
| --provider 环境变量处理 | 单元测试 |
| doctor Provider 检查 | 单元测试（移植 doctor.py 测试） |

## 12. 文件变更清单

| 文件 | 操作 |
|------|------|
| `cli/misra-pipeline-cli.py` | 修改：添加 8 个移植命令 |
| `cli/VERSION` | 修改：升级到 v0.2.0 |
| `.agents/tools/pipeline_cli.py` | 修改：添加废弃警告 |
| `.agents/tools/doctor.py` | 修改：导出 check_all_providers 函数 |
| `tests/test_misra_pipeline_cli.py` | 修改：添加移植命令测试 |
| `README.md` | 修改：统一使用 misra-pipeline 命令 |
| `.agents/compat/AGENTS.md` | 修改：更新命令引用 |
| `.codex/skills/cppcheck-misra-fix/SKILL.md` | 修改：更新命令引用 |
| `.claude/skills/cppcheck-misra-fix/SKILL.md` | 修改：更新命令引用 |

## 13. 版本规划

| 版本 | 内容 |
|------|------|
| v0.1.0 | init/upgrade/version/doctor（已完成） |
| v0.2.0 | 移植 split/run/merge/verify/bootstrap/validate/oneshot/policy |

## 14. 兼容性

| 场景 | 处理 |
|------|------|
| 用户已有 `pipeline_cli.py` 脚本 | 废弃警告，建议迁移 |
| Agent 兼容层调用 pipeline_cli.py | 更新为 misra-pipeline |
| 远程 init 安装 | 使用 install.sh/install.bat 安装 CLI |

## 15. 实现优先级

| 优先级 | 任务 |
|--------|------|
| P0 | 合并 doctor（Provider 检查） |
| P1 | 移植 split/run/merge |
| P1 | 移植 oneshot |
| P2 | 移植 verify/bootstrap/validate |
| P2 | 移植 policy |
| P3 | 废弃警告 + 文档更新 |