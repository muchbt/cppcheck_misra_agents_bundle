
Now let me check the current state of the relevant files to cross-reference.

Now let me verify the error classification logic to confirm the design's claim about stderr being empty.

Now I have the full context. Here's the review.

---

# 设计审核：[2026-04-25-agent-execution-log-design.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/specs/2026-04-25-agent-execution-log-design.md:0:0-0:0)

## 设计文档定位

`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\specs\2026-04-25-agent-execution-log-design.md:1-90`

这是一个轻量级设计方案，针对 agent chunk 执行失败时用户无法看到有效错误信息的问题。

---

## 问题诊断 ✅ 准确

设计文档指出的核心问题确实存在于 `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py:277-278`：

```python
stderr_preview = (result.get("stderr") or "")[:200]
print(f"[run] Chunk {idx} 失败: {result.get('error_kind', 'unknown')} - {stderr_preview}")
```

**两层盲区叠加：**

1. **只取 stderr** — 三个 provider（codex/claude/opencode）的关键输出实际在 stdout
2. **仅 200 字符** — 即使 stderr 有内容也可能截断关键信息

同时，`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\agent_runner.py:119` 的 [classify_runtime_error(completed.stderr)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 也**只分析 stderr**，这意味着对三个 provider 来说，错误分类几乎永远返回 `runtime_error` 的兜底值。

⚠️ **设计文档遗漏了这个上游问题** — [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 也应同时分析 stdout，否则即使日志写全了，error_kind 分类仍不准确。虽然文档声明"不改变 error_kind 分类逻辑"，但这个决策值得重新考虑。

---

## 方案评价

### 日志文件位置

```
.agents/runtime/logs/chunk_XXX.log
```

| 维度 | 评价 |
|------|------|
| 命名对齐 | ✅ 与 `chunk_XXX_result.json` 一致 |
| 目录选择 | ✅ 在 [runtime/](cci:9://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/runtime:0:0-0:0) 下，不污染 [reports/](cci:9://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/reports:0:0-0:0) |
| 归档兼容 | ⚠️ 需确认 [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) 的 `copy_current_run_archive` 能否自动归档 `logs/` 子目录 |

`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:441-467` 的归档逻辑 `copy_current_run_archive` 已有 `logs_archive` 目录，但它只复制 `pipeline.log` 和 `run_log.jsonl`，**不会自动复制 `runtime/logs/chunk_XXX.log`**。实现时需确保归档覆盖。

### 日志格式 ✅ 合理

纯文本格式、结构清晰、包含时间戳/provider/命令/返回码。适合人工排查。

**建议补充：**
- `prompt` 长度或摘要（便于确认输入是否正常）
- `cwd` 路径（便于确认工作目录）
- `staging_dir` 路径（便于定位产出物）

### 失败摘要输出 ✅ 方向正确，细节需完善

```
[run] 错误摘要: ERROR: You've hit your usage limit. Upgrade to Pro
```

**关键词提取策略的潜在问题：**

| 问题 | 说明 |
|------|------|
| 关键词过泛 | `"failed"` 在正常 cppcheck 输出中常见（如 "check failed for file X"），可能误提取 |
| 缺少 provider 特征词 | codex 的 quota 错误关键词（`"usage limit"`, `"Upgrade to Pro"`）、opencode 的 `"zen/v1/messages"` 应纳入 |
| 未定义搜索范围 | 应优先从 stdout 末尾 N 行搜索，而非全量搜索 |

### `--verbose` 实时输出 ⚠️ 需要架构决策

当前 `agent_runner.py:76-84` 用 `subprocess.run(capture_output=True)` 一次性捕获输出。`--verbose` 需要改为流式读取（`subprocess.Popen` + 逐行读），这与当前架构冲突。

| 选项 | 改动量 | 风险 |
|------|--------|------|
| A: `Popen` + `tee` 式读取 | 中 — 需重构 [run_chunk_agent](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:47:0-130:5) | 可能影响 prompt stdin 管道 |
| B: 执行后全量打印 | 小 — 不改 subprocess 调用 | 不是真正的"实时"，但满足调试需求 |
| C: 仅输出到日志文件，`tail -f` 提示 | 最小 | 用户需额外开终端 |

**建议方案 B**：chunk 完成后立即输出全量 stdout/stderr，标注为 `--verbose`。实现最简，且已有 `result["stdout"]` / `result["stderr"]` 数据。

---

## 实现范围评价

| 文件 | 计划改动 | 审核意见 |
|------|----------|----------|
| [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) | 添加日志写入 | ⚠️ 日志写入应在 [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 而非 [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0)。[agent_runner.run_chunk_agent](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:47:0-130:5) 是纯函数（输入 config/chunk → 输出 result dict），让它负责 I/O 会破坏职责边界。[run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 拿到 result 后再写日志更干净 |
| [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) | 改进失败摘要 | ✅ 正确位置 |
| [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) | 日志目录常量 | ✅ 合理 |

---

## 与现有代码的交互问题

### 1. [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 只分析 stderr

`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\agent_runner.py:117-119`：

```python
if callable(classify_fn):
    error_kind = classify_fn(completed.stderr)
```

三个 provider 的 [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 均只接收 stderr。如果 stderr 为空，分类永远是 `runtime_error`。**日志改进解决了可见性问题，但分类不准确的根因未修**。

**建议：** 将 [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 改为 [classify_runtime_error(stderr, stdout="")](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) — 向后兼容且仅需修改调用方一行。

### 2. [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 的失败输出逻辑

当前第 276-278 行在每次重试失败时都打印。如果改为同时写日志 + 摘要输出，需注意：
- 重试场景下日志是覆盖还是追加？建议追加，用 `--- ATTEMPT 1 ---` 分隔
- 最终失败报告应显示最后一次尝试的摘要

### 3. `ensure_runtime_dirs` 需补充

[common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) 的 `ensure_runtime_dirs` 创建 `runtime/chunks`、`runtime/results` 等目录。需要补 `runtime/logs`。

---

## 问题汇总

| # | 问题 | 严重程度 | 建议 |
|---|------|----------|------|
| 1 | [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 只分析 stderr，三个 provider 关键信息在 stdout | **高** | 扩展签名为 [classify_runtime_error(stderr, stdout="")](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) |
| 2 | 日志写入放在 [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) 破坏纯函数设计 | **中** | 改为在 [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 写日志 |
| 3 | `copy_current_run_archive` 不会归档 `runtime/logs/` | **中** | 实现时确保归档逻辑覆盖 |
| 4 | `--verbose` 实时输出与 `capture_output=True` 冲突 | **中** | 降级为执行后全量输出（方案 B）|
| 5 | 失败摘要关键词 `"failed"` 过泛 | **低** | 增加 provider 特征词，限制搜索范围为末尾 50 行 |
| 6 | 重试场景日志策略未定义 | **低** | 追加模式 + attempt 分隔标记 |
| 7 | 日志缺少 prompt/cwd/staging_dir 上下文 | **低** | 补充元数据 |
| 8 | `ensure_runtime_dirs` 需补 `logs/` | **低** | 实现时同步修改 |

## 结论

**设计方向正确，精准命中了"stderr 为空导致排障盲区"这个核心痛点。** 方案简洁、改动面小、与现有结构兼容。

**需要调整的核心点：**
1. **日志写入职责**应从 [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) 移到 [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0)
2. **强烈建议顺带修复 [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 只分析 stderr 的问题**，否则 error_kind 分类在三个 provider 上始终是 `runtime_error` 兜底值，日志改进的价值打折扣
3. `--verbose` 降级为执行后全量输出，避免重构 subprocess 调用
