# 代码与文档 GAP 分析设计

## 背景

本文档对 cppcheck + MISRA agent pipeline 项目进行全面的代码与文档一致性分析。通过模块对比法，系统性地对比设计文档、用户文档、代码实现，识别出不一致、缺失或过时的内容。

## 分析范围

- **设计文档**：`docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md`
- **计划文档**：`docs/superpowers/plans/2026-04-24-opencode-phase3.md`
- **用户文档**：`README.md`, `AGENTS.md`
- **实现代码**：`.agents/tools/*.py`, `.agents/tools/providers/*.py`
- **配置文件**：`.agents/config/pipeline.json`

## 分析方法

采用模块对比法，按以下维度逐一对比：

1. 设计文档 vs 实现代码
2. README.md vs 实现代码
3. AGENTS.md vs 实现代码
4. Phase 3 计划 vs 当前实现
5. Provider 实现细节
6. 配置文件 vs 文档描述

---

## GAP 分析结果

### 一、设计文档 vs 实现代码 GAP

| 设计文档位置 | 实现代码位置 | GAP 类型 | 详情 |
|-------------|-------------|---------|------|
| 设计文档:53-58 | `oneshot.py` | **部分实现** | 设计要求 `oneshot` 支持 `--resume` 参数（用于脚本中表达意图），但代码未实现该参数。当前默认行为即为续跑，当检测到 `ready/running/partial/failed` 状态时自动恢复执行。**建议**：设计文档中 `--resume` 是可选语义增强，非必需功能，可保持现状或添加显式参数。 |
| 设计文档:68-95 | `common.py`, `merge_results.py` | **已实现** | 归档目录结构设计已实现：`.agents/runs/<run_id>/` 包含 `runtime/`, `reports/`, `logs/`, `run_manifest.json`。 |
| 设计文档:159-168 | `doctor.py` | **已实现** | doctor 预检设计已实现，检查：Python 版本、cppcheck.xml、配置、agent 启动参数、staging 目录、skill 可见性、认证、网络、自定义验证命令、归档大小、prompt 长度。 |
| 设计文档:200-205 | - | **未实现** | 设计提到 `oneshot --run-id` 允许一键入口指定自定义运行 ID。当前代码：`oneshot.py` 支持 `--run-id` 参数，但仅在 `--fresh` 模式下使用，透传给 `split` 阶段。**建议**：已部分实现，文档需更新说明 `--run-id` 仅在 fresh 模式有效。 |
| 设计文档:224-289 | `providers/`, `agent_runner.py` | **已实现** | Task 7 结构化 agent 配置模型已实现：`provider`、`launch.argv`、`launch.prompt_via`、`launch.cwd`、`launch.env`、`launch.requires_tty`、`launch.output.mode`、`capabilities`。 |
| 设计文档:410-422 | `common.py:431-647`, `agent_runner.py:92-108` | **已实现** | staging 模型和导入逻辑已实现：agent 写 staging 目录，runner 在成功后导入到 runtime。 |

### 二、README.md vs 实现代码 GAP

| README 描述位置 | 实现代码位置 | GAP 类型 | 详情 |
|----------------|-------------|---------|------|
| README:97 | `claude.py:11-17` | **文档不准确** | README 说 "Claude Code 会从项目内 `.claude/skills/` 或用户全局 `~/.claude/skills/` 加载 skill"。实际代码：`claude.py` 通过 `--append-system-prompt` CLI 参数注入 `CLAUDE_APPEND_SYSTEM_PROMPT` 内容，而非依赖 skill 文件自动加载。**建议**：更新 README 说明 Claude provider 通过 CLI 参数注入指令，skill 文件作为备用文档。 |
| README:96 | `codex.py:12` | **已实现** | README 说运行时 "会自动移除继承下来的 `CODEX_SANDBOX_NETWORK_DISABLED`"。代码：`codex.py` 定义 `SANITIZED_ENV_KEYS = {"CODEX_SANDBOX_NETWORK_DISABLED"}`，`agent_runner.py:22-31` 的 `build_launch_env()` 在启动前移除该变量。 |
| README:32-74 | `pipeline.json` | **已实现** | agent 配置模型与 README 描述一致，包含 `provider`、`staging_dir`、`providers` 子配置。 |
| README:125 | `oneshot.py:14-15` | **已实现** | 续跑条件 `ready/running/partial/failed` 与代码 `UNFINISHED_STATUSES` 常量一致。 |

