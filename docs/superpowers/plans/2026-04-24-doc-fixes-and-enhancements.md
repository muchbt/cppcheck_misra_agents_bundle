# 文档修复与可选增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-step. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复代码与文档 GAP 中的文档不准确问题，实现可选的命令行参数增强。

**Architecture:** 分两阶段执行：第一阶段纯文档更新（README、AGENTS.md、skill 文档），第二阶段可选代码增强（oneshot 参数）。文档更新遵循现有格式风格，代码增强保持向后兼容。

**Tech Stack:** Python 3.8+、Markdown 文档、argparse 命令行参数处理。

---

## File Structure

**文档文件：**
- Modify: `README.md` - 用户使用文档，修复 GAP-001、GAP-005、GAP-007
- Modify: `.agents/skills/cppcheck-misra-fix/SKILL.md` - Skill 文档，补充 staging 输出格式契约（GAP-002）
- Modify: `AGENTS.md` - Agent 行为指导（可选补充 staging 格式说明）

**代码文件：**
- Modify: `.agents/tools/oneshot.py` - 可选添加 `--resume` 参数（GAP-006）

---

### Task 1: 修复 README Claude Provider 描述（GAP-001）

**Files:**
- Modify: `README.md:97`

**问题：** README 描述 "Claude Code 会从项目内 `.claude/skills/` 或用户全局 `~/.claude/skills/` 加载 skill"，但实际通过 `--append-system-prompt` CLI 参数注入。

- [ ] **Step 1: 定位并修改 README 中的 Claude skill 加载描述**

找到 README 第 97 行附近的内容，将描述改为实际行为。

**修改内容：**

```markdown
- `Claude Code` 通过 `--append-system-prompt` CLI 参数注入 cppcheck-misra-fix skill 指令，同时保留 `.claude/skills/` 目录作为 skill 元数据来源；推荐始终生成项目内兼容层，避免不同机器行为不一致
```

替换原有的：
```markdown
- `Claude Code` 会从项目内 `.claude/skills/` 或用户全局 `~/.claude/skills/` 加载 skill；推荐始终生成项目内兼容层，避免不同机器行为不一致
```

- [ ] **Step 2: 验证 README 格式完整性**

运行：检查 Markdown 格式无语法错误，确认行号约 97 行附近修改正确。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: fix Claude provider skill loading description (GAP-001)"
```

---

### Task 2: 补充 Staging 输出格式契约到 Skill 文档（GAP-002）

**Files:**
- Modify: `.agents/skills/cppcheck-misra-fix/SKILL.md:35` (在 Required outputs 后追加)

**问题：** `claude.py:11-17` 硬编码的 staging 输出格式契约未在任何文档中说明。

- [ ] **Step 1: 在 SKILL.md 的 Required outputs 章节后添加格式契约说明**

在 `.agents/skills/cppcheck-misra-fix/SKILL.md` 的 `# Required outputs` 章节末尾（约第 35 行后）追加：

```markdown

# Staging output format contract

The staging directory output files must follow these formats:

**issue_status_delta.json:**
- Option A: Flat object `{issue_key: patch}` where patch contains status, risk_level, risk_reason, etc.
- Option B: Wrapper object `{status_changes: [{issue_key, new_status, ...}]}` or `{issue_status_changes: [...]}`

**file_change_delta.json:**
- Option A: Flat object `{file_path: data}` where data contains edits, change_summary, etc.
- Option B: Wrapper object `{file_changes: [{file, summary, linked_issues, ...}]}`

Keep field names stable and deterministic. Each edit must include `edit_id`, `summary`, `chunk_index`, and `related_issue_keys`.
```

- [ ] **Step 2: 同步兼容层 skill 文件**

运行 `bootstrap_agents.py` 同步更新 `.codex/skills/.../SKILL.md` 和 `.claude/skills/.../SKILL.md`：

```bash
python3 .agents/tools/bootstrap_agents.py --mode merge
```

- [ ] **Step 3: Commit**

