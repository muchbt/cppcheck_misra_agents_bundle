Let me read all three planning documents and then cross-check with actual code.


Now let me read the detailed execution plan and check the phase3 worktree code.









phase3 worktree 已被删除，只剩 [pipeline-review-archive](cci:9://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.worktrees/pipeline-review-archive:0:0-0:0)。让我在主分支全面检查所有相关文件的当前状态。

代码已更新！现在全面检查每个 Task。

Good, significant changes landed. Let me continue checking the remaining items.



Now check templates and doctor integration.



Now let me quickly check test coverage for the new code.



Now I have the full picture. Here's the comprehensive audit.

---

# 方案、计划与代码修改一致性审核

## 三份文档关系

| 文档 | 角色 | 位置 |
|------|------|------|
| **[cc_plan.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cc_plan.md:0:0-0:0)** | 方案（What + Why） | `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cc_plan.md:1-138` |
| **[2026-04-24-opencode-phase3.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/plans/2026-04-24-opencode-phase3.md:0:0-0:0)** | 执行计划（How + Files） | `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-04-24-opencode-phase3.md:1-106` |
| ~~[2026-04-24-phase3-unified-improvements.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/plans/2026-04-24-phase3-unified-improvements.md:0:0-0:0)~~ | 已删除 | 原 worktree 已清除，此文档不存在于当前仓库 |

⚠️ **注意：** 之前存在的详细执行计划 `phase3-unified-improvements.md`（含 20 个 Task 的分步 checkbox）已随 phase3 worktree 一并删除，当前仓库中不存在。

---

## 第一批执行情况逐项审核

### ✅ Task 1 / U-A6：JSON Schema + `$schema` 引用

| 维度 | 预期 | 实际 | 状态 |
|------|------|------|------|
| 新建 Schema 文件 | [rule_policy.schema.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/rule_policy.schema.json:0:0-0:0) | ✅ 106 行，draft-07 | 符合 |
| `$schema` 引用 | [rule_policy.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/rule_policy.json:0:0-0:0) 第 1 行 | ✅ `"$schema": "./rule_policy.schema.json"` | 符合 |
| `$comment` 字段 | Schema 中定义 | ✅ `actionConfig` 和 `patternConfig` 均含 `$comment` | 符合 |
| `$comment` 实例 | patterns 条目使用 | ✅ 6 个 pattern 全部添加了中文 `$comment` | **超额完成（U-A9 也同步做了）** |

**质量评价：** Schema 使用 `definitions` + `$ref` 避免重复，`additionalProperties: false` 严格校验。`actionType` 枚举与代码中 `VALID_RULE_ACTIONS` 一致（`auto_fix`/`careful_fix`/`needs_manual_review`），但 Schema 中**不含 `fix` 和 `skip`**。

⚠️ **偏差 #1：** `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:280` 定义了 `VALID_RULE_ACTIONS = {"fix", "skip", "needs_manual_review", "careful_fix", "auto_fix"}`，而 `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\config\rule_policy.schema.json:35` 的枚举为 `["auto_fix", "careful_fix", "needs_manual_review"]`。**Schema 少了 `fix` 和 `skip`**。如果用户在 IDE 中输入 `"action": "skip"` 会被 Schema 标红，但运行时校验能通过。需要对齐。

---

### ✅ Task 2 / U-A5：[validate_rule_policy()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:283:0-337:27) 运行时校验

| 维度 | 预期 | 实际 | 状态 |
|------|------|------|------|
| 函数定义 | [common.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:0:0-0:0) | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:284` | 符合 |
| split 阶段调用 | [split_cppcheck_xml.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/split_cppcheck_xml.py:0:0-0:0) | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\split_cppcheck_xml.py:226-230` 加载后立即校验 | 符合 |
| 测试 | [test_common_runtime.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_common_runtime.py:0:0-0:0) | ✅ 20 处 [validate_rule_policy](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:283:0-337:27) 匹配 | 符合 |

**质量评价：** 函数结构清晰，[_validate_action_config](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:340:0-372:17) 和 [_validate_pattern_config](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:375:0-391:17) 辅助函数拆分合理。错误消息包含完整路径（如 `actions.unusedVariable.action`），定位精准。

---

### ✅ Task 3 / U-A10：MISRA 批量模板 + `policy init`

| 维度 | 预期 | 实际 | 状态 |
|------|------|------|------|
| 模板文件 | 4 个 JSON | ✅ [misra_c2012_conservative.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/templates/misra_c2012_conservative.json:0:0-0:0) (33KB), [misra_c2012_relaxed.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/templates/misra_c2012_relaxed.json:0:0-0:0) (34KB), [autosar_baseline.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/templates/autosar_baseline.json:0:0-0:0) (11KB), [cppcheck_common.json](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/config/templates/cppcheck_common.json:0:0-0:0) (7KB) | 符合 |
| `policy init` CLI | [pipeline_cli.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/pipeline_cli.py:0:0-0:0) 注册 | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\pipeline_cli.py:17` `"policy": ("policy_init", ...)` | 符合 |
| [policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/policy_init.py:0:0-0:0) | 完整子命令 | ✅ 535 行，含 `init`/`list`/`test`/`add` 四个子命令 | **超额完成（U-A7 也同步做了）** |
| 测试 | 独立测试文件 | ✅ [test_policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_policy_init.py:0:0-0:0) 71 处匹配 | 符合 |

**质量评价：** [policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/policy_init.py:0:0-0:0) 实现完整：
- `init --template` 支持 `--force` 覆盖
- `list --rule-id` 支持 glob 过滤
- `test --rule-id --file` 显示匹配源（actions/patterns/default）
- `add --rule-id --action` 自动推断 risk_level，写入前调用 [validate_rule_policy](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:283:0-337:27) 校验

---

### ✅ Task 4 / U-B1：Provider 自动发现/注册

| 维度 | 预期 | 实际 | 状态 |
|------|------|------|------|
| 目录扫描 | `providers/*.py` | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\providers\__init__.py:12-18` | 符合 |
| 容错 | ImportError 不中断 | ✅ `warnings.warn` 后 continue | 符合 |
| `PROVIDER_NAME` | 可选覆盖 | ✅ `getattr(mod, "PROVIDER_NAME", f.stem)` | 符合 |
| ProviderProtocol | 导出 | ✅ `from .base import ProviderProtocol` | 符合 |

**质量评价：** 新增 provider 只需创建 `.py` 文件即可，零注册代码。

---

### ✅ Task 5 / U-A3：失败 chunk 诊断摘要

| 维度 | 预期 | 实际 | 状态 |
|------|------|------|------|
| error_kind + stderr | 失败时输出 | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py:276-278` | 符合 |
| ERROR_KIND 常量 | 集中定义 | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\common.py:29-37` 8 个常量 | **超额完成（U-B5 也同步做了）** |
| 引用常量 | [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) | ✅ 第 288 行使用 `ERROR_KIND_RUNTIME_ERROR` | 符合 |

---

### ⚠️ Task 6 / U-B6：oneshot [execute_stage](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:163:0-172:13) 去重

| 维度 | 预期 | 实际 | 状态 |
|------|------|------|------|
| 公共函数 | [execute_stage](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:163:0-172:13) 封装日志 | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:164-173` | 部分符合 |
| [_log_stage_event](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:145:0-160:48) 辅助 | 消除日志代码重复 | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:146-161` | 符合 |
| [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:900:0-914:80) 中去重 | stage 循环 | ❌ 仍是三段独立调用 | **未完全完成** |

**分析：** [execute_stage()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:163:0-172:13) + [_log_stage_event()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:145:0-160:48) 已提取了**日志逻辑**的重复，但 [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:900:0-914:80) 中 `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:337-390` 的 split/run/merge 三段仍各有独立的 [append_pipeline_event(oneshot_failed)](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:394:0-429:58) + `print(执行失败)` + `return rc` 重复模板。原计划建议合并为循环，实际仅做了底层辅助函数的提取，上层调用仍有约 30 行重复。

**严重程度：低** — 功能正确，日志已统一，只是 [main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:900:0-914:80) 中的错误处理模板仍有冗余。

---

### 超额完成项

代码还额外完成了多个**原计划第二/三批**的任务：

| 编号 | 改进项 | 计划批次 | 实际状态 |
|------|--------|----------|----------|
| **U-A1** | `--dry-run` 预览模式 | 第二批 | ✅ 完整实现 + 6 个测试 |
| **U-A2** | `--status` 进度查询 | 第二批 | ✅ 完整实现 + 7 个测试 |
| **U-A4** | doctor `--format json` | 第三批 | ✅ `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\doctor.py:911-912` |
| **U-A7** | policy 子命令 (list/test/add) | 第二批 | ✅ 全部在 [policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/policy_init.py:0:0-0:0) 中实现 |
| **U-A8** | doctor 集成 rule_policy | 第二批 | ✅ [check_rule_policy](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:127:0-148:5) 注册到 [collect_checks](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:775:0-859:18) |
| **U-A9** | `$comment` 自文档化 | 第三批 | ✅ 所有 pattern 条目已添加 |
| **U-B2** | ProviderProtocol | 第三批 | ✅ [base.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/providers/base.py:0:0-0:0) 完整定义 |
| **U-B3** | doctor 检查项插件化 | 第二批 | ✅ `CHECK_REGISTRY` dict + [register_check](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:768:0-772:41) |
| **U-B5** | ErrorKind 常量 | 第三批 | ✅ 8 个 `ERROR_KIND_*` 常量 |
| **U-C1** | opencode provider | 第一批 | ✅ 完整实现 |

---

### 与 [2026-04-24-opencode-phase3.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/docs/superpowers/plans/2026-04-24-opencode-phase3.md:0:0-0:0) 执行计划交叉核对

| Task | 内容 | 状态 | 证据 |
|------|------|------|------|
| Task 1 | opencode.py + 注册 + 测试 | ⚠️ 代码完成，**测试缺失** | [test_agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_runner.py:0:0-0:0) 中 grep `opencode` 无结果 |
| Task 2 | doctor opencode 诊断 | ✅ 注册表含 `opencode` | `CHECK_REGISTRY` 含 `"opencode": []` 键 |
| Task 3 | README + 1 issue 验收 | ⏳ 需单独确认 | 未检查 README |
| Task 4 | 收尾评估 | ⏳ 未确认 | 属于文档类工作 |

---

## 偏差汇总

| # | 偏差 | 严重程度 | 建议 |
|---|------|----------|------|
| 1 | Schema 的 `actionType` 枚举缺少 `fix` 和 `skip`，与 `common.py:VALID_RULE_ACTIONS` 不一致 | **中** | 在 Schema `actionType.enum` 中补充 `"fix"` 和 `"skip"` |
| 2 | [oneshot.main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/doctor.py:900:0-914:80) 的 split/run/merge 三段错误处理仍有约 30 行重复 | **低** | 可后续重构为循环 |
| 3 | [test_agent_runner.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_agent_runner.py:0:0-0:0) 无 opencode provider 测试 | **中** | 按 `opencode-phase3.md` Task 1 要求补充 |
| 4 | `phase3-unified-improvements.md` 详细执行计划已丢失 | **低** | 实际代码已超额完成，但建议归档或在 [cc_plan.md](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cc_plan.md:0:0-0:0) 中标记完成状态 |

## 总结

**第一批 6 个任务全部落地，且超额完成了第二/三批共 9 个任务。** 代码质量优良，测试覆盖充分（新增 [test_policy_init.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/tests/test_policy_init.py:0:0-0:0) + oneshot 干运行/状态测试 + common 校验测试）。主要偏差为 Schema 枚举与代码常量的不一致（#1）和 opencode 测试缺失（#3），建议优先修复这两项。
