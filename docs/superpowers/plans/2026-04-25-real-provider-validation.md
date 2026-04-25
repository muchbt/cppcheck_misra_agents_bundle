# Real Provider Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 `codex` / `opencode` 的真实运行阻塞点，并新增 `pipeline_cli validate-real` 子命令，用于执行真实 `1 issue / 1 chunk` provider 验收。

**Architecture:** 复用现有 `split -> run -> verify` 主流程，不新增并行执行框架。`validate-real` 只负责创建最小样例工作区、判定 provider 是否“应跑”、切换到目标 provider 配置后串行调用现有 CLI 模块，并汇总统一报告。

**Tech Stack:** Python 3.8+ 标准库、现有 `.agents/tools` CLI、`unittest`、本机 `codex` / `claude` / `opencode` CLI。

---

### Task 1: 修复 provider 真实运行阻塞点

**Files:**
- Modify: `.agents/config/pipeline.json`
- Modify: `.agents/tools/providers/codex.py`
- Modify: `.agents/tools/providers/opencode.py`
- Test: `tests/test_agent_runner.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: 修正默认 `opencode` 启动前缀**

把 `opencode` 的默认命令从裸 `opencode` 收口为明确的非交互入口，避免真实运行落到帮助/TUI。

- [ ] **Step 2: 让 `codex` 真实运行满足 trusted directory 前置条件**

通过 provider 级 launch 参数或运行前准备，保证最小验收样例不会因为 git repo trust 检查直接失败。

- [ ] **Step 3: 补 provider 单测**

覆盖：
- `codex` 启动参数包含 trusted directory 所需参数
- `opencode` 启动参数是非交互前缀
- `doctor.check_agent_launch()` 能接受新的前缀约束

### Task 2: 新增 `validate-real` 子命令

**Files:**
- Create: `.agents/tools/validate_real.py`
- Modify: `.agents/tools/pipeline_cli.py`
- Modify: `.agents/tools/doctor.py`
- Test: `tests/test_pipeline_cli.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: 实现最小样例工作区构建**

在临时目录或保留目录中创建：
- `src/a.c`
- `cppcheck.xml`
- `.agents/config/pipeline.json` 的 provider 定向副本
- 必要的 `.agents/prompts` / skill 兼容文件

- [ ] **Step 2: 实现 provider 前置状态判定**

状态必须收敛为：
- `ready`
- `skipped_not_installed`
- `skipped_auth_missing`
- `skipped_precheck_blocked`

判定来源优先复用 `doctor` 的现有检查结果，不重复定义新规则。

- [ ] **Step 3: 实现真实 `split -> run -> verify` 编排**

仅对 `ready` 的 provider 执行：
- `split_cppcheck_xml.main(["--run-id", ...])`
- `run_fix_pipeline.main(["--max-chunks", "1"])`
- `verify_chunk.verify_chunk_result(...)`

- [ ] **Step 4: 实现统一 JSON 报告与退出码**

报告至少包含：
- provider
- status
- precheck results
- split/run return code
- stderr 摘要
- result/verification 是否存在

退出码规则：
- 任一 `ready` provider 失败：非 `0`
- 所有 `ready` provider 成功：`0`
- 全部跳过：`0`，但报告明确未发生真实验收

- [ ] **Step 5: 把 `validate-real` 注册到 `pipeline_cli`**

### Task 3: 补测试并做针对性验证

**Files:**
- Modify: `tests/test_pipeline_cli.py`
- Modify: `tests/test_doctor.py`
- Modify: `tests/test_agent_runner.py`

- [ ] **Step 1: 新增 CLI 分发测试**

覆盖 `pipeline_cli` 暴露 `validate-real`，并能把子参数透传到 `validate_real.main()`。

- [ ] **Step 2: 新增 `validate_real` 单测**

覆盖：
- 未安装 provider 被跳过
- 未认证 provider 被跳过
- `ready` provider 成功时写入报告
- 存在失败 provider 时整体退出非 `0`

- [ ] **Step 3: 运行针对性测试**

Run:
`python3 -m unittest tests.test_pipeline_cli tests.test_doctor tests.test_agent_runner -v`

- [ ] **Step 4: 运行一次 `validate-real` 自举验证**

至少验证命令可执行、报告可生成；真实 provider 是否通过取决于本机安装与认证状态，不得伪造结论。
