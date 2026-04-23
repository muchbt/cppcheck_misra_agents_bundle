# 非交互 Agent 执行层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 cppcheck/MISRA 流水线补上结构化、非交互、可诊断的 agent 执行层，并为 `Claude Code` 二期接入预留稳定接口。

**Architecture:** 保留现有 `split -> run -> merge` 主流程和 runtime/报告结构，只替换 `run` 阶段的 agent 调用模型。新增 `providers/` 与 `agent_runner.py`，由 provider 负责 prompt 和 launch spec，runner 负责配置校验、cwd/env/stdin 准备和子进程执行，`doctor` 复用同一套执行元信息做阻断诊断。

**Tech Stack:** Python 3.8+ 标准库、`unittest`、现有 `.agents/tools` 脚本、JSON/JSONL、Markdown。

---

## File Structure

- Modify `.agents/config/pipeline.json`
  - 将旧的 `agent.type` / `agent.command` 升级为 `agent.provider` / `agent.launch` / `agent.capabilities`。
- Modify `.agents/tools/common.py`
  - 扩展配置校验；为 runner 提供 cwd/env 解析辅助；保留 Python 3.8 兼容类型标注。
- Create `.agents/tools/providers/base.py`
  - 定义 `LaunchSpec`、`ExecutionResult`、provider 元信息结构。
- Create `.agents/tools/providers/__init__.py`
  - 提供 provider 注册表和 `get_provider()`。
- Create `.agents/tools/providers/codex.py`
  - 组装 chunk prompt，声明 `codex exec` 的非交互 launch spec。
- Create `.agents/tools/agent_runner.py`
  - 加载配置、解析 provider、验证 launch spec、调用 `subprocess.run()`、统一返回执行结果。
- Modify `.agents/tools/run_fix_pipeline.py`
  - 用 `run_chunk_agent()` 替代旧的 `run_chunk()` 调用，保留 progress / log / verification 逻辑。
- Modify `.agents/tools/doctor.py`
  - 从“命令存在”升级到“是否适合非交互执行”的检查。
- Modify `README.md`
  - 更新 `agent` 配置示例和非交互执行约束。
- Create `tests/test_agent_runner.py`
  - 覆盖配置模型、provider、runner 的核心行为。
- Modify `tests/test_doctor.py`
  - 改为覆盖结构化 agent 配置与阻断诊断。
- Modify `tests/test_run_pipeline.py`
  - 改为通过 runner 测试 `run` 阶段，而不是通过 `agent_adapter_codex.py`。

---

### Task 1: 配置模型升级与公共校验

**Files:**
- Modify: `.agents/config/pipeline.json`
- Modify: `.agents/tools/common.py`
- Create: `tests/test_agent_runner.py`

- [ ] **Step 1: 写配置校验的失败用例**

```python
def test_validate_pipeline_config_rejects_legacy_agent_command(self) -> None:
    config = {
        "project": {"runtime_dir": ".agents/runtime", "reports_dir": ".agents/reports", "chunks_dir": ".agents/runtime/chunks", "results_dir": ".agents/runtime/results"},
        "input": {"cppcheck_xml": "cppcheck.xml"},
        "chunking": {"max_issues_per_chunk": 12, "max_files_per_chunk": 3, "prefer_group_by_file": True, "split_high_risk_alone": True},
        "filter": {"include_severity": ["error", "warning", "style"], "exclude_information": True},
        "misra": {"enabled": True, "detect_prefixes": ["misra"]},
        "fix_strategy": {"mode": "conservative", "mark_high_risk_in_all_auto": True, "require_review_after_high_risk_fix": True},
        "verification": {"mode": "light", "rerun_cppcheck_for_touched_files": False, "custom_command": ""},
        "agent": {"type": "codex", "command": "codex", "auto_bootstrap_compat": True},
    }

    errors, warnings = common.validate_pipeline_config(config)

    self.assertIn("agent.provider must be a non-empty string", errors)
    self.assertIn("agent.launch must be an object", errors)
    self.assertEqual(warnings, [])
```

- [ ] **Step 2: 运行失败用例确认当前行为不满足**

Run: `python3 -m unittest tests.test_agent_runner.AgentConfigValidationTests.test_validate_pipeline_config_rejects_legacy_agent_command -v`

Expected: FAIL，说明当前 `validate_pipeline_config()` 仍接受旧结构。

- [ ] **Step 3: 更新默认配置文件**

```json
"agent": {
  "provider": "codex",
  "launch": {
    "argv": ["codex", "exec", "--full-auto"],
    "prompt_via": "stdin",
    "cwd": "project_root",
    "env": {
      "CODEX_HOME": ".agents/runtime/agent-home"
    },
    "requires_tty": false,
    "output": {
      "mode": "exit_code"
    }
  },
  "capabilities": {
    "non_interactive": true,
    "workspace_write_required": true
  },
  "auto_bootstrap_compat": true
}
```

