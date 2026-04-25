# OpenCode 兼容三期计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于真实 `1 issue / 1 chunk` 探针经验，为流水线增加 `opencode` 最小兼容能力，并把其数据目录、状态目录、网络错误和权限模型纳入现有 provider 抽象。

**经验总结：**

- `opencode run` 可以进入真实会话，说明现有 `provider -> runner -> staging` 设计可复用。
- 默认全局状态目录可能在受限环境下触发 SQLite/WAL 或锁文件写入失败；仅设置 `XDG_DATA_HOME` 不足，还需要同时管理 `XDG_STATE_HOME`。
- 真实运行时会访问 `https://opencode.ai/zen/v1/messages`；网络失败需要单独归类。
- `opencode` 的权限控制不完全等同于 `codex` / `Claude Code`，后续需要预留临时配置注入能力。

**Architecture:** 新增 `opencode` provider，但不改变现有 `.agents/runtime`、`.agents/staging`、`.agents/runs` 语义。通过 provider 级环境准备把 `XDG_DATA_HOME` 和 `XDG_STATE_HOME` 收口到工作区，并继续复用 staging 导入和统一日志/报告链路。

**Tech Stack:** Python 3.8+ 标准库、现有 `.agents/tools` 脚本、JSON/JSONL、Markdown、`unittest`、本机 `opencode` CLI。

---

## File Structure

- Modify `.agents/config/pipeline.json`
  - 增加 `opencode` 示例配置，但不替换默认 provider。
- Create `.agents/tools/providers/opencode.py`
  - 实现 `opencode` 的 launch spec、环境准备和错误分类。
- Modify `.agents/tools/providers/__init__.py`
  - 注册 `opencode` provider。
- Modify `.agents/tools/agent_runner.py`
  - 保持通用执行层不写死 `opencode` 特例，只接受 provider 级环境注入。
- Modify `.agents/tools/doctor.py`
  - 增加 `opencode` 的认证、网络、本地状态目录、权限模型诊断。
- Modify `README.md`
  - 补充 `opencode` 的结构化配置、环境变量和已知限制说明。
- Modify `tests/test_agent_runner.py`
  - 覆盖 `opencode` 的 launch spec、环境目录和错误分类。
- Modify `tests/test_doctor.py`
  - 覆盖 `opencode` 的认证/网络/状态目录诊断。

---

### Task 1: Provider 最小落地与环境目录收口

**Files:**
- Create: `.agents/tools/providers/opencode.py`
- Modify: `.agents/tools/providers/__init__.py`
- Modify: `tests/test_agent_runner.py`

- [x] Add failing tests for:
  - `opencode` launch spec generation
  - `XDG_DATA_HOME` 指向工作区内可写目录
  - `XDG_STATE_HOME` 指向工作区内可写目录
  - 常见 `ConnectionRefused` / `zen/v1/messages` 错误映射为 `network_error`
- [x] Implement `providers/opencode.py`.
- [x] Register the provider.
- [x] Run:

```bash
python3 -m unittest tests.test_agent_runner -v
```

当前状态：

- 已补齐 `.agents/config/pipeline.json` 中的 `agent.providers.opencode` 配置块，并把当前默认 provider 切到 `opencode`
- 已实现 `providers/opencode.py` 的 launch spec、`XDG_DATA_HOME` / `XDG_STATE_HOME` 环境注入和基础错误分类
- 已覆盖 `connection refused`、`dial tcp`、`timed out`、`zen/v1/messages` 等网络错误归类
- `tests.test_agent_runner` 当前已通过

---

### Task 2: Doctor 诊断补齐

**Files:**
- Modify: `.agents/tools/doctor.py`
- Modify: `tests/test_doctor.py`

- [x] Add failing tests for:
  - `opencode` 可执行入口检查
  - 本地状态目录不可写
  - 数据目录不可写
  - 网络失败提示
  - 认证状态提示
- [x] Extend `doctor.py` with `opencode`-specific diagnostics.
- [x] Run:

```bash
python3 -m unittest tests.test_doctor -v
```

当前状态：

- `doctor.py` 已具备 `opencode` 的可执行入口、XDG 目录和认证提示检查
- `tests.test_doctor` 当前已通过
- 网络错误的最终诊断仍以运行时 stderr 分类为准，`doctor` 继续提供环境与配置层提示

---

### Task 3: 文档与真实 `1 issue / 1 chunk` 验收

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md`

- [x] Document `opencode` config, environment isolation, and known limitations.
- [ ] Run one real `1 issue / 1 chunk` acceptance flow with `opencode`.
- [ ] Confirm whether prompt-by-arg is sufficient or `prompt_via=file` is needed.
- [ ] Record the final blocker, if any, with exact classification.

---

### Task 4: 收尾与后续抽象评估

**Files:**
- Modify: `docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md`
- Modify: `docs/superpowers/plans/2026-04-24-opencode-phase3.md`

- [ ] Decide whether current `agent.provider` 模型仍够用，或是否需要在后续区分“执行器 provider”和“模型 provider”。
- [ ] Record what remains provider-specific vs. what should move back into the common runner.
- [x] Prepare final commit message for the phase 3 implementation batch.
