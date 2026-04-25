# Phase 3 统一改进计划（合并版）

将两份分析结果合并为一个统一编号体系，并按用户要求提升 **MISRA 规则批量模板** 优先级。

---

## 统一编号与分类

### U-A 易用性改进

| 编号 | 来源 | 改进项 | 工作量 | 说明 |
|------|------|--------|--------|------|
| **U-A1** | review | `oneshot --dry-run` 预览模式 | ~30 行 | split 后打印 chunk 摘要，不启动 agent |
| **U-A2** | review | `oneshot --status` 进度查询 | ~50 行 | 解析 progress.json 输出人类可读摘要 |
| **U-A3** | review | 失败 chunk 诊断摘要 | ~5 行 | 输出 `error_kind` + stderr 前 200 字符 |
| **U-A4** | review | doctor `--format json` | ~20 行 | CI/CD 可消费的结构化输出 |
| **U-A5** | rule_policy | `validate_rule_policy()` 运行时校验 | ~40 行 | 仿 [validate_pipeline_config](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/common.py:114:0-265:27) 模式 |
| **U-A6** | rule_policy | JSON Schema + `$schema` 引用 | ~50 行新文件 | IDE 实时补全+校验，零代码改动 |
| **U-A7** | rule_policy | `pipeline_cli.py policy` 子命令 | ~140 行 | `policy list` / `policy test` / `policy add` |
| **U-A8** | rule_policy | doctor 集成 rule_policy 校验 | ~15 行 | `doctor` 提前发现配置错误 |
| **U-A9** | rule_policy | `$comment` 自文档化规范 | 纯文档 | JSON 内嵌注释约定 |
| **U-A10** | rule_policy (**提级**) | MISRA 规则批量模板 + `policy init` | ~200 行 | 预置模板 + CLI 一键初始化 |

### U-B 易维护性改进

| 编号 | 来源 | 改进项 | 工作量 | 说明 |
|------|------|--------|--------|------|
| **U-B1** | review | Provider 自动发现/注册 | ~15 行重写 | `providers/*.py` 目录扫描 |
| **U-B2** | review | Provider Protocol 类型化 | ~20 行 | `base.py` 新增 Protocol 定义 |
| **U-B3** | review | doctor 检查项插件化 | ~40 行 | 按 provider 分组检查集 |
| **U-B4** | review | [merge_results.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/merge_results.py:0:0-0:0) 单元测试 | ~80 行 | 补齐唯一缺测试的核心模块 |
| **U-B5** | review | 错误码常量集中 `ErrorKind` | ~15 行 | 消除魔法字符串 |
| **U-B6** | review | oneshot `execute_stage` 去重 | ~25 行 | split/run/merge 模板代码合并 |

### U-C OpenCode 必需项

| 编号 | 来源 | 改进项 | 依赖 | 说明 |
|------|------|--------|------|------|
| **U-C1** | review | `providers/opencode.py` | U-B1 | 新 provider 文件 |
| **U-C2** | review | doctor opencode 诊断 | U-B3 | 新增 provider 检查集 |
| **U-C3** | review | README opencode 配置说明 | — | 补充 env 策略差异 |
| **U-C4** | review | 执行器 vs 模型 provider 设计评估 | U-B2 | 判断是否需拆分接口 |

---

## 实施批次（合并后）

### 第一批：基础设施 + 开箱体验（与 OpenCode 同步）

| 序号 | 编号 | 改进项 | 理由 |
|------|------|--------|------|
| 1 | **U-A6** | JSON Schema + `$schema` | **零代码改动即获 IDE 补全**，用户编辑 rule_policy 时立刻受益 |
| 2 | **U-A5** | `validate_rule_policy()` | 运行时兜底，防止配置静默失效；与 U-A6 互补 |
| 3 | **U-A10** | MISRA 批量模板 + `policy init` | **提级理由：** OpenCode 接入意味着更多团队/项目使用此工具。新项目面对上百条 MISRA 规则需要快速起步模板，而非逐条手写。与 U-C1 同批交付可形成"新 provider + 开箱即用规则"的完整体验 |
| 4 | **U-B1** | Provider 自动发现 | 让 U-C1 opencode.py 零注册 |
| 5 | **U-A3** | 失败 chunk 诊断摘要 | 5 行改动，立刻提升调试效率 |
| 6 | **U-B6** | oneshot 去重 | 降低后续阶段维护成本 |

**第一批产出物：**
```
.agents/config/rule_policy.schema.json          ← U-A6
.agents/config/templates/
  misra_c2012_conservative.json                  ← U-A10
  misra_c2012_relaxed.json                       ← U-A10
  autosar_baseline.json                          ← U-A10
.agents/tools/providers/opencode.py              ← U-C1
修改: common.py, providers/__init__.py, 
      run_fix_pipeline.py, oneshot.py, 
      split_cppcheck_xml.py, pipeline_cli.py
```

### 第二批：CLI 工具链 + 测试加固