- [ ] **Step 4: 扩展 `validate_pipeline_config()` 的最小实现**

```python
agent = config.get("agent", {})
if isinstance(agent, dict):
    provider = agent.get("provider")
    if not isinstance(provider, str) or not provider.strip():
        errors.append("agent.provider must be a non-empty string")

    launch = agent.get("launch")
    if not isinstance(launch, dict):
        errors.append("agent.launch must be an object")
    else:
        argv = launch.get("argv")
        if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item.strip() for item in argv):
            errors.append("agent.launch.argv must be a non-empty list of strings")
        if launch.get("prompt_via") not in {"stdin", "arg", "file"}:
            errors.append("agent.launch.prompt_via must be one of: stdin, arg, file")
        if launch.get("cwd") not in {"project_root", "runtime_dir", "custom"}:
            errors.append("agent.launch.cwd must be one of: project_root, runtime_dir, custom")
        if not isinstance(launch.get("env"), dict):
            errors.append("agent.launch.env must be an object")
        if not isinstance(launch.get("requires_tty"), bool):
            errors.append("agent.launch.requires_tty must be a boolean")

    capabilities = agent.get("capabilities")
    if not isinstance(capabilities, dict):
        errors.append("agent.capabilities must be an object")
```

- [ ] **Step 5: 补充结构化配置通过用例**

```python
def test_validate_pipeline_config_accepts_structured_agent(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    errors, warnings = common.validate_pipeline_config(config)
    self.assertEqual(errors, [])
    self.assertEqual(warnings, [])
```

- [ ] **Step 6: 运行本任务测试**

