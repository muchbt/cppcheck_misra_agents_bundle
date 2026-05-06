from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    ROOT,
    AGENTS_DIR,
    CONFIG_DIR,
    SKILLS_DIR,
    AUTO_BLOCK_BEGIN,
    AUTO_BLOCK_END,
    ensure_dirs,
    load_json,
    read_text,
    replace_or_append_marked_block,
    write_text,
)

def ensure_parent_dir(path: Path) -> None:
    parent = path.parent
    if parent.exists() and parent.is_dir():
        return

    current = parent
    while current != ROOT and not current.exists():
        current = current.parent

    if current.exists() and current.is_file():
        if current.name == ".codex" and current.stat().st_size == 0:
            current.unlink()
            current.mkdir(parents=True, exist_ok=True)
        else:
            raise SystemExit(f"Cannot create directory '{parent}': '{current}' is a file.")

    parent.mkdir(parents=True, exist_ok=True)

def build_agents_md_block() -> str:
    return """## Static analysis / cppcheck / MISRA workflow

- Read the current chunk JSON first
- Only process the current chunk
- Only inspect files listed in the current chunk unless strictly necessary
- Apply minimal edits only — change only the lines necessary to resolve each issue; do not reformat, refactor, or restructure surrounding code
- For every code change, add a brief inline comment at the modified line(s) identifying the fixed issue and the fix method, e.g. `/* fix: misra-c2012-11.3 — added explicit cast */`
- Do not do unrelated refactors or formatting
- Do not infer behavior from comments; use actual code/data/control flow
- Follow the current chunk's fix_strategy and each issue's strategy_action
- In conservative mode, auto-fix only when the remediation is local and unambiguous
- In conservative mode, do not automatically modify:
  - interrupt/ISR paths
  - volatile-related logic
  - register access code
  - macro-heavy conditional compilation logic
  - AUTOSAR RTE/MCAL/BSW high-risk paths
  - public interfaces / propagated header changes
- In all_auto mode, high-risk issues may be fixed, but must be marked with risk_level, risk_reason, and review_required_after_fix=true
- Prefer completing work inside the current workspace
- If one issue is blocked, record the blocker and continue with other safe issues in the same chunk
- Do not wait indefinitely for sandbox, tool, or environment side effects; write blockers into runtime state and result files
- Ask users only when explicit authorization is required and no safe workspace-only path exists
- After edits, write the current chunk's staging delta files only (do not overwrite canonical runtime files directly):
  - <staging_dir>/chunk_XXX/issue_status_delta.json
  - <staging_dir>/chunk_XXX/file_change_delta.json
  - <staging_dir>/chunk_XXX/chunk_result.json
  - <staging_dir>/chunk_XXX/chunk_result.md
- Follow the staging output format contract defined in the cppcheck-misra-fix SKILL.md file at `.agents/skills/cppcheck-misra-fix/SKILL.md`
- Keep a clear mapping from issues to edit points via edit_id and related_issue_keys
"""

def sync_agents_md(mode: str, dry_run: bool) -> None:
    agent_map = load_json(CONFIG_DIR / "agent_map.json", {})
    target = ROOT / agent_map["agents"]["codex"]["bootstrap"]["agents_md_target"]

    block = build_agents_md_block()
    existing = read_text(target, "")
    if mode == "overwrite":
        new_content = f"# Project AGENTS\n\n{AUTO_BLOCK_BEGIN}\n{block.rstrip()}\n{AUTO_BLOCK_END}\n"
    else:
        new_content = replace_or_append_marked_block(existing, block)

    changed = existing != new_content
    print(f"[AGENTS.md] target={target} changed={changed} mode={mode} dry_run={dry_run}")
    if changed and not dry_run:
        write_text(target, new_content)

def sync_skill(mode: str, dry_run: bool) -> None:
    agent_map = load_json(CONFIG_DIR / "agent_map.json", {})
    skill_source = SKILLS_DIR / "cppcheck-misra-fix" / "SKILL.md"
    src = read_text(skill_source, "")
    for provider_name, data in sorted(agent_map.get("agents", {}).items()):
        bootstrap = data.get("bootstrap", {}) if isinstance(data, dict) else {}
        skill_target_value = bootstrap.get("skill_target", "")
        if not isinstance(skill_target_value, str) or not skill_target_value.strip():
            continue
        skill_target = ROOT / skill_target_value
        old = read_text(skill_target, "")
        changed = src != old
        print(
            f"[SKILL.md] provider={provider_name} target={skill_target} "
            f"changed={changed} mode={mode} dry_run={dry_run}"
        )
        if changed and not dry_run:
            ensure_parent_dir(skill_target)
            write_text(skill_target, src)

def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap .agents compatibility files.")
    parser.add_argument(
        "--mode",
        choices=["merge", "overwrite"],
        default="merge",
        help="merge: replace/append managed AGENTS.md block; overwrite: rebuild compatible files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned changes without writing files.",
    )
    args = parser.parse_args()

    ensure_dirs()
    sync_agents_md(args.mode, args.dry_run)
    sync_skill(args.mode, args.dry_run)

    compat_agents = AGENTS_DIR / "compat" / "AGENTS.md"
    compat_codex_skill = AGENTS_DIR / "compat" / ".codex" / "skills" / "cppcheck-misra-fix" / "SKILL.md"
    compat_claude_skill = AGENTS_DIR / "compat" / ".claude" / "skills" / "cppcheck-misra-fix" / "SKILL.md"

    if args.dry_run:
        print(f"[DRY-RUN] would sync compat AGENTS to {compat_agents}")
        print(f"[DRY-RUN] would sync compat SKILL to {compat_codex_skill}")
        print(f"[DRY-RUN] would sync compat SKILL to {compat_claude_skill}")
        return

    write_text(compat_agents, read_text(ROOT / "AGENTS.md", ""))
    skill_text = read_text(SKILLS_DIR / "cppcheck-misra-fix" / "SKILL.md", "")
    write_text(compat_codex_skill, skill_text)
    write_text(compat_claude_skill, skill_text)
    print("Bootstrap completed.")