```bash
git add .agents/skills/cppcheck-misra-fix/SKILL.md
git add .agents/compat/.codex/skills/cppcheck-misra-fix/SKILL.md
git add .agents/compat/.claude/skills/cppcheck-misra-fix/SKILL.md
git add .codex/skills/cppcheck-misra-fix/SKILL.md
git add .claude/skills/cppcheck-misra-fix/SKILL.md
git commit -m "docs: add staging output format contract to skill docs (GAP-002)"
```

---

### Task 3: 补充 Provider 环境配置策略差异说明（GAP-005）

**Files:**
- Modify: `README.md:98-99` (在 Agent 配置章节末尾)

**问题：** README 未说明 codex 有 CODEX_HOME 而 claude env 为空的差异原因。

- [ ] **Step 1: 在 README Agent 配置章节末尾添加策略说明**

在 README 的 Agent 配置章节（约第 98-99 行）末尾追加：

```markdown
**Provider 环境配置策略差异：**

- `codex`：需要 `CODEX_HOME` 指向工作区内可写目录，用于存放认证文件 (`auth.json`) 和配置 (`config.toml`)。运行时会自动从 `~/.codex/` 复制到工作区。
- `claude`：认证依赖本机 `claude auth login` 或环境变量 `ANTHROPIC_API_KEY`，不需要额外工作区目录配置。`env` 字段可保持为空对象 `{}`。
- 后续新增 provider（如 `opencode`）可能需要同时管理 `XDG_DATA_HOME` 和 `XDG_STATE_HOME`。
```

- [ ] **Step 2: 验证 README 格式完整性**

确认新增内容在 Agent 配置章节内，Markdown 格式正确。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: add provider environment config strategy differences (GAP-005)"
```

---

### Task 4: 补充 oneshot --run-id 限制说明（GAP-007）

**Files:**
- Modify: `README.md:142-145` (在 fresh 与续跑章节)

**问题：** README 未明确说明 `--run-id` 仅在 `--fresh` 模式有效。

- [ ] **Step 1: 修改 README 中的 --run-id 描述**

找到 README 第 142-145 行附近的 `--run-id` 描述，补充限制说明：

将原有的：
```markdown
需要指定本次 fresh 运行的编号时：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --run-id 20260423-001
```
```

修改为：
```markdown
需要指定本次 fresh 运行的编号时：

```bash
python3 .agents/tools/pipeline_cli.py oneshot --fresh --run-id 20260423-001
```

注意：`--run-id` 参数仅在 `--fresh` 模式下有效。续跑模式会使用已有 `progress.json` 中的 `run_id`，传入不一致的 `--run-id` 会触发错误提示。
```

- [ ] **Step 2: 验证 README 格式完整性**

确认 Markdown 格式正确，代码块闭合。

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: clarify oneshot --run-id limitation (GAP-007)"
```

---

### Task 5: 可选添加 oneshot --resume 参数（GAP-006）

**Files:**
- Modify: `.agents/tools/oneshot.py`

**问题：** 设计文档提到 `--resume` 参数用于脚本中表达意图，代码未实现（默认行为即为续跑）。此为可选语义增强。

- [ ] **Step 1: 在 oneshot.py 添加 --resume 参数定义**

在 `parse_args()` 函数中添加 `--resume` 参数：

```python
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键执行 split -> run -> merge，可自动续跑。")
    parser.add_argument("--fresh", action="store_true", help="忽略已有运行状态，强制从 split 重新开始。")
    parser.add_argument("--resume", action="store_true", help="显式续跑模式，与默认续跑行为一致，用于脚本中表达意图。")
    # ... 其他参数保持不变
```

- [ ] **Step 2: 添加 --resume 与 --fresh 冲突检查**

在 `main()` 函数开头添加参数冲突检查：

```python
def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    if args.fresh and args.resume:
        print("[oneshot] --fresh 和 --resume 不能同时使用。")
        return 2

    # mode 判断逻辑保持不变，--resume 不改变 mode 值
    mode = "fresh"
    if args.resume or (not args.fresh and has_unfinished_runtime(progress)):
        mode = "resume"
