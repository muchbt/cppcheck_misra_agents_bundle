
设计文档又做了更新（从 169 行扩展到 202 行）。下面逐项对照。

---

# 设计方案 vs 实施计划 一致性分析

## 对照矩阵

| 设计方案章节 | 计划 Task | 一致性 | 差异说明 |
|-------------|----------|--------|---------|
| **日志文件位置** `.agents/runtime/logs/chunk_XXX.log` | Task 1 Step 1 (`LOGS_DIR`) + Task 7 (`write_chunk_execution_log`) | ✅ 一致 | — |
| **日志格式** 头部元数据 + STDOUT/STDERR/END 分段 | Task 7 Step 1 代码 | ✅ 一致 | — |
| **重试场景日志策略** 追加模式 + `ATTEMPT N` 分隔 | Task 7 Step 1 `mode = "a" if attempt > 1` | ✅ 一致 | — |
| **classify 签名** [classify_runtime_error(stderr, stdout="")](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/opencode.py:23:0-37:35) | Task 2-6 | ✅ 一致 | — |
| **Protocol 同步** base.py ProviderProtocol | Task 2 | ✅ 一致 | — |
| **codex classify** 新增 quota/usage limit 检测 | Task 3 | ✅ 一致 | — |
| **claude classify** 新增 stdout 分析 | Task 4 | ✅ 一致 | — |
| **opencode classify** 新增 stdout 分析 | Task 5 | ✅ 一致 | — |
| **agent_runner 调用改为传 stdout** | Task 6 | ✅ 一致 | — |
| **失败摘要输出** 3 行格式 + 关键词提取 | Task 8 + Task 9 | ✅ 一致 | — |
| **摘要提取逻辑** provider 关键词 + 通用关键词 + 兜底 | Task 8 `extract_error_summary` | ✅ 一致 | — |
| **--verbose 输出** 执行后全量 + 只输出最后一次尝试 | Task 10 | ✅ 一致 | — |
| **ensure_dirs 追加 logs** | Task 1 Step 2 | ✅ 一致 | — |
| **reset_runtime_logs 补 shutil.rmtree** | Task 1 Step 3 | ✅ 一致 | — |
| **归档 `("chunks", "results", "logs")`** | Task 1 Step 4 | ✅ 一致 | — |
| **测试计划** 7 项 | Task 11（集成测试） + Self-Review Checklist | ⚠️ 见下方 | — |
| **Error kind 示例** 设计文档改为 `auth_error` | Task 3 代码返回 `ERROR_KIND_AUTH_ERROR` | ✅ 一致 | — |

---

## 细节差异

### 1. ✅ 设计文档 `Error kind` 示例已修正

**设计第 54 行：** `Error kind: auth_error`（上版用了 `quota_exceeded`）
**设计第 58 行：** 新增说明"使用现有 ERROR_KIND 常量"，允许"实现时决定"是否新增 `quota_error`。
**计划 Task 3：** 代码中 quota/usage limit 直接返回 `ERROR_KIND_AUTH_ERROR`。

⚠️ **轻微模糊：** 设计第 58 行说"归类为 `auth_error` 或新增 `quota_error`（实现时决定）"，但计划已明确选择了 `auth_error`。建议设计文档也收敛为 `auth_error`，去掉"或新增"的表述，避免实施者犹豫。

### 2. ⚠️ 设计文档测试计划新增第 7 项，计划未对应

**设计第 196 行：** `reset 清理 — 验证 reset_runtime_logs 正确清理 logs/ 目录`

**计划 Task 11：** 只有 validate-real 集成测试，没有 [reset_runtime_logs](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:434:0-438:25) 的单独单元测试。

建议在 Task 1 Step 5 或新增 Task 补一个 [reset_runtime_logs](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:434:0-438:25) 的单元测试断言。

### 3. ⚠️ 设计 [ensure_dirs](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47) 名称精度

**设计第 129 行 + 132 行：** 给出了 [ensure_dirs()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47) 函数的伪代码，含 `RUNTIME_DIR / "logs"` 追加。

**计划 Task 1 Step 2：** 也给出了 [ensure_dirs()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47) 函数代码。

**但：** 当前 [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) 中这段逻辑**不是一个名为 [ensure_dirs()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47) 的函数**，而是模块级裸循环代码：

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:93-105
    for path in [
        ...
        RESULTS_DIR,
        REPORTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)
