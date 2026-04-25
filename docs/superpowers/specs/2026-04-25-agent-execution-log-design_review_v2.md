
Now let me cross-reference with the current codebase to verify feasibility and accuracy.







Now let me check the current [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) more fully around the failure handling:

Now let me check [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/codex.py:38:0-44:35) signatures across all providers:

Now I have the full picture.

---

# `agent-execution-log-design.md` 审查

## 文档结构评价

设计文档结构清晰、目标明确、实现范围适度。以下逐项交叉验证。

---

## ✅ 准确的诊断

### 问题 1：stderr 为空导致错误信息丢失

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py:277-278
                stderr_preview = (result.get("stderr") or "")[:200]
                print(f"[run] Chunk {idx} 失败: {result.get('error_kind', 'unknown')} - {stderr_preview}")
```

**确认：** 当前只取 `stderr[:200]`。如果三个 provider 的输出都在 stdout，这一行将显示空字符串。设计文档诊断完全正确。✅

### 问题 2：[classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 只分析 stderr

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\agent_runner.py:117-119
        classify_fn = getattr(provider, "classify_runtime_error", None)
        if callable(classify_fn):
            error_kind = classify_fn(completed.stderr)
```

**确认：** 只传了 `completed.stderr`。三个 provider 的签名均为 [classify_runtime_error(stderr: str)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35)，没有 stdout 参数。✅

---

## 设计方案逐项审查

### 1. 日志文件位置 `.agents/runtime/logs/chunk_XXX.log`

**可行性：** 
- 当前 [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) 无 `LOGS_DIR` 常量，需新增。计划已明确写在实现范围表。✅
- 目录初始化：当前路径创建逻辑在 `common.py:93-105` 遍历固定列表 `mkdir`，需追加 `RUNTIME_DIR / "logs"`。✅

**归档兼容：**

```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:449-467
    if runtime_dir.exists():
        for path in runtime_dir.iterdir():
            if path.is_file() and path.suffix == ".json":
                shutil.copy2(path, runtime_archive / path.name)
        for name in ("chunks", "results"):
            ...
        for name in ("pipeline.log", "run_log.jsonl"):
            src = runtime_dir / name
            if src.exists():
                shutil.copy2(src, logs_archive / name)
```

**问题：** 当前归档只复制 `chunks`、`results` 子目录和 `pipeline.log`、`run_log.jsonl` 两个文件。**`logs/` 子目录不会被归档。** 设计文档第 32 行提到"修改 [copy_current_run_archive](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:440:0-474:35) 确保归档 `runtime/logs/` 目录内容"。✅ 方向正确。

⚠️ **建议补充具体做法：** 在 `for name in ("chunks", "results"):` 循环中追加 `"logs"`，即改为 `("chunks", "results", "logs")`。这是最小改动。

### 2. [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 签名扩展

设计方案：[classify_runtime_error(stderr, stdout="")](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) — 向后兼容。

**交叉验证：**

- [ProviderProtocol](cci:2://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:13:0-44:11) 在 `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\providers\base.py:39` 定义了 [classify_runtime_error(self, stderr: str) -> str](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35)。Protocol 也需同步更新。
- 三个 provider 的实现签名均为 [classify_runtime_error(stderr: str)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35)。
- 调用方在 `agent_runner.py:119`。

**向后兼容性分析：** `stdout=""` 作为默认参数，旧签名调用方仍可只传 stderr。但如果有外部代码只用关键字参数调用则不影响。✅ 方案可行。

⚠️ **遗漏：** 设计文档未提到 [base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) 的 [ProviderProtocol](cci:2://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:13:0-44:11) 需要同步修改签名。建议在实现范围表补充 [providers/base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0)。

### 3. 失败摘要输出

设计方案第 98-107 行的摘要提取逻辑：

- 从 stdout 末尾 50 行搜索 → **合理**，避免扫描大量正常输出
- 关键词按 provider 分组 → **合理**，但需要知道当前 provider 名称
- 显示前 3 条关键错误行 → **合理**
- 兜底显示 stdout 末尾 200 字符 → **合理**

⚠️ **实现注意点：** 摘要提取需要在 [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 中拿到 provider 名称。当前 [run_chunk_agent()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/agent_runner.py:46:0-129:5) 返回的 result dict 不含 provider 名称。需要额外从 config 中读取，或在 result dict 中追加。

### 4. `--verbose` 降级为执行后全量输出

**合理决策。** 当前 `subprocess.run(capture_output=True)` 收集完整 stdout/stderr，实时流式需要改为 `Popen` + 实时读取，工程量大。降级方案符合"不做"清单中的承诺。✅

⚠️ **遗漏：** `run_fix_pipeline.py:parse_args` 当前无 `--verbose` 参数。设计方案的实现范围表提到要加，但**重试场景下 verbose 输出会重复多次**——建议在重试段落中明确 verbose 是否每次尝试都输出还是只输出最后一次。

### 5. 重试场景日志策略

追加模式 + 分隔标记。✅ 合理。

当前重试逻辑在 `run_fix_pipeline.py:221-279` 的 `for attempt in range(1, max_attempts+1)` 循环中。日志追加可在每次 [run_chunk_agent](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/agent_runner.py:46:0-129:5) 返回后执行。✅

---

## 实现范围表审查

| 文件 | 改动 | 审查结果 |
|------|------|---------|
| [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) | 日志写入、失败摘要、--verbose | ✅ 方向正确 |
| [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) | classify 调用改为传入 stdout | ✅ 一处改动 |
| `providers/*.py` | classify 签名扩展 | ⚠️ 需明确包含 [base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) Protocol |
| [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) | LOGS_DIR、mkdir、归档 | ⚠️ 需明确归档改法 |

---

## 未提及但需要关注的点

| # | 内容 | 说明 |
|---|------|------|
| 1 | **[providers/base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) ProviderProtocol** | 需同步更新 [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/gap-closure/.agents/tools/providers/opencode.py:23:0-37:35) 签名 |
| 2 | **[copy_current_run_archive](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:440:0-474:35) 具体改法** | 建议在 `("chunks", "results")` 中追加 `"logs"` |
| 3 | **摘要提取需要 provider 名称** | [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 需从 config 获取 provider 以选择关键词 |
| 4 | **verbose + 重试场景** | 是否每次尝试都全量输出？建议只输出最后一次 |
| 5 | **测试覆盖** | 设计文档未提及测试计划（应覆盖：日志文件生成、摘要提取、classify 新签名、归档包含 logs） |
| 6 | **[reset_runtime_logs](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:434:0-438:25)** | `common.py:435` 当前只清理 `pipeline.log` + `run_log.jsonl`，新增 logs 目录后可能也需要清理 |

---

## 总结

设计方案 **诊断准确、方向正确、改动范围适度**。核心设计决策（日志文件独立、classify 签名扩展、--verbose 降级）都合理。

**需要补充的 3 个关键点：**
1. [providers/base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) ProviderProtocol 签名同步
2. [copy_current_run_archive](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:440:0-474:35) 归档 `logs/` 子目录的具体做法
3. 测试计划（至少覆盖日志写入、摘要提取、classify 新签名）