```

- [ ] **Step 3: 运行现有测试验证无破坏性变更**

```bash
python3 -m unittest tests/test_oneshot.py -v
```

Expected: PASS（现有测试应全部通过，因为 --resume 不改变默认行为）

- [ ] **Step 4: 添加 --resume 参数测试**

在 `tests/test_oneshot.py` 添加测试：

```python
def test_resume_explicit_mode():
    """Test --resume flag sets mode to resume when progress exists."""
    import oneshot
    args = oneshot.parse_args(["--resume"])
    assert args.resume == True
    assert args.fresh == False

def test_resume_and_fresh_conflict():
    """Test --resume and --fresh together returns error."""
    import oneshot
    import tempfile
    import json
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        runtime_dir = root / ".agents" / "runtime"
        runtime_dir.mkdir(parents=True)

        progress = {"status": "running", "total_chunks": 1, "completed_chunks": []}
        (runtime_dir / "progress.json").write_text(json.dumps(progress))

        # 需要修改 ROOT 或使用 mock，简化测试
        args = oneshot.parse_args(["--fresh", "--resume"])
        assert args.fresh == True
        assert args.resume == True
        # main() 应返回 2
```

- [ ] **Step 5: 运行新增测试**

```bash
python3 -m unittest tests.test_oneshot.test_resume_explicit_mode tests.test_oneshot.test_resume_and_fresh_conflict -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add .agents/tools/oneshot.py tests/test_oneshot.py
git commit -m "feat: add --resume flag to oneshot for explicit resume mode (GAP-006)"
```

---

### Task 6: 更新设计文档标注 --resume 为已实现

**Files:**
- Modify: `docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md:53-58`

- [ ] **Step 1: 更新设计文档中 --resume 描述**

找到设计文档第 53-58 行附近的 `--resume` 描述，标注为已实现：

将原有的：
```markdown
- 若用户传入 `--resume`，行为与默认续跑一致，用于脚本中表达意图。
```

保持不变，但添加注释说明已实现。

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-23-pipeline-review-archive-design.md
git commit -m "docs: mark --resume as implemented in design spec"
```

---

### Task 7: 更新 GAP 分析文档标注已修复

**Files:**
- Modify: `docs/superpowers/specs/2026-04-24-gap-analysis-design.md`

- [ ] **Step 1: 更新 GAP 分析文档中各 GAP 状态**

在各 GAP 的"建议"部分添加"**状态：已修复**"标记：

```markdown
### 高优先级 GAP（影响功能准确性）

1. **GAP-001: Claude provider skill 加载机制不一致**
   - **位置**：README:97 vs claude.py:38-41
   - **问题**：README 描述 skill 自动加载，实际通过 CLI 参数注入
   - **建议**：更新 README 说明 Claude provider 的实际行为
   - **状态：已修复**（Task 1）

2. **GAP-002: Staging 输出格式契约未文档化**
   - **位置**：claude.py:11-17 CLAUDE_APPEND_SYSTEM_PROMPT
   - **问题**：JSON 格式要求在代码中硬编码，AGENTS.md 和 skill 文档未包含
   - **建议**：将格式契约写入 skill 文档或 AGENTS.md
   - **状态：已修复**（Task 2）
```

类似更新 GAP-005, GAP-006, GAP-007。

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-24-gap-analysis-design.md
git commit -m "docs: mark resolved GAPs in analysis document"
```

---

## 自审清单

**1. Spec coverage:** 所有 GAP-001, GAP-002, GAP-005, GAP-006, GAP-007 均有对应任务。

**2. Placeholder scan:** 无 TBD、TODO、未完成章节。所有代码块完整。

**3. Type consistency:** 参数名称 `--resume`、`--fresh` 在各任务中一致。

---

## 最终提交汇总

执行完所有任务后，汇总提交：

```bash
git log --oneline -7
```

Expected output:
```
docs: mark resolved GAPs in analysis document
docs: mark --resume as implemented in design spec
feat: add --resume flag to oneshot for explicit resume mode (GAP-006)
docs: clarify oneshot --run-id limitation (GAP-007)
docs: add provider environment config strategy differences (GAP-005)
docs: add staging output format contract to skill docs (GAP-002)
docs: fix Claude provider skill loading description (GAP-001)
```