```

**设计和计划同步引入了函数封装 [ensure_dirs()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47)**，这意味着计划隐含了一个重构——将裸循环提取为函数。两者在这一点上一致，但**都未显式说明这是从裸循环重构为函数**。实施者可能困惑于"修改已有函数"还是"新建函数"。

建议在计划 Task 1 Step 2 的描述中加一句：*"当前为模块级裸循环，提取为 [ensure_dirs()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47) 函数并追加 `LOGS_DIR`"*。

### 4. ⚠️ 计划 Task 7 日志写入逻辑的格式细节

**设计日志格式：**
```
=== CHUNK 001 EXECUTION LOG ===
(头部元数据)
--- STDOUT ---
(content)
--- STDERR ---
(content)
--- END ---
(尾部元数据)
```

**计划 Task 7 代码（第 271-291 行）：**
- attempt > 1 时只写 `--- ATTEMPT N ---` + stdout + `--- STDERR ---` + stderr
- **缺少尾部 `--- END ---` / Returncode / Error kind / Finished**

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-04-25-agent-execution-log.md:272-291
        if attempt > 1:
            f.write(f"\n--- ATTEMPT {attempt} ---\n")
        else:
            f.write(f"=== CHUNK {chunk_index:03d} EXECUTION LOG ===\n")
            ...
            f.write("\n--- STDOUT ---\n")
        f.write(stdout or "(empty)")
        f.write("\n--- STDERR ---\n")
        f.write(stderr or "(empty)")
        if attempt == 1 or mode == "w":
            f.write("\n--- END ---\n")
            f.write(f"Returncode: {returncode}\n")
            f.write(f"Error kind: {error_kind}\n")
            f.write(f"Finished: {finished_at}\n")
```

**问题：**
- `if attempt == 1 or mode == "w"` — 当 attempt > 1 时 mode = "a"，条件为 False，所以 **重试尝试没有尾部元数据（Returncode/Error kind/Finished）**
- 设计文档对重试格式只展示了 `--- ATTEMPT N ---` + output，未明确是否需要尾部。这是**不一致**还是**有意省略**？

**建议：** 每次 attempt 都应写入 Returncode 和 Error kind，否则排查重试失败时无法区分每次失败原因。修改条件为始终写入尾部，或设计文档明确"重试尝试不写尾部"。

### 5. ✅ 计划 Task 9 引用了未定义的函数/变量

**Task 9 第 383 行：**
```python
command_str = " ".join(result.get("prompt", "")[:100] if result.get("prompt") else "")
```

这行有 bug：`" ".join(...)` 的参数是一个字符串（非列表），会按字符拆分。应该是取 `argv` 而非 `prompt`。

**Task 9 第 391 行：**
```python
cwd=str(ROOT),
staging_dir=str(resolve_agent_staging_dir(config) / f"chunk_{idx:03d}"),
```

`ROOT` 和 [resolve_agent_staging_dir](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:55:0-59:58) 未在 Task 9 的 import 中列出。Task 9 Step 1 只添加了 `from common import LOGS_DIR, get_selected_agent_provider_name`。

此外，[get_selected_agent_provider_name](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:66:0-67:67) 在当前 [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) 中**不存在**——存在的是 [get_selected_agent_config](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:70:0-90:17)。需要新增或改名。

### 6. ⚠️ 实现范围表一致性

| 设计文档实现范围 | 计划 File Structure | 一致性 |
|-----------------|-------------------|--------|
| [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) | ✅ 一致 | ✅ |
| [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) | ✅ 一致 | ✅ |
| [providers/base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) | ✅ 一致 | ✅ |
| [providers/codex.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/codex.py:0:0-0:0) | ✅ 一致 | ✅ |
| [providers/claude.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/claude.py:0:0-0:0) | ✅ 一致 | ✅ |
| [providers/opencode.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/opencode.py:0:0-0:0) | ✅ 一致 | ✅ |
| [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) | ✅ 一致 | ✅ |

7 个文件完全对齐。✅

---

## 总结

| 维度 | 评价 |
|------|------|
| **结构对齐** | ✅ 设计 7 个文件 = 计划 7 个文件，11 个 Task 覆盖设计全部章节 |
| **功能对齐** | ✅ 所有核心功能点（日志写入、classify 扩展、摘要提取、verbose、归档、清理）双向匹配 |
| **Self-Review Checklist** | ✅ 计划第 536-551 行 13 项全部可追溯到设计文档 |

**需修复的不一致：**

| # | 问题 | 修在哪 |
|---|------|--------|
| 1 | 重试 attempt 缺少尾部元数据（Returncode/Error kind） | 计划 Task 7 代码 |
| 2 | Task 9 `command_str` 行有 join bug | 计划 Task 9 代码 |
| 3 | Task 9 缺少 `ROOT`、[resolve_agent_staging_dir](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:55:0-59:58) import | 计划 Task 9 代码 |
| 4 | [get_selected_agent_provider_name](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:66:0-67:67) 在 common.py 不存在 | 计划 Task 9 或 Task 1 需新增 |
| 5 | [ensure_dirs()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:92:0-104:47) 是新建函数（从裸循环重构），需显式说明 | 计划 Task 1 Step 2 + 设计 |
| 6 | [reset_runtime_logs](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:434:0-438:25) 单元测试缺失 | 计划需补 |
| 7 | 设计第 58/84 行"或新增 quota_error"与计划选择 `auth_error` 未收敛 | 设计文档 |

**问题 1-4 是代码级 bug，应在实施前修复；5-7 是描述精度问题，优先级较低。**
