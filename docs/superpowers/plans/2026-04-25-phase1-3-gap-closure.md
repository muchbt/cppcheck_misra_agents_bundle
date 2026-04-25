# Phase 1-3 Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐前三期计划遗留的 provider 测试、配置和诊断缺口，并修复当前因默认切换到 `opencode` 而暴露的回归问题。

**Architecture:** 保持现有 `agent.provider + agent.providers.<name>` 配置模型、`providers/*` 模块边界和 `doctor` 注册式检查框架不变。实现只收口 5 个面：默认配置、测试夹具隔离、`agent_runner` 根目录解析、`opencode` 诊断/错误分类、README 与 phase 3 文档同步。

**Tech Stack:** Python 3.8+、标准库 `unittest`、现有 `.agents/tools` provider/runner/doctor 框架、JSON、Markdown。

---

## File Structure

- Modify `.agents/config/pipeline.json`
  - 补齐 `agent.providers.opencode` 结构化配置，保证当前选中 provider 可通过校验。
- Modify `.agents/tools/agent_runner.py`
  - 让 env/cwd/staging 路径都按当前传入 root 一致解析，避免测试误触真实仓库路径。
- Modify `.agents/tools/providers/opencode.py`
  - 完善 `opencode` 的 launch spec 和错误分类。
- Modify `.agents/tools/doctor.py`
  - 把 `opencode` 的可执行文件、XDG 目录、认证和网络提示收口到现有检查框架。
- Modify `tests/test_agent_runner.py`
  - 去掉对“仓库默认 provider”的隐式依赖，补 `opencode` 的真实行为测试。
- Modify `tests/test_doctor.py`
  - 显式区分 `codex` / `claude` / `opencode` 诊断场景。
- Modify `README.md`
  - 同步 `opencode` 配置与运行时隔离说明。
- Modify `docs/superpowers/plans/2026-04-24-opencode-phase3.md`
  - 按当前真实实现状态更新 phase 3 计划文档。

### Task 1: 补齐默认 `opencode` 配置并恢复配置校验

**Files:**
- Modify: `.agents/config/pipeline.json`
- Modify: `tests/test_agent_runner.py`
- Test: `tests/test_agent_runner.py`

- [ ] **Step 1: 写失败测试，锁定“当前选中的 provider 必须有完整配置”**

```python
def test_validate_pipeline_config_accepts_structured_agent(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})

    self.assertEqual(config["agent"]["provider"], "opencode")
    self.assertIn("opencode", config["agent"]["providers"])
    self.assertEqual(
        config["agent"]["providers"]["opencode"]["launch"]["argv"],
        ["opencode"],
    )

    errors, warnings = common.validate_pipeline_config(config)

    self.assertEqual(errors, [])
    self.assertEqual(warnings, [])
```

- [ ] **Step 2: 运行单测，确认当前配置确实失败**

Run: `python3 -m unittest tests.test_agent_runner.AgentConfigValidationTests.test_validate_pipeline_config_accepts_structured_agent -v`

Expected: FAIL，报 `agent.providers must include the selected agent.provider` 或 `agent.launch.argv must be a non-empty list of strings`。

- [ ] **Step 3: 在 `pipeline.json` 中补齐 `opencode` provider 配置**

```json
"agent": {
  "provider": "opencode",
  "staging_dir": ".agents/staging",
  "providers": {
    "codex": {
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
      }
    },
    "claude": {
      "launch": {
        "argv": ["claude", "-p", "--output-format", "text", "--permission-mode", "acceptEdits"],
        "prompt_via": "stdin",
        "cwd": "project_root",
        "env": {},
        "requires_tty": false,
        "output": {
          "mode": "exit_code"
        }
      },
      "capabilities": {
        "non_interactive": true,
        "workspace_write_required": true
      }
    },
    "opencode": {
      "launch": {
        "argv": ["opencode"],
        "prompt_via": "stdin",
        "cwd": "project_root",
        "env": {},
        "requires_tty": false,
        "output": {
          "mode": "exit_code"
        }
      },
      "capabilities": {
        "non_interactive": true,
        "workspace_write_required": true
      }
    }
  },
  "auto_bootstrap_compat": true
}
```

- [ ] **Step 4: 运行配置校验测试，确认默认配置恢复**

