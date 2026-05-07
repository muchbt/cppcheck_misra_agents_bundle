Let me re-read both files to do a precise consistency check.

# 设计 vs 实施计划 一致性分析

## 逐项对比

### 1. Files Overview / 修改范围

| 文件 | 设计 (design.md) | 计划 (plan.md) | 一致？ |
|------|------------------|----------------|--------|
| `providers/kimi.py` | ✅ NEW | ✅ Create | ✅ |
| [providers/base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) | ✅ MODIFY (签名) | ❌ **未列出** | ❌ |
| [providers/codex.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/codex.py:0:0-0:0) | ✅ MODIFY (签名) | ❌ **未列出** | ❌ |
| [providers/claude.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/claude.py:0:0-0:0) | ✅ MODIFY (签名) | ❌ **未列出** | ❌ |
| [providers/opencode.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/opencode.py:0:0-0:0) | ✅ MODIFY (签名) | ❌ **未列出** | ❌ |
| [doctor.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:0:0-0:0) | ✅ MODIFY | ✅ Modify | ✅ |
| [pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:0:0-0:0) | ✅ MODIFY | ✅ Modify | ✅ |
| [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) | ✅ MODIFY (传 returncode) | ❌ **未列出** | ❌ |
| [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) | ✅ MODIFY (PROVIDER_ERROR_KEYWORDS) | ❌ **未列出** | ❌ |
| [pipeline.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/pipeline.json:0:0-0:0) | ✅ MODIFY | ✅ Modify | ✅ |
| [tests/test_agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_runner.py:0:0-0:0) | ✅ MODIFY | ❌ **未列出** | ❌ |
| [tests/test_doctor.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_doctor.py:0:0-0:0) | ✅ MODIFY | ✅ Modify | ✅ |
| [tests/test_pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:0:0-0:0) | ✅ MODIFY | ✅ Modify | ✅ |

**结论：计划缺少 7 个文件的修改**。设计在自审后补全了所有文件，但计划没有同步更新。

---

### 2. [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/opencode.py:23:0-38:35) 签名

| 维度 | 设计 | 计划 | 一致？ |
|------|------|------|--------|
| **签名** | `(stderr, stdout="", returncode: Optional[int]=None)` | `(stderr, stdout="")` | ❌ |
| **kimi.py 实现** | 用 returncode 做 exit code 分级（75→network, 1+auth→auth） | 纯文本匹配 | ❌ |
| **base.py Protocol** | 更新为带 returncode | 不修改 | ❌ |
| **agent_runner.py 调用** | `classify_fn(stderr, stdout, returncode)` | `classify_fn(stderr, stdout)` | ❌ |
| **现有 provider 签名** | 加 `returncode` 参数但不使用 | 不修改 | ❌ |
| **类型标注** | `Optional[int]` + `from typing import Optional` | 无 | ❌ |

**结论：这是最大的不一致。** 设计引入了 returncode 参数作为 kimi 的核心分类机制，计划完全没有这个概念。

---

### 3. [prepare_launch_env](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/claude.py:17:0-18:15)

| 维度 | 设计 | 计划 | 一致？ |
|------|------|------|--------|
| **行为** | 设置 `KIMI_SHARE_DIR` + `KIMI_CLI_NO_AUTO_UPDATE` | `return None`（空操作） | ❌ |
| **import** | 需要 `ROOT`（因为 `KIMI_SHARE_DIR` 用 ROOT 路径） | 有 `from pathlib import Path` 但未使用 | ❌ |
| **workspace 隔离** | ✅ 通过 KIMI_SHARE_DIR 隔离 | ❌ 无隔离 | ❌ |

设计 line 53-57：
```
KIMI_SHARE_DIR → <ROOT>/.agents/runtime/kimi-home
KIMI_CLI_NO_AUTO_UPDATE → "1"
```

计划 line 50-56：
```python
def prepare_launch_env(env: Dict[str, str]) -> None:
    """...No special env preparation needed - kimi handles its own auth."""
    return None
```

**结论：完全矛盾。** 设计要求 workspace 隔离，计划实现为空操作。

---

### 4. [build_launch_spec](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/codex.py:50:0-70:5) guard 逻辑

| 维度 | 设计 | 计划 | 一致？ |
|------|------|------|--------|
| `--input-format text` | ✅ guard 追加 | ✅ guard 追加 | ✅ |
| `--output-format text` | ✅ guard 追加 | ✅ guard 追加 | ✅ |
| `--yolo` | ✅ guard 追加（防御性） | ❌ **未追加** | ❌ |

**结论：计划缺少 `--yolo` guard。**

---

### 5. [pipeline.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/pipeline.json:0:0-0:0) argv

| 维度 | 设计 | 计划 | 一致？ |
|------|------|------|--------|
| **argv** | `["kimi", "--print"]`（最小） | `["kimi", "--print", "--input-format", "text", "--output-format", "text"]`（完整） | ❌ |

设计 line 77 明确写道：
> pipeline.json contains only minimal argv: `["kimi", "--print"]`.

计划 Task 4 (line 296-302) 把 `--input-format text` 和 `--output-format text` 也放进了 argv。

**结论：** 这导致计划中 [build_launch_spec](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/codex.py:50:0-70:5) 的 guard 永远不会触发（检测到已存在就跳过）。设计的意图是 pipeline.json 最小化 + guard 补全，计划两边都加了。

---

### 6. Doctor checks

