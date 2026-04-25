# Agent 执行日志改进设计

## 背景

当前 `run_fix_pipeline.py` 在 chunk 失败时只显示 stderr 的前 200 字符。但实际测试发现：

- **codex**: 所有输出都在 stdout，stderr 为空
- **claude**: 所有输出都在 stdout，stderr 为空
- **opencode**: 所有输出都在 stdout，stderr 为空

导致用户无法看到关键错误信息（如 "You've hit your usage limit. Upgrade to Pro"）。

同时，`agent_runner.py` 的 `classify_runtime_error(completed.stderr)` **只分析 stderr**，对三个 provider 来说分类永远返回 `runtime_error` 兜底值，即使日志可见性改进，`error_kind` 分类仍不准确。

## 目标

让用户能够：
1. 查看 agent 执行的完整 stdout/stderr 输出
2. 失败时获得清晰的错误摘要和准确的 error_kind 分类
3. 知道日志文件位置以排查问题

## 设计方案

### 日志文件位置

```
.agents/runtime/logs/chunk_XXX.log
```

每个 chunk 独立日志文件，与现有 `chunk_XXX_result.json` 结构对齐。

### 日志格式

```
=== CHUNK 001 EXECUTION LOG ===
Started: 2026-04-25T19:30:00+08:00
Provider: codex
Command: codex exec --full-auto --skip-git-repo-check
CWD: /path/to/workspace
Staging: .agents/staging/chunk_001
Prompt length: 1308 characters

--- STDOUT ---
Reading prompt from stdin...
OpenAI Codex v0.124.0 (research preview)
...
ERROR: You've hit your usage limit. Upgrade to Pro

--- STDERR ---
(empty or actual stderr content)

--- END ---
Returncode: 1
Error kind: auth_error
Finished: 2026-04-25T19:30:15+08:00
```

**注：** `Error kind` 字段使用现有 `common.py` 的 ERROR_KIND 常量（如 `auth_error`、`network_error`、`runtime_error`）。classify_runtime_error 扩展后将能正确识别 quota/usage limit 类错误并归类为 `auth_error` 或新增 `quota_error`（实现时决定）。

### 重试场景日志策略

追加模式，用分隔标记区分每次尝试：

```
--- ATTEMPT 1 ---
(attempt 1 output)

--- ATTEMPT 2 ---
(attempt 2 output)
```

最终失败报告显示最后一次尝试的摘要。

### classify_runtime_error 扩展

**签名扩展：** `classify_runtime_error(stderr, stdout="")` — 向后兼容

调用方修改（`agent_runner.py:119`）：
```python
# 原：error_kind = classify_fn(completed.stderr)
error_kind = classify_fn(completed.stderr, completed.stdout)
```

各 provider 实现同步修改，优先从 stdout 分析，stderr 作为补充。识别到 quota/usage limit 类错误时返回 `auth_error` 或新增常量。

**Protocol 同步：** `providers/base.py` 的 `ProviderProtocol` 需同步更新签名定义。

### 失败摘要输出

当 chunk 失败时，终端输出：

```
[run] Chunk 1 失败: auth_error - OpenAI API usage limit reached
[run] 查看完整日志: .agents/runtime/logs/chunk_001.log
[run] 错误摘要: ERROR: You've hit your usage limit. Upgrade to Pro
```

**摘要提取逻辑：**

1. **从 config 获取 provider 名称** 以选择对应关键词
2. **优先从 stdout 末尾 50 行搜索**（而非全量）
3. **关键词按 provider 特征词优先：**
   - codex: `"usage limit"`, `"Upgrade to Pro"`, `"quota"`
   - claude: `"anthropic_api_key"`, `"authentication"`, `"rate limit"`
   - opencode: `"zen/v1/messages"`, `"api key"`, `"credentials"`
   - 通用: `"ERROR:"`, `"FATAL:"`, `"failed to"`
4. **显示前 3 条关键错误行**
5. **兜底：** 无匹配时显示 stdout 末尾 200 字符

### --verbose 输出

降级为**执行后全量输出**（而非实时流式），避免重构 `subprocess.run(capture_output=True)` 调用。

**重试场景：** 只输出最后一次尝试的全量 stdout/stderr（避免重复多次）。

```
python .agents/tools/pipeline_cli.py run --verbose

# chunk 最终完成/失败后输出：
=== CHUNK 001 STDOUT (verbose) ===
(full stdout content from last attempt)

=== CHUNK 001 STDERR (verbose) ===
(full stderr content from last attempt)
```

### 目录初始化与清理

**初始化：** 在 `common.py:93-105` 的 `ensure_dirs()` 函数路径列表中追加 `RUNTIME_DIR / "logs"`：

```python
def ensure_dirs() -> None:
    for path in [
        AGENTS_DIR,
        CONFIG_DIR,
        PROMPTS_DIR,
        SKILLS_DIR,
        RUNTIME_DIR,
        RUNS_DIR,
        CHUNKS_DIR,
        RESULTS_DIR,
        REPORTS_DIR,
        RUNTIME_DIR / "logs",  # 新增
    ]:
        path.mkdir(parents=True, exist_ok=True)
```

**清理：** `reset_runtime_logs` 补充清理 `logs/` 目录，采用 `shutil.rmtree` + 重建方式：

```python
def reset_runtime_logs(runtime_dir: Path = RUNTIME_DIR) -> None:
    for name in ("pipeline.log", "run_log.jsonl"):
        path = runtime_dir / name
        if path.exists():
            path.unlink()
    # 新增：清理 logs 目录
    logs_dir = runtime_dir / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir, ignore_errors=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
```

### 归档逻辑

修改 `copy_current_run_archive`，在归档子目录循环中追加 `"logs"`：

```python
# 原：for name in ("chunks", "results"):
for name in ("chunks", "results", "logs"):
```

这是最小改动，确保 `runtime/logs/` 内容被归档到 `runs/YYYY-MM-DD-HHMMSS/logs/`。

## 实现范围

| 文件 | 改动 |
|------|------|
| `run_fix_pipeline.py` | 日志写入逻辑、失败摘要改进、--verbose 参数、从 config 获取 provider 名称 |
| `agent_runner.py` | classify_runtime_error 调用改为传入 stdout |
| `providers/base.py` | ProviderProtocol 签名同步更新 |
| `providers/codex.py` | classify_runtime_error 签名扩展，分析 stdout，识别 quota 类错误 |
| `providers/claude.py` | classify_runtime_error 签名扩展，分析 stdout |
| `providers/opencode.py` | classify_runtime_error 签名扩展，分析 stdout |
| `common.py` | 添加 LOGS_DIR 常量、ensure_dirs 追加 logs 路径、reset_runtime_logs 补 shutil.rmtree 清理、归档追加 logs |

## 测试计划

| 测试项 | 说明 |
|--------|------|
| 日志文件生成 | 验证 chunk 执行后 logs/chunk_XXX.log 存在且格式正确 |
| 重试日志追加 | 验证多次尝试时日志追加 + ATTEMPT 分隔标记 |
| 摘要提取 | 验证各 provider 关键词匹配 + 兜底逻辑 |
| classify 新签名 | 验证传入 stdout 参数后 error_kind 分类准确 |
| 归档包含 logs | 验证 archive 后 logs/ 子目录存在 |
| verbose 输出 | 验证 --verbose 只输出最后一次尝试 |
| reset 清理 | 验证 reset_runtime_logs 正确清理 logs/ 目录 |

## 不做

- 不改变 staging 目录结构
- 不添加日志轮转/清理机制（后续可扩展）
- 不重构 subprocess 为实时流式（--verbose 降级为执行后输出）