Run: `python3 -m unittest tests.test_agent_runner.AgentConfigValidationTests -v`

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add .agents/config/pipeline.json tests/test_agent_runner.py
git commit -m "fix: add structured opencode provider config"
```

### Task 2: 让 provider 测试不再依赖仓库默认 provider

**Files:**
- Modify: `tests/test_agent_runner.py`
- Modify: `tests/test_doctor.py`
- Test: `tests/test_agent_runner.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: 写失败测试，明确 codex/claude 用例必须显式切换 provider**

```python
def test_codex_provider_builds_non_interactive_launch_spec(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "codex"
    chunk = {
        "chunk_index": 1,
        "fix_strategy": "conservative",
        "contains_high_risk": False,
    }
    codex_provider = importlib.import_module("providers.codex")
    spec = codex_provider.build_launch_spec(config, chunk)

    self.assertEqual(spec["argv"][:3], ["codex", "exec", "--full-auto"])
    self.assertEqual(spec["prompt_via"], "stdin")
    self.assertEqual(spec["cwd_mode"], "project_root")

def test_check_agent_skill_visibility_reports_codex_skill_ok(self) -> None:
    config = doctor.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "codex"

    result = doctor.check_agent_skill_visibility(config, root=REPO_ROOT)

    self.assertEqual(result["level"], "ok")
    self.assertEqual(result["code"], "agent_skill_ok")
```

- [ ] **Step 2: 运行受影响测试，确认默认 provider 漂移仍会打断断言**

Run: `python3 -m unittest tests.test_agent_runner.CodexProviderTests tests.test_doctor.DoctorTests.test_check_agent_skill_visibility_reports_codex_skill_ok -v`

Expected: FAIL，至少一个用例仍会拿到 `opencode` 分支结果。

- [ ] **Step 3: 修改 `tests/test_agent_runner.py` 和 `tests/test_doctor.py`，把 provider 选择显式写进每个场景**

```python
config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
config["agent"]["provider"] = "codex"
```

```python
config = doctor.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
config["agent"]["provider"] = "claude"
```

```python
config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
config["agent"]["provider"] = "opencode"
```

- [ ] **Step 4: 为 `opencode` 补一条真实 launch spec 测试，而不是只测 import**

```python
def test_opencode_provider_builds_launch_spec_with_workspace_staging(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "opencode"
    chunk = {
        "chunk_index": 1,
        "fix_strategy": "conservative",
        "contains_high_risk": False,
    }

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        runtime_dir = root / "runtime"
        prompts_dir = root / "prompts"
        chunks_dir = runtime_dir / "chunks"
        staging_dir = root / ".agents" / "staging"
        runtime_dir.mkdir(parents=True)
        prompts_dir.mkdir(parents=True)
        chunks_dir.mkdir(parents=True)
        staging_dir.mkdir(parents=True)

        (prompts_dir / "fix_chunk_prompt.txt").write_text(
            "Read chunk {chunk_index}\n{chunk_result_json_path}\n{strategy_instructions}\n",
            encoding="utf-8",
        )
        (chunks_dir / "chunk_001.json").write_text(json.dumps(chunk), encoding="utf-8")

        opencode_provider = importlib.import_module("providers.opencode")
        provider_base = importlib.import_module("providers.base")

        with patch.object(opencode_provider, "RUNTIME_DIR", runtime_dir), patch.object(
            provider_base, "PROMPTS_DIR", prompts_dir
        ), patch.object(
            provider_base, "resolve_agent_staging_dir", return_value=staging_dir
        ):
            spec = opencode_provider.build_launch_spec(config, chunk)

    self.assertEqual(spec["argv"][:1], ["opencode"])
    self.assertIn("--add-dir", spec["argv"])
    self.assertIn(str(staging_dir / "chunk_001"), spec["argv"])
    self.assertEqual(spec["prompt_via"], "stdin")
    self.assertIn(".agents/staging/chunk_001/chunk_result.json", spec["prompt"])
```

- [ ] **Step 5: 运行 provider/doctor 测试，确认各自与默认配置解耦**

Run: `python3 -m unittest tests.test_agent_runner tests.test_doctor -v`

Expected: 仍可能有与 `agent_runner` / `doctor` 实现有关的失败，但不再出现“因为默认 provider 被切换”而导致的大面积误报。

- [ ] **Step 6: Commit**

```bash
git add tests/test_agent_runner.py tests/test_doctor.py
git commit -m "test: isolate provider-specific cases from default config"
```

### Task 3: 修正 `agent_runner` 的根目录与 staging 路径解析

