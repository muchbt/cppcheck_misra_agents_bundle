# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目简述

一个纯 Python 3.8+ 跨平台（Windows/Linux）的 cppcheck + MISRA agent 修复管线。解析 `cppcheck.xml` → 按文件聚类切 chunk → 调用本地 agent CLI (codex/claude/opencode/kimi) 自动修复 → 生成中文报告并归档。

## 常用命令

```bash
# 运行所有测试
python3 -m pytest tests/ -v --tb=short

# 运行单个测试文件
python3 -m pytest tests/test_common.py -v

# 运行单个测试函数
python3 -m pytest tests/test_common.py::test_reset_runtime_logs_clears_logs_dir -v

# 运行全部诊断检查
python3 .agents/tools/pipeline_cli.py doctor

# 一键执行完整管线 (split → run → merge)
python3 .agents/tools/pipeline_cli.py oneshot

# 从模板初始化策略配置
python3 .agents/tools/pipeline_cli.py policy init misra_c2012_relaxed

# 构建 Release 归档 (先运行测试再打包)
make release

# 仅构建，跳过测试
make release -B  # 或手动运行 tar 命令
```

## 架构总览

### 两个入口点（职责不同）

| 入口 | 文件 | 用途 |
|------|------|------|
| 分发 CLI | `cli/misra-pipeline-cli.py` | 用户安装/升级/版本管理；从 Release 下载 `.agents/` 到项目目录 |
| 管线 CLI | `.agents/tools/pipeline_cli.py` | 解析 cppcheck.xml、执行 agent 管线、生成报告 |

管线 CLI 通过 `importlib.import_module` 动态加载子命令模块。`--provider` 参数通过环境变量 `PIPELINE_AGENT_PROVIDER` 传递给子进程（try 中设置，finally 中恢复，见 `common.py` 中 `get_selected_agent_provider_name` 的优先级检查）。

### 管线阶段（3 个核心步骤 + 工具命令）

1. **split** (`split_cppcheck_xml.py`)：解析 XML → 按 `rule_policy.json` 分类每个 issue 的 action/risk_level → 按 chunk 策略分组（高风险独占 chunk，其余按文件聚集）→ 输出 `runtime/chunks/`, `issues_master.json`, `issue_status.json`, `progress.json`

2. **run** (`run_fix_pipeline.py`)：遍历 chunk → `agent_runner.run_chunk_agent()` 启动 provider CLI → 等待 agent 写 staging 产物 → `import_chunk_staging_artifacts()` 将 delta 合并到权威 runtime 文件 → 支持重试、规则过滤 (`--rule-id`)、`--misra-only`、`--max-chunks` 限制

3. **merge** (`merge_results.py`)：汇总 `issue_status.json` + `file_change_index.json` → 生成 Markdown/JSON 报告 → 复制到 `runs/<run_id>/` 归档

4. **oneshot** (`oneshot.py`)：串联 split → run → merge，支持自动续跑（检测 `progress.json` 中未完成状态）、`--fresh` 强制从头开始、`--dry-run` 预览模式

### Agent Provider 架构

`providers/` 目录下每个 provider 是一个模块，实现 `ProviderProtocol` 契约（见 `providers/base.py`）：

- `PROVIDER_NAME` — 唯一标识符
- `SANITIZED_ENV_KEYS` — 需要在 launch 环境中清除的敏感 key
- `prepare_launch_env(env)` — 启动前设置环境变量
- `classify_runtime_error(stderr, stdout, returncode)` — 将错误分类为 auth/network/runtime 类
- `build_launch_spec(config, chunk)` — 构建 prompt + argv + 环境 + staging 路径

`agent_runner.py` 是 provider 的实际调用者：组装 prompt、调用 subprocess、导入 staging 产物。`providers/__init__.py` 自动发现目录下所有 `*.py` 模块。

### 数据流和关键文件

```
cppcheck.xml
  → split_cppcheck_xml
    → runtime/issues_master.json       # 所有 issue 的完整信息
    → runtime/issue_status.json        # issue_key → {status, edit_ids, verified, ...}
    → runtime/file_change_index.json   # file_path → {edits: [{edit_id, summary, related_issue_keys, ...}]}
    → runtime/progress.json            # {run_id, status, total_chunks, completed_chunks, failed_chunks}
    → runtime/chunks/chunk_XXX.json    # 每个 chunk 的 issues + 元数据
  → run_fix_pipeline
    → agent_runner → subprocess → provider CLI
    → .agents/staging/chunk_XXX/       # agent 写入的 staging 产物（非权威）
      → issue_status_delta.json
      → file_change_delta.json
      → chunk_result.json / chunk_result.md
    → import_chunk_staging_artifacts() # 将 staging delta 合并到 runtime/ 权威文件
    → runtime/results/chunk_XXX_result.{json,md}
    → runtime/logs/chunk_XXX.log
  → merge_results
    → reports/final_summary.{md,json}
    → reports/review_checklist.md
    → reports/run_manifest.json
    → runs/<run_id>/                   # 完整归档副本
```

### 两层策略系统

- **规则策略** (`rule_policy.json`)：定义每条 MISRA/cppcheck 规则在任意模式下的默认动作 (`auto_fix` / `careful_fix` / `needs_manual_review` / `skip`)。通过 `policy init` 从模板 JSON 初始化。
- **修复策略** (`pipeline.json` 中的 `fix_strategy.mode`)：`conservative`（默认，尊重规则策略）或 `all_auto`（将 `needs_manual_review` 降级为 `careful_fix`，但仍标记 `requires_review_after_fix=true`）。

`split_cppcheck_xml.classify_issue()` 是策略融合的核心：先查 `rule_policy.json` 得到基础 action，再根据 `fix_strategy.mode` 调整。

### 关键约定

- **Staging import 支持多种 agent 输出格式**：`common.py` 中 `normalize_file_change_delta()` 和 `normalize_issue_status_delta()` 同时兼容三种格式：数组包装 (`file_changes`/`status_changes`)、单条记录 (`file`/`issue_key` 根字段)、和 flat 对象。格式契约定义在 `.agents/skills/cppcheck-misra-fix/SKILL.md`。
- **Edit ID 生成**：`next_edit_id()` 使用 `{file_path}#{NNN}` 格式，NNN 基于当前文件的已有 edit 数量递增。
- **Issue key 生成**：`build_issue_key()` 使用 `{file_path}:{line}:{rule_id}:{msg_hash}` 格式，msg 取 SHA1 前 8 位。
- **时区**：所有时间戳使用 `timezone(timedelta(hours=8))`（北京时间）。
- **Agent 只写 staging directory**，不直接写 runtime 文件。`import_chunk_staging_artifacts()` 是唯一合并 staging → runtime 的路径。
- **Chunk 策略**：`chunking.split_high_risk_alone=true` 时，每个 `needs_manual_review` issue 独占一个 chunk；其余 issue 按文件分组，每 chunk 最多 12 个 issue、3 个文件。

### 兼容层（bootstrap）

主目录是 `.agents/`。`bootstrap_agents.py` 通过 `replace_or_append_marked_block()` 生成/更新项目根 `AGENTS.md` 和 provider 专用 skill 文件（`.claude/skills/`, `.codex/skills/`），内容用 `<!-- BEGIN/END AUTO-GENERATED -->` 标记。

### 测试

测试文件位于 `tests/`，通过将 `.agents/tools/` 加入 `sys.path` 来导入被测试模块。需要 Python 3.8+ 运行。
