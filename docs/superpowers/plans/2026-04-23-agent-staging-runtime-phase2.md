# Agent Staging Runtime Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 引入 agent 可写 staging 目录，把 agent 写入和 `.agents/runtime` 权威运行态分离，解决 agent 子会话无法直接写 `.agents/runtime/*` 的结构性问题。

**Architecture:** 保留 `.agents/runtime`、`.agents/runs/`、`.agents/reports/` 的现有语义不变，新增专门给 agent 会话使用的 staging 目录。provider 只向 staging 目录输出结果，`agent_runner.py` 或 `run_fix_pipeline.py` 在子进程退出后把 staging 结果导入权威 runtime，并继续复用现有 merge / archive / report 逻辑。

**Tech Stack:** Python 3.8+ 标准库、现有 `.agents/tools` 脚本、JSON/JSONL、Markdown、`unittest`。

---

## File Structure

- Modify `.agents/config/pipeline.json`
  - 新增 `agent.staging_dir`，并保持 `agent.launch.env` / `CODEX_HOME` 配置与 staging 语义一致。
- Modify `.agents/tools/common.py`
  - 增加 staging 目录解析、清理和导入辅助函数。
- Modify `.agents/tools/providers/codex.py`
  - prompt 中的结果写入目标改为 staging 目录，不再要求 agent 直接写 `.agents/runtime/results/*`。
- Modify `.agents/prompts/fix_chunk_prompt.txt`
  - 明确要求 agent 把 chunk 结果、issue 状态变更、edit 记录写入 staging。
- Modify `.agents/tools/agent_runner.py`
  - 创建 staging 目录
  - 透传给子进程
  - 在子进程退出后执行 staging -> runtime 导入
- Modify `.agents/tools/run_fix_pipeline.py`
  - 用导入后的权威结果判断 chunk 是否成功
  - 在导入失败时记录明确的 `error_kind`
- Modify `.agents/tools/doctor.py`
  - 检查 `agent.staging_dir` 是否可写
  - 区分“staging 可写但 runtime 权威目录由主流程写入”和“agent 直写 runtime”的旧模型
- Modify `README.md`
  - 说明 staging 目录语义
- Create `tests/test_agent_staging.py`
  - 覆盖 staging 目录、导入逻辑和失败路径
- Modify `tests/test_agent_runner.py`
  - 覆盖 runner 对 staging 的准备和导入
- Modify `tests/test_run_pipeline.py`
  - 覆盖通过 staging 结果判定 chunk 成功
- Modify `tests/test_doctor.py`
  - 覆盖 staging 可写性诊断

---

### Task 1: 配置模型补充 staging 目录

**Files:**
- Modify: `.agents/config/pipeline.json`
- Modify: `.agents/tools/common.py`
- Create: `tests/test_agent_staging.py`

- [ ] Add failing tests for:
  - missing `agent.staging_dir`
  - valid relative `agent.staging_dir`
  - resolved staging path staying under project root
- [ ] Extend `validate_pipeline_config()` to require `agent.staging_dir` as a non-empty string.
- [ ] Add a helper that resolves `agent.staging_dir` relative to project root.
- [ ] Update `pipeline.json` with a default such as `.agents/staging`.
- [ ] Run:

```bash
python3 -m unittest tests.test_agent_staging -v
```

- [ ] Commit:

```bash
git add .agents/config/pipeline.json .agents/tools/common.py tests/test_agent_staging.py
git commit -m "feat: add agent staging directory config"
```

---

### Task 2: Prompt 与 Provider 切换到 staging 输出

**Files:**
- Modify: `.agents/prompts/fix_chunk_prompt.txt`
- Modify: `.agents/tools/providers/codex.py`
- Modify: `tests/test_agent_runner.py`

- [ ] Add failing tests asserting the codex prompt references staging output files instead of `.agents/runtime/results/*`.
- [ ] Update the prompt so chunk result JSON/Markdown, issue status delta, and file change delta are written under the staging directory for the current chunk.
- [ ] Make `providers/codex.py` pass resolved staging paths into the rendered prompt.
- [ ] Run:

```bash
python3 -m unittest tests.test_agent_runner.CodexProviderTests -v
```

- [ ] Commit:

```bash
git add .agents/prompts/fix_chunk_prompt.txt .agents/tools/providers/codex.py tests/test_agent_runner.py
git commit -m "feat: write codex chunk output to staging"
```

---

### Task 3: Runner 导入 staging 结果到权威 runtime

**Files:**
- Modify: `.agents/tools/agent_runner.py`
- Modify: `.agents/tools/common.py`
- Modify: `tests/test_agent_runner.py`
- Modify: `tests/test_agent_staging.py`

- [ ] Add failing tests for:
  - creating per-chunk staging directories
  - importing `chunk_result.json` / `chunk_result.md` into `.agents/runtime/results/`
  - merging issue status delta into `.agents/runtime/issue_status.json`
  - merging file change delta into `.agents/runtime/file_change_index.json`
- [ ] Implement staging preparation in `agent_runner.py`.
- [ ] Implement import helpers that copy/merge staging artifacts into canonical runtime files after the agent exits successfully.
- [ ] Preserve the current auth bootstrap and env sanitization behavior.
- [ ] Classify staging import failures separately from raw provider execution failures.
- [ ] Run:

```bash
python3 -m unittest tests.test_agent_runner tests.test_agent_staging -v
```

- [ ] Commit:

```bash
git add .agents/tools/agent_runner.py .agents/tools/common.py tests/test_agent_runner.py tests/test_agent_staging.py
git commit -m "feat: import agent staging results into runtime"
```

---

### Task 4: Run 流程与 Doctor 适配 staging 模型

**Files:**
- Modify: `.agents/tools/run_fix_pipeline.py`
- Modify: `.agents/tools/doctor.py`
- Modify: `tests/test_run_pipeline.py`
- Modify: `tests/test_doctor.py`

- [ ] Add failing tests asserting:
  - chunk success is determined by imported canonical result files after staging import
  - doctor checks `agent.staging_dir` writability
  - doctor no longer assumes the agent must directly write `.agents/runtime/*`
- [ ] Update `run_fix_pipeline.py` to treat staging import completion as the success boundary.
- [ ] Update `doctor.py` to diagnose staging dir resolution and writability.
- [ ] Keep current launch/auth/network diagnostics intact.
- [ ] Run:

```bash
python3 -m unittest tests.test_doctor tests.test_run_pipeline -v
```

- [ ] Commit:

```bash
git add .agents/tools/run_fix_pipeline.py .agents/tools/doctor.py tests/test_run_pipeline.py tests/test_doctor.py
git commit -m "feat: route run pipeline through staging runtime"
```

---

### Task 5: 文档、真实链路验证与收尾

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md`

- [ ] Document the staging directory, the runtime import boundary, and the unchanged meaning of `.agents/runtime`.
- [ ] Run:

```bash
python3 -m unittest tests.test_doctor tests.test_run_pipeline tests.test_agent_runner tests.test_agent_staging -v
python3 .agents/tools/pipeline_cli.py doctor
```

- [ ] Run a real pipeline verification with generated sample input and confirm chunk 1 no longer fails because `.agents` is mounted read-only inside the agent session.
- [ ] Commit:

```bash
git add README.md docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md
git commit -m "docs: describe agent staging runtime phase 2"
```