| 维度 | 设计 | 计划 | 一致？ |
|------|------|------|--------|
| **check_kimi_executable** | ❌ 不需要（common check 已覆盖） | ✅ 有独立实现 | ❌ |
| **check_kimi_auth 检查项** | `KIMI_API_KEY` env → auth file → warning | auth file → config.toml → warning | ❌ |
| **auth 文件路径** | `~/.kimi/credentials/kimi-code.json` | `~/.kimi/kimi-code.json` | ❌ |
| **register_check 数量** | 1 个（只 auth） | 2 个（executable + auth） | ❌ |

详细差异：

**设计** doctor check 流程（line 148-152）：
1. Check `KIMI_API_KEY` env var → ok
2. Check `~/.kimi/credentials/kimi-code.json` → ok
3. Neither → warning

**计划** doctor check 流程（line 187-226）：
1. Check `~/.kimi/kimi-code.json` → ok
2. Check `~/.kimi/config.toml` → warning (config only)
3. Neither → warning

**结论：** 检查逻辑完全不同。设计增加了环境变量检查，改了 auth 文件路径，去掉了 executable 检查和 config.toml 检查。

---

### 7. Tests

| 测试项 | 设计 | 计划 | 一致？ |
|--------|------|------|--------|
| **test_agent_runner.py KimiProviderTests** | ✅ 3 个测试 | ❌ 无 | ❌ |
| **test_doctor.py kimi auth** | 3 个（env_var, credential_file, manual_check） | 3 个（missing_auth, auth_ok, config_only）+ 2 个 executable | ❌ |
| **test_pipeline_cli.py** | 修改现有 [test_parse_args_provider_choices](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_pipeline_cli.py:76:4-79:53) | 新增 3 个独立测试 | ❌ |
| **Path.rmtree bug** | ✅ 用 TemporaryDirectory 修复 | ❌ line 382 仍有 `fake_home.rmtree()` | ❌ |

**结论：** 测试策略完全不同。设计修改现有测试避免冗余，计划新增重复测试。计划的 P1 bug（`Path.rmtree`）在设计中已标注修复但计划代码未更新。

---

### 8. [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) PROVIDER_ERROR_KEYWORDS

| 维度 | 设计 | 计划 | 一致？ |
|------|------|------|--------|
| **kimi 条目** | ✅ 有（line 140） | ❌ 无 | ❌ |
| **关键词** | `["login", "unauthorized", "api_key", "token", "quota", "credit", "rate limit"]` | — | ❌ |

**结论：** 计划完全遗漏了此修改。

---

## 不一致汇总

| # | 类别 | 严重度 | 设计要求 | 计划实现 |
|---|------|--------|----------|----------|
| 1 | **classify_runtime_error 签名** | 🔴 高 | 加 `returncode` 参数 | 无此参数 |
| 2 | **prepare_launch_env** | 🔴 高 | 设置 KIMI_SHARE_DIR + NO_AUTO_UPDATE | 空操作 |
| 3 | **修改范围** | 🔴 高 | 12 个文件 | 6 个文件 |
| 4 | **pipeline.json argv** | 🟡 中 | 最小 `["kimi", "--print"]` | 完整包含 format 参数 |
| 5 | **build_launch_spec --yolo** | 🟡 中 | 有 guard | 无 |
| 6 | **doctor executable check** | 🟡 中 | 不需要（common 覆盖） | 有独立实现 |
| 7 | **doctor auth 检查逻辑** | 🟡 中 | env var → credentials 路径 | auth file → config.toml |
| 8 | **auth 文件路径** | 🟡 中 | `~/.kimi/credentials/kimi-code.json` | `~/.kimi/kimi-code.json` |
| 9 | **PROVIDER_ERROR_KEYWORDS** | 🟡 中 | 有 kimi 条目 | 遗漏 |
| 10 | **test_agent_runner.py** | 🟡 中 | KimiProviderTests 3 个测试 | 无 |
| 11 | **test_pipeline_cli.py 策略** | 🟢 低 | 修改现有测试 | 新增重复测试 |
| 12 | **Path.rmtree bug** | 🟢 低 | 已修复 | 仍存在 |

---

## 结论

**设计和计划严重不一致**，存在 3 个高严重度和 7 个中严重度的差异。根本原因是设计文档是在计划之后编写的，吸收了审核意见并做了重大设计变更（returncode 签名扩展、workspace 隔离、doctor 简化），但**计划没有同步回更新**。

**建议：** 以设计文档为准（它是更新版），重写实施计划使其与设计完全对齐。需要：
1. 新增 Task：修改 [base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) / [codex.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/codex.py:0:0-0:0) / [claude.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/claude.py:0:0-0:0) / [opencode.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/opencode.py:0:0-0:0) / [agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/agent_runner.py:0:0-0:0) 的 [classify_runtime_error](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/opencode.py:23:0-38:35) 签名
2. 新增 Task：修改 [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 的 `PROVIDER_ERROR_KEYWORDS`
3. 重写 Task 1：kimi.py 使用带 returncode 的签名 + 非空 [prepare_launch_env](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/claude.py:17:0-18:15)
4. 重写 Task 2：doctor 只保留 `check_kimi_auth`，使用设计的检查逻辑
5. 重写 Task 4：pipeline.json 用最小 argv
6. 重写 Task 5-6：测试与设计的 Test Plan 对齐
7. 新增 Task：[test_agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_runner.py:0:0-0:0) 的 KimiProviderTests