**Files:**
- Modify: `.agents/tools/agent_runner.py`
- Modify: `tests/test_agent_runner.py`
- Test: `tests/test_agent_runner.py`

- [ ] **Step 1: 写失败测试，锁定 `ROOT` patch 后所有相对路径都必须落在临时目录**

```python
def test_run_chunk_agent_reports_spawn_error(self) -> None:
    config = common.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "codex"
    chunk = {"chunk_index": 1}
    agent_runner = importlib.import_module("agent_runner")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        staging_dir = root / ".agents" / "staging" / "chunk_001"

        with patch.object(
            agent_runner,
            "ROOT",
            root,
        ), patch.object(
            agent_runner,
            "get_provider",
            return_value=SimpleNamespace(
                build_launch_spec=lambda current_config, current_chunk: {
                    "argv": ["codex", "exec", "--full-auto"],
                    "prompt_via": "stdin",
                    "cwd_mode": "project_root",
                    "env": {"CODEX_HOME": ".agents/runtime/agent-home"},
                    "requires_tty": False,
                    "output_mode": "exit_code",
                    "prompt": "prompt body",
                    "staging_dir": str(staging_dir),
                }
            ),
        ), patch.object(agent_runner.subprocess, "run", side_effect=OSError("permission denied")):
            result = agent_runner.run_chunk_agent(config, chunk)

    self.assertEqual(result["error_kind"], "spawn_error")
    self.assertIn("permission denied", result["stderr"])
```

说明：本任务已确认的现状问题是 `resolve_env_path()`、`build_launch_env()`、`resolve_cwd()` 三个函数硬绑模块级 `ROOT`，导致 `spawn_error` 测试会误用真实仓库路径。

- [ ] **Step 2: 运行该测试，确认当前实现仍可能去删真实仓库的 staging 目录**

Run: `python3 -m unittest tests.test_agent_runner.AgentRunnerTests.test_run_chunk_agent_reports_spawn_error -v`

Expected: ERROR，栈中出现 `.agents/staging/chunk_001` 的只读路径或 `shutil.rmtree()` 失败。

- [ ] **Step 3: 调整 `agent_runner.py`，给路径解析函数增加 `root` 形参，并在 `run_chunk_agent()` 中统一透传**

```python
def resolve_env_path(value: str, root: Path = ROOT) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    return path


def build_launch_env(env_config: Dict[str, str], provider: Any, root: Path = ROOT) -> Dict[str, str]:
    env = dict(os.environ)
    for key in getattr(provider, "SANITIZED_ENV_KEYS", set()):
        env.pop(key, None)
    for key, value in env_config.items():
        env[key] = str(resolve_env_path(value, root=root))
    prepare_launch_env = getattr(provider, "prepare_launch_env", None)
    if callable(prepare_launch_env):
        prepare_launch_env(env)
    return env


def resolve_cwd(cwd_mode: str, spec: Dict[str, Any], root: Path = ROOT) -> Path:
    if cwd_mode == "project_root":
        return root
    if cwd_mode == "runtime_dir":
        return runtime_dir_for_root(root)
    if cwd_mode == "custom":
        custom = spec.get("cwd_path", "")
        path = Path(str(custom))
        if not path.is_absolute():
            path = root / path
        return path
    return root
```

- [ ] **Step 4: 在 `run_chunk_agent()` 内固定使用 `current_root = ROOT`，并让 runtime/staging 都从这个根派生**

```python
def run_chunk_agent(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    current_root = ROOT
    provider_name = str(config.get("agent", {}).get("provider", "")).strip()
    provider = get_provider(provider_name)
    if provider is None:
        return {
            "returncode": 2,
            "stdout": "",
            "stderr": "unsupported provider",
            "error_kind": ERROR_KIND_CONFIG_ERROR,
            "prompt": "",
        }

    spec = provider.build_launch_spec(config, chunk)
    cwd = resolve_cwd(str(spec.get("cwd_mode", "project_root")), spec, root=current_root)
    env = build_launch_env(spec.get("env", {}), provider, root=current_root)
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_dir = Path(str(spec.get("staging_dir", "")).strip()) if str(spec.get("staging_dir", "")).strip() else None
    if staging_dir is not None:
        prepare_chunk_staging_dir(staging_dir)

    completed = subprocess.run(
        list(spec.get("argv", [])),
        input=str(spec.get("prompt", "")) if str(spec.get("prompt_via", "stdin")) == "stdin" else None,
        text=True,
        capture_output=True,
        cwd=str(cwd),
        env=env,
        check=False,
    )

    if completed.returncode == 0 and staging_dir is not None:
        runtime_dir = runtime_dir_for_root(current_root)
        imported_paths = import_chunk_staging_artifacts(
            staging_dir,
            chunk_index,
            runtime_dir=runtime_dir,
            results_dir=runtime_dir / "results",
        )
```