### 三、AGENTS.md vs 实现代码 GAP

| AGENTS.md 内容 | 实现代码/配置 | GAP 类型 | 详情 |
|---------------|-------------|---------|------|
| AGENTS.md:24-27 | `fix_chunk_prompt.txt:12-16`, `staging 模型` | **已实现** | 运行态更新路径已改为 staging 目录：`issue_status_delta.json`, `file_change_delta.json`, `chunk_result.json`, `chunk_result.md`。 |
| AGENTS.md:11-18 | `split_cppcheck_xml.py:86-118` | **已实现** | conservative 模式规则与代码 `classify_issue()` 逻辑一致，高风险问题标记为 `needs_manual_review`。 |
| - | `common.py:557-601`, `claude.py:11-17` | **文档缺失** | AGENTS.md 未提及 staging 导入的具体 JSON 格式要求。代码中有两种格式支持：`{issue_key: patch}` flat object 或 `{status_changes: [...]}` wrapper；`{file: data}` flat object 或 `{file_changes: [...]}` wrapper。Claude provider 在 `CLAUDE_APPEND_SYSTEM_PROMPT` 中硬编码了格式说明。**建议**：在 AGENTS.md 或 skill 文档中补充 staging 输出格式契约。 |

### 四、Phase 3 计划 vs 当前实现 GAP

| Phase 3 计划内容 | 当前实现状态 | GAP 类型 | 详情 |
|-----------------|-------------|---------|------|
| Task 1: 创建 `providers/opencode.py` | **未实现** | **计划待执行** | opencode provider 尚未创建，需实现 `build_launch_spec()`, `prepare_launch_env()`, `classify_runtime_error()`。 |
| Task 2: doctor opencode 诊断 | **未实现** | **计划待执行** | `doctor.py` 未包含 opencode 特定检查：可执行入口、本地状态目录、数据目录、网络失败、认证状态。 |
| Task 3: README opencode 配置说明 | **未实现** | **计划待执行** | README 未包含 opencode 的结构化配置、环境隔离、已知限制说明。 |
| Task 4: 设计评估 | **未实现** | **计划待执行** | 需评估当前 `agent.provider` 模型是否足够，或需要区分"执行器 provider"和"模型 provider"。 |
| `XDG_DATA_HOME/XDG_STATE_HOME` 管理 | **未实现** | **计划待执行** | opencode 环境目录收口逻辑尚未实现，需在 `prepare_launch_env()` 中处理。 |

### 五、Provider 实现细节 GAP

| Provider | 文档描述 | 实现代码 | GAP 详情 |
|----------|---------|---------|---------|
| `codex.py` | README:95 描述认证复用 | `codex.py:14-35` `prepare_launch_env()` | **已实现**：代码通过 symlink/copy 将 `~/.codex/auth.json` 和 `~/.codex/config.toml` 同步到工作区 `CODEX_HOME`。 |
| `claude.py` | README:97 描述 skill 加载 | `claude.py:38-41` `--append-system-prompt` | **不一致**：README 说 skill 自动加载，但代码通过 CLI 参数注入硬编码指令。指令内容包含 staging 输出格式契约，但 skill 文档 `SKILL.md` 未包含这些格式要求。 |
| `claude.py` | AGENTS.md skill 内容 | `claude.py:11-17` `CLAUDE_APPEND_SYSTEM_PROMPT` | **内容分离**：Claude provider 的实际行为指令在代码中硬编码，与 `.agents/skills/cppcheck-misra-fix/SKILL.md` 内容不完全一致。 |

### 六、配置文件 vs 文档描述 GAP

| pipeline.json 字段 | 文档描述 | GAP 类型 |
|-------------------|---------|---------|
| `agent.providers.claude.launch` | README:56-70 描述 | **已实现**，配置与文档一致 |
| `verification.custom_command` | README:232-236 说明 | **已实现**，doctor 检查存在 |
| `agent.launch.env` | README 未明确说明 provider 差异 | **设计差异**：`claude` provider `env` 为空，`codex` 有 `CODEX_HOME`。文档未说明不同 provider 的 env 配置策略差异。**建议**：补充说明各 provider 的环境变量配置策略。 |