Run: `python3 -m unittest tests.test_agent_runner.AgentConfigValidationTests -v`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add .agents/config/pipeline.json .agents/tools/common.py tests/test_agent_runner.py
git commit -m "feat: add structured agent config validation"
```

---

### Task 2: Provider 基础设施与 Codex Provider

**Files:**
- Create: `.agents/tools/providers/base.py`
- Create: `.agents/tools/providers/__init__.py`
- Create: `.agents/tools/providers/codex.py`
- Modify: `tests/test_agent_runner.py`

- [ ] **Step 1: 写 Codex provider 的失败用例**

```python
def test_codex_provider_builds_non_interactive_launch_spec(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    chunk = {"chunk_index": 1, "fix_strategy": "conservative", "contains_high_risk": False}

    spec = codex_provider.build_launch_spec(config, chunk)

    self.assertEqual(spec["argv"][:3], ["codex", "exec", "--full-auto"])
    self.assertEqual(spec["prompt_via"], "stdin")
    self.assertEqual(spec["cwd_mode"], "project_root")
    self.assertFalse(spec["requires_tty"])
```

- [ ] **Step 2: 运行失败用例确认 provider 尚不存在**

Run: `python3 -m unittest tests.test_agent_runner.CodexProviderTests.test_codex_provider_builds_non_interactive_launch_spec -v`

Expected: FAIL，提示模块或函数不存在。

- [ ] **Step 3: 定义 provider 通用结构**

```python
# .agents/tools/providers/base.py
from typing import Any, Dict

LaunchSpec = Dict[str, Any]
ExecutionResult = Dict[str, Any]
ProviderSpec = Dict[str, Any]
```

- [ ] **Step 4: 实现 provider 注册表**

```python
# .agents/tools/providers/__init__.py
from providers import codex

PROVIDERS = {
    "codex": codex,
}

def get_provider(name: str):
    return PROVIDERS.get(name)
```

- [ ] **Step 5: 实现 `providers/codex.py` 的最小版本**

```python
from common import CONFIG_DIR, PROMPTS_DIR, RUNTIME_DIR, load_json, read_text

def build_prompt(chunk_index: int) -> str:
    template = read_text(PROMPTS_DIR / "fix_chunk_prompt.txt", "")
    chunk = load_json(RUNTIME_DIR / "chunks" / f"chunk_{chunk_index:03d}.json", {})
    strategy = chunk.get("fix_strategy", "conservative")
    return template.format(chunk_index=chunk_index, strategy_instructions=f"Fix strategy: {strategy}.")

def build_launch_spec(config: dict, chunk: dict) -> dict:
    launch = config["agent"]["launch"]
    return {
        "argv": list(launch["argv"]),
        "prompt_via": launch["prompt_via"],
        "cwd_mode": launch["cwd"],
        "env": dict(launch.get("env", {})),
        "requires_tty": bool(launch["requires_tty"]),
        "output_mode": launch.get("output", {}).get("mode", "exit_code"),
        "prompt": build_prompt(int(chunk["chunk_index"])),
    }
```

- [ ] **Step 6: 运行 provider 测试**

Run: `python3 -m unittest tests.test_agent_runner.CodexProviderTests -v`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add .agents/tools/providers/base.py .agents/tools/providers/__init__.py .agents/tools/providers/codex.py tests/test_agent_runner.py
git commit -m "feat: add codex provider registry"
```

---

### Task 3: 通用 Runner 落地并接入 Run Pipeline

**Files:**
- Create: `.agents/tools/agent_runner.py`
- Modify: `.agents/tools/run_fix_pipeline.py`
- Modify: `tests/test_agent_runner.py`
- Modify: `tests/test_run_pipeline.py`

- [ ] **Step 1: 写 runner 的失败用例**

```python
def test_run_chunk_agent_passes_prompt_via_stdin(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    chunk = {"chunk_index": 1}

    with patch.object(agent_runner.subprocess, "run") as run_mock:
        run_mock.return_value.returncode = 0
        result = agent_runner.run_chunk_agent(config, chunk)

    kwargs = run_mock.call_args.kwargs
    self.assertEqual(kwargs["input"], result["prompt"])
    self.assertEqual(kwargs["text"], True)
    self.assertEqual(result["returncode"], 0)
```

- [ ] **Step 2: 写 run pipeline 的替换用例**

```python
def test_run_pipeline_uses_agent_runner_result(self) -> None:
    with patch.object(run_fix_pipeline, "run_chunk_agent", return_value={"returncode": 0, "result_path": str(results_dir / "chunk_001_result.json"), "error_kind": ""}):
        rc = run_fix_pipeline.main([])
    self.assertEqual(rc, 0)
```

- [ ] **Step 3: 运行失败用例确认 runner 尚未接入**

Run: `python3 -m unittest tests.test_agent_runner.AgentRunnerTests tests.test_run_pipeline.SplitAndRunPipelineTests.test_run_pipeline_uses_agent_runner_result -v`

Expected: FAIL。

- [ ] **Step 4: 实现 `agent_runner.py` 的最小执行路径**

```python
def run_chunk_agent(config: dict, chunk: dict) -> dict:
    provider_name = config["agent"]["provider"]
    provider = get_provider(provider_name)
    if provider is None:
        return {"returncode": 2, "error_kind": "config_error", "stderr": "unsupported provider", "prompt": ""}

    spec = provider.build_launch_spec(config, chunk)
    completed = subprocess.run(
        spec["argv"],
        input=spec["prompt"] if spec["prompt_via"] == "stdin" else None,
        text=True,
        capture_output=True,
        cwd=str(ROOT) if spec["cwd_mode"] == "project_root" else str(RUNTIME_DIR),
        env=build_launch_env(spec["env"]),
    )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "error_kind": "" if completed.returncode == 0 else "runtime_error",
        "prompt": spec["prompt"],
    }
```

- [ ] **Step 5: 用 runner 替换旧适配器调用**

```python
config = load_json(CONFIG_DIR / "pipeline.json", {})
chunk_payload = load_chunk_payload(idx)
result = run_chunk_agent(config, chunk_payload)
rc = int(result.get("returncode", 1))
success = rc == 0 and result_json.exists()
```

- [ ] **Step 6: 删除旧导入并保留失败分类**

```python
from agent_runner import run_chunk_agent

progress["last_failure"] = {
    "chunk_index": idx,
    "returncode": last_rc,
    "retries": args.retry_failed,
    "error_kind": result.get("error_kind", "runtime_error"),
}
```

- [ ] **Step 7: 运行本任务测试**

Run: `python3 -m unittest tests.test_agent_runner.AgentRunnerTests tests.test_run_pipeline -v`

Expected: PASS。

- [ ] **Step 8: 提交**

```bash
git add .agents/tools/agent_runner.py .agents/tools/run_fix_pipeline.py tests/test_agent_runner.py tests/test_run_pipeline.py
git commit -m "feat: run chunks through agent runner"
```

---

### Task 4: 升级 Doctor 为非交互执行诊断

**Files:**
- Modify: `.agents/tools/doctor.py`
- Modify: `tests/test_doctor.py`

- [ ] **Step 1: 写 doctor 阻断用例**

```python
def test_check_agent_launch_rejects_interactive_codex(self) -> None:
    config = {
        "agent": {
            "provider": "codex",
            "launch": {"argv": ["codex"], "prompt_via": "arg", "cwd": "project_root", "env": {}, "requires_tty": True, "output": {"mode": "exit_code"}},
            "capabilities": {"non_interactive": False, "workspace_write_required": True},
            "auto_bootstrap_compat": True,
        }
    }

    result = doctor.check_agent_launch(config, root=REPO_ROOT)

    self.assertEqual(result["level"], "error")
    self.assertEqual(result["code"], "agent_launch_interactive_not_supported")
```

- [ ] **Step 2: 写不可写环境目录的用例**

```python
def test_check_agent_launch_rejects_unwritable_env_dir(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    with patch.object(doctor, "_ensure_writable_dir", return_value="permission denied"):
        result = doctor.check_agent_launch(config, root=REPO_ROOT)
    self.assertEqual(result["level"], "error")
    self.assertEqual(result["code"], "agent_launch_env_unwritable")
```

- [ ] **Step 3: 运行失败用例**

Run: `python3 -m unittest tests.test_doctor.DoctorTests.test_check_agent_launch_rejects_interactive_codex tests.test_doctor.DoctorTests.test_check_agent_launch_rejects_unwritable_env_dir -v`

Expected: FAIL。

- [ ] **Step 4: 实现 `check_agent_launch()`**

```python
def check_agent_launch(config: Any, root: Path) -> Dict[str, Any]:
    agent = config.get("agent", {}) if isinstance(config, dict) else {}
    launch = agent.get("launch", {}) if isinstance(agent, dict) else {}
    capabilities = agent.get("capabilities", {}) if isinstance(agent, dict) else {}

    argv = launch.get("argv", [])
    if not isinstance(argv, list) or not argv:
        return make_result("error", "agent_launch_invalid_argv", "agent 启动参数无效。", "launch.argv 不能为空。")
    if bool(launch.get("requires_tty")) or not bool(capabilities.get("non_interactive")):
        return make_result("error", "agent_launch_interactive_not_supported", "当前 agent 配置仍依赖交互式执行。", "流水线只支持非交互模式。")
```

- [ ] **Step 5: 将 provider 和 launch 诊断接入 `collect_checks()`**

```python
if pipeline_result["level"] != "error":
    results.append(check_agent_launch(config, root))
    results.append(check_custom_verification_command(config))
```

- [ ] **Step 6: 运行 doctor 测试**

Run: `python3 -m unittest tests.test_doctor -v`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add .agents/tools/doctor.py tests/test_doctor.py
git commit -m "feat: add non-interactive agent diagnostics"
```

---

### Task 5: 文档、全链路验证与收尾

**Files:**
- Modify: `README.md`
- Modify: `tests/test_agent_runner.py`

- [ ] **Step 1: 更新 README 的 agent 配置示例**

````md
## Agent 配置

`pipeline.json` 必须使用结构化 `agent` 配置。默认的 `codex` 非交互配置如下：

```json
"agent": {
  "provider": "codex",
  "launch": {
    "argv": ["codex", "exec", "--full-auto"],
    "prompt_via": "stdin",
    "cwd": "project_root",
    "env": {
      "CODEX_HOME": ".agents/runtime/agent-home"
    },
    "requires_tty": false,
    "output": {
      "mode": "exit_code"
    }
  }
}
```
````

- [ ] **Step 2: 补充一个 spawn error 的 runner 测试**

```python
def test_run_chunk_agent_reports_spawn_error(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    with patch.object(agent_runner.subprocess, "run", side_effect=OSError("permission denied")):
        result = agent_runner.run_chunk_agent(config, {"chunk_index": 1})
    self.assertEqual(result["error_kind"], "spawn_error")
    self.assertIn("permission denied", result["stderr"])
```

- [ ] **Step 3: 运行单测**

Run: `python3 -m unittest tests.test_doctor tests.test_run_pipeline tests.test_agent_runner -v`

Expected: PASS。

- [ ] **Step 4: 运行 doctor**

Run: `python3 .agents/tools/pipeline_cli.py doctor`

Expected: 不再以“裸 `codex` 可执行即可”判定通过；若配置或环境仍是交互式，明确报 blocker。

- [ ] **Step 5: 运行真实链路验证**

Run:

```bash
python3 gen_scan_files.py
cppcheck --enable=warning,style --addon=misra.py --xml --xml-version=2 . 2> cppcheck.xml
python3 .agents/tools/pipeline_cli.py oneshot --fresh --run-id 20260423-999
```

Expected:
- 不出现交互式 TUI 提示
- 不再出现启动阶段 PATH 更新导致的只读文件系统报错
- `split` 正常完成
- `run` 通过 provider + runner 进入非交互执行
- 若 agent 本身失败，`progress.json` 中 `last_failure.error_kind` 能区分失败类别

- [ ] **Step 6: 检查最终工作树**

Run: `git status --short`

Expected: 仅剩本次验证产物或无未提交实现改动。

- [ ] **Step 7: 提交**

```bash
git add README.md tests/test_agent_runner.py
git commit -m "docs: describe non-interactive agent runner"
```