- [ ] **Step 5: 运行 `AgentRunnerTests`，确认 staging 和 env 路径只落在临时目录**

Run: `python3 -m unittest tests.test_agent_runner.AgentRunnerTests -v`

Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add .agents/tools/agent_runner.py tests/test_agent_runner.py
git commit -m "fix: resolve runner paths from the active root"
```

### Task 4: 补齐 `opencode` provider 与 `doctor` 诊断闭环

**Files:**
- Modify: `.agents/tools/providers/opencode.py`
- Modify: `.agents/tools/doctor.py`
- Modify: `tests/test_agent_runner.py`
- Modify: `tests/test_doctor.py`
- Test: `tests/test_agent_runner.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: 写失败测试，锁定 `opencode` 的错误分类和诊断语义**

```python
def test_opencode_classify_runtime_error(self) -> None:
    from providers.opencode import classify_runtime_error

    self.assertEqual(classify_runtime_error("Authentication failed"), "auth_error")
    self.assertEqual(classify_runtime_error("dial tcp: connect: connection refused"), "network_error")
    self.assertEqual(classify_runtime_error("POST https://opencode.ai/zen/v1/messages timed out"), "network_error")
    self.assertEqual(classify_runtime_error("Unknown error"), "runtime_error")
```

```python
def test_check_opencode_xdg_dirs_reports_unwritable(self) -> None:
    config = doctor.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "opencode"

    with patch.object(doctor, "_ensure_writable_dir", side_effect=["permission denied", "permission denied"]):
        result = doctor.check_opencode_xdg_dirs(config, root=REPO_ROOT)

    self.assertEqual(result["level"], "error")
    self.assertEqual(result["code"], "opencode_xdg_dirs_unwritable")
```

```python
def test_check_opencode_auth_reports_manual_check(self) -> None:
    config = doctor.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "opencode"

    with patch.dict(os.environ, {}, clear=True), patch.object(doctor.Path, "home", return_value=REPO_ROOT / "missing-home"):
        result = doctor.check_opencode_auth(config, root=REPO_ROOT)

    self.assertEqual(result["level"], "warning")
    self.assertEqual(result["code"], "opencode_auth_manual_check")
```

- [ ] **Step 2: 运行这些测试，确认当前实现尚未覆盖网络关键字和完整诊断边界**

Run: `python3 -m unittest tests.test_agent_runner.OpenCodeProviderTests tests.test_doctor.DoctorTests.test_check_opencode_xdg_dirs_reports_unwritable tests.test_doctor.DoctorTests.test_check_opencode_auth_reports_manual_check -v`

Expected: 至少一个 FAIL，常见原因是错误分类过窄，或 `doctor` 测试夹具尚未显式设置 `opencode`。

- [ ] **Step 3: 扩展 `providers/opencode.py` 的错误分类，覆盖真实 phase 3 文档里的网络特征**

```python
def classify_runtime_error(stderr: str) -> str:
    text = (stderr or "").lower()
    if "auth" in text or "login" in text or "unauthorized" in text or "api key" in text:
        return ERROR_KIND_AUTH_ERROR
    if (
        "network" in text
        or "timeout" in text
        or "timed out" in text
        or "connection refused" in text
        or "dial tcp" in text
        or "zen/v1/messages" in text
    ):
        return ERROR_KIND_NETWORK_ERROR
    return ERROR_KIND_RUNTIME_ERROR
```

- [ ] **Step 4: 在 `doctor.py` 中补一条 `opencode` 网络提示检查，并保留现有注册框架**

```python
def check_opencode_network(config: Any, root: Path = ROOT) -> Dict[str, Any]:
    provider_name = _get_agent_provider_name(config)
    if provider_name != "opencode":
        return make_result(
            "ok",
            "opencode_network_not_applicable",
            "当前 provider 不是 opencode，跳过网络提示检查。",
            f"provider: {provider_name or '未设置'}",
        )

    return make_result(
        "warning",
        "opencode_network_manual_check",
        "OpenCode 真实运行依赖外网访问 opencode 服务。",
        "如出现 connection refused、timeout 或 zen/v1/messages 请求失败，应归类为 network_error 并优先检查网络连通性。",
    )


register_check("opencode", check_opencode_network)
```