---

## 关键发现总结

### 高优先级 GAP（影响功能准确性）

1. **GAP-001: Claude provider skill 加载机制不一致**
   - **位置**：README:97 vs claude.py:38-41
   - **问题**：README 描述 skill 自动加载，实际通过 CLI 参数注入
   - **建议**：更新 README 说明 Claude provider 的实际行为
   - **状态：已修复**（Task 1, commit b6a51d1）

2. **GAP-002: Staging 输出格式契约未文档化**
   - **位置**：claude.py:11-17 CLAUDE_APPEND_SYSTEM_PROMPT
   - **问题**：JSON 格式要求在代码中硬编码，AGENTS.md 和 skill 文档未包含
   - **建议**：将格式契约写入 skill 文档或 AGENTS.md
   - **状态：已修复**（Task 2, commits 5ff544c, 383ac8d）

3. **GAP-003: OpenCode provider 整体未实现**
   - **位置**：docs/superpowers/plans/2026-04-24-opencode-phase3.md
   - **问题**：Phase 3 计划 Task 1-4 均未实现
   - **建议**：按计划执行实现

### 中优先级 GAP（影响可维护性）

4. **GAP-004: AGENTS.md 未反映 staging 导入格式**
   - **位置**：common.py:557-601 vs AGENTS.md
   - **问题**：代码支持多种格式（flat/wrapper），文档未说明
   - **建议**：在 AGENTS.md 补充格式说明

5. **GAP-005: Provider 环境配置策略差异未文档化**
   - **位置**：pipeline.json:56-91
   - **问题**：codex 有 CODEX_HOME，claude env 为空，README 未解释差异原因
   - **建议**：在 README 补充各 provider 环境配置策略说明
   - **状态：已修复**（Task 3, commit 7c90d3f）

### 低优先级 GAP（已实现但文档可改进）

6. **GAP-006: oneshot --resume 参数未实现**
   - **位置**：设计文档:53-58 vs oneshot.py
   - **问题**：设计提到 `--resume` 参数，代码未实现（默认行为即为续跑）
   - **建议**：设计文档标注为可选语义增强，非必需功能
   - **状态：已修复**（Task 5, commit 655cb77）

7. **GAP-007: oneshot --run-id 限制未文档化**
   - **位置**：设计文档:200-205 vs README
   - **问题**：`--run-id` 仅在 `--fresh` 模式有效，README 未明确说明
   - **建议**：README 补充说明限制条件
   - **状态：已修复**（Task 4, commit 30e0657）

---

## 建议修复顺序

### 第一阶段：文档更新（低成本）

1. 更新 README 说明 Claude provider 实际行为（GAP-001）
2. 补充 staging 输出格式契约到 skill 文档（GAP-002）
3. 补充 oneshot --run-id 限制说明（GAP-007）
4. 补充 provider 环境配置策略差异说明（GAP-005）

### 第二阶段：代码完善

5. 实现 OpenCode provider（GAP-003）
6. 实现 doctor opencode 诊断

### 第三阶段：可选增强

7. 添加 oneshot --resume 参数（GAP-006）
8. 实现 oneshot 直接支持 --run-id（设计文档:200-205）

---

## 附录：文件对照表

| 文档文件 | 对应实现文件 |
|---------|-------------|
| `README.md` | `.agents/tools/*.py`, `.agents/config/pipeline.json` |
| `AGENTS.md` | `.agents/tools/split_cppcheck_xml.py`, `.agents/prompts/fix_chunk_prompt.txt` |
| `docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md` | `oneshot.py`, `doctor.py`, `agent_runner.py`, `common.py`, `merge_results.py` |
| `docs/superpowers/plans/2026-04-24-opencode-phase3.md` | `.agents/tools/providers/` (待实现 opencode.py) |
| `.agents/skills/cppcheck-misra-fix/SKILL.md` | `.agents/prompts/fix_chunk_prompt.txt` |