| 序号 | 编号 | 改进项 | 理由 |
|------|------|--------|------|
| 7 | **U-A7** | `policy list/test/add` 子命令 | 消除规则匹配黑盒；依赖 U-A5 的校验逻辑 |
| 8 | **U-A8** | doctor 集成 rule_policy 校验 | 统一诊断入口，依赖 U-A5 |
| 9 | **U-A1** | `--dry-run` 预览 | 依赖 U-B6 去重后的 stage 架构 |
| 10 | **U-A2** | `--status` 进度查询 | — |
| 11 | **U-B4** | merge_results 单元测试 | 补齐测试缺口 |
| 12 | **U-B3** | doctor 检查项插件化 | 为 U-C2 opencode 诊断铺路 |
| 13 | **U-C2** | doctor opencode 诊断 | 依赖 U-B3 |
| 14 | **U-C3** | README opencode 说明 | — |

### 第三批：类型安全 + 可选增强

| 序号 | 编号 | 改进项 | 理由 |
|------|------|--------|------|
| 15 | **U-B2** | Provider Protocol 类型化 | 配合 mypy CI |
| 16 | **U-B5** | ErrorKind 常量集中 | 消除魔法字符串 |
| 17 | **U-A4** | doctor `--format json` | CI 场景增强 |
| 18 | **U-A9** | `$comment` 自文档化 | 纯文档，可随时补充 |
| 19 | **U-C4** | 执行器 vs 模型接口评估 | 架构决策，依赖 U-B2 |

---

## U-A10 提级说明

原计划 U-A10（MISRA 批量模板）放在 P3（最低优先级），现提升至**第一批**，核心理由：

1. **新 provider 入场 = 新团队入场** — OpenCode 接入后会有更多用户首次接触此工具，`policy init --template misra_c2012_relaxed` 可将首次配置时间从"翻文档 30 分钟"降至"一条命令 5 秒"
2. **与 U-A5/U-A6 天然协同** — 模板文件本身就是 Schema 的活文档，用户从模板起步就自带校验
3. **与 U-C1 形成完整交付** — "新 provider + 开箱即用规则模板"比"新 provider + 空白配置"的用户价值高一个量级
4. **工作量可控** — ~200 行，主要是 JSON 数据文件 + `policy init` 的模板拷贝逻辑

**预置模板内容规划：**

| 模板文件 | 规则数 | 策略特征 |
|----------|--------|----------|
| `misra_c2012_conservative.json` | ~80 | 全部 `needs_manual_review`，安全第一 |
| `misra_c2012_relaxed.json` | ~80 | 低风险规则 `auto_fix`，中风险 `careful_fix`，高风险保持人工 |
| `autosar_baseline.json` | ~30 | RTE/MCAL/BSW 路径全部 `needs_manual_review` + `risk_tags` 标注 |
| `cppcheck_common.json` | ~20 | cppcheck 原生规则（非 MISRA）的常见策略 |

---

## 依赖关系图

```
第一批:
  U-A6 (Schema) ──┐
  U-A5 (validate) ─┤── 互补，IDE + 运行时双保险
  U-A10 (模板)  ───┘── 模板即 Schema 活文档
  U-B1 (自动发现) ──→ U-C1 (opencode.py)
  U-A3 (诊断摘要)     独立
  U-B6 (去重)          独立

第二批:
  U-A5 ──→ U-A7 (policy 子命令)
  U-A5 ──→ U-A8 (doctor 集成)
  U-B6 ──→ U-A1 (dry-run)
  U-B3 (插件化) ──→ U-C2 (opencode 诊断)

第三批:
  U-B2 (Protocol) ──→ U-C4 (接口评估)
  其余均独立
```

---

## Phase 3 完成状态

| 编号 | 改进项 | 状态 | 提交 SHA |
|------|--------|------|----------|
| U-A6 | JSON Schema + `$schema` | DONE | ae45c88 |
| U-A5 | `validate_rule_policy()` | DONE | aadc138 |
| U-A10 | MISRA 批量模板 + `policy init` | DONE | 8558eb0, cd26ff7 |
| U-B1 | Provider 自动发现 | DONE | 05d7963 |
| U-A3 | 失败 chunk 诊断摘要 | DONE | cae735b |
| U-B6 | oneshot 去重 | DONE | 0dff383 |
| U-A7 | `policy list/test/add` 子命令 | DONE | 209262c |
| U-A8 | doctor 集成 rule_policy 校验 | DONE | 65e212b |
| U-A1 | `--dry-run` 预览 | DONE | d81c711 |
| U-A2 | `--status` 进度查询 | DONE | 6241f44 |
| U-B4 | merge_results 单元测试 | DONE | fa6712a |
| U-B3 | doctor 检查项插件化 | DONE | 672c344 |
| U-C2 | doctor opencode 诊断 | DONE | 672c344 |
| U-C3 | README opencode 说明 | DONE | 2b6ab45 |
| U-B2 | Provider Protocol 类型化 | DONE | 079fa79, 67b1f54 |
| U-B5 | ErrorKind 常量集中 | DONE | 38eb347 |
| U-A4 | doctor `--format json` | DONE | 1f86ad8 |
| U-A9 | `$comment` 自文档化 | DONE | 337c58d |
| U-C1 | `providers/opencode.py` | DONE | 6ec3b98 |
| U-C4 | 执行器 vs 模型 provider 设计评估 | DONE | ecf5c73 |

**偏差修复:**
- 偏差 #1: Schema actionType 枚举补充 fix/skip | DONE | 8619c01
- 偏差 #3: opencode provider 测试 | DONE | (本提交)
- 偏差 #4: Phase 3 完成状态文档 | DONE | (本提交)

**完成时间:** 2026-04-24