- [ ] **Step 5: 让 `tests/test_doctor.py` 覆盖 `opencode` 各检查，并用最小配置隔离场景**

```python
def test_check_opencode_network_reports_manual_check(self) -> None:
    config = doctor.load_json(REPO_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = "opencode"

    result = doctor.check_opencode_network(config, root=REPO_ROOT)

    self.assertEqual(result["level"], "warning")
    self.assertEqual(result["code"], "opencode_network_manual_check")
```

- [ ] **Step 6: 运行 `opencode` 相关测试，确认 provider/doctor 闭环成立**

Run: `python3 -m unittest tests.test_agent_runner.OpenCodeProviderTests tests.test_doctor -v`

Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add .agents/tools/providers/opencode.py .agents/tools/doctor.py tests/test_agent_runner.py tests/test_doctor.py
git commit -m "feat: complete opencode diagnostics and error classification"
```

### Task 5: 同步 README 与 phase 3 文档，并做定向回归

**Files:**
- Modify: `README.md`
- Modify: `docs/superpowers/plans/2026-04-24-opencode-phase3.md`
- Test: `tests/test_agent_runner.py`
- Test: `tests/test_doctor.py`

- [ ] **Step 1: 更新 README 的 provider 配置示例与 `opencode` 目录隔离说明**

```markdown
"opencode": {
  "launch": {
    "argv": ["opencode"],
    "prompt_via": "stdin",
    "cwd": "project_root",
    "env": {},
    "requires_tty": false,
    "output": {
      "mode": "exit_code"
    }
  },
  "capabilities": {
    "non_interactive": true,
    "workspace_write_required": true
  }
}
```

```markdown
- `opencode`：运行时会自动设置 `XDG_DATA_HOME` 和 `XDG_STATE_HOME`，分别指向工作区内的 `.opencode/data` 和 `.opencode/state`。
- `doctor` 会检查上述目录是否可写，并给出认证/网络的有限提示；真实认证仍依赖 OpenCode CLI 的本机配置或环境变量。
- 如果 stderr 中出现 `connection refused`、`timeout` 或 `zen/v1/messages` 请求失败，应按网络问题处理。
```

- [ ] **Step 2: 更新 `2026-04-24-opencode-phase3.md`，把“未实现”项改成当前真实状态**

```markdown
### Task 1: Provider 最小落地与环境目录收口

- [x] `providers/opencode.py` 已创建，并提供 launch spec、XDG 目录隔离和基础错误分类。
- [x] `providers/__init__.py` 已通过自动发现注册 `opencode` provider。
- [x] `tests/test_agent_runner.py` 已覆盖 `opencode` 的 launch spec 与错误分类。
- [ ] 仍需确认真实 `1 issue / 1 chunk` 验收时的网络/认证边界。
```

```markdown
### Task 2: Doctor 诊断补齐

- [x] `doctor.py` 已补充 `opencode` 可执行文件、XDG 目录、认证与网络提示检查。
- [x] `tests/test_doctor.py` 已覆盖目录不可写与认证人工确认场景。
- [ ] 真实 CLI 环境下的验收仍需单独执行，不混入单元测试。
```

- [ ] **Step 3: 运行定向回归，只验证本轮改动面**

Run: `python3 -m unittest tests.test_agent_runner tests.test_doctor -v`

Expected: PASS。

- [ ] **Step 4: Commit**

```bash
git add README.md docs/superpowers/plans/2026-04-24-opencode-phase3.md
git commit -m "docs: sync opencode phase 3 status and provider guidance"
```

## Self-Review

- 规格覆盖：
  - 配置缺口：Task 1
  - 测试隔离：Task 2
  - runner 根目录一致性：Task 3
  - `opencode` 诊断/分类闭环：Task 4
  - README 与 phase 3 文档同步：Task 5
- 占位符扫描：
  - 计划内无 `TODO` / `TBD` / “类似 Task N”。
- 类型一致性：
  - 使用的函数名与现有代码一致：`validate_pipeline_config()`、`build_launch_spec()`、`check_opencode_xdg_dirs()`、`run_chunk_agent()`。
