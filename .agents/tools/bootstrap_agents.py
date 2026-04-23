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

def build_agents_md_block() -> str:
    return """## Static analysis / cppcheck / MISRA workflow

- Read the current chunk JSON first
- Only process the current chunk
- Only inspect files listed in the current chunk unless strictly necessary
- Apply minimal edits only
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
- After edits, update:
  - .agents/runtime/issue_status.json
  - .agents/runtime/file_change_index.json
  - .agents/runtime/results/chunk_XXX_result.json
- Keep a clear mapping from issues to edit points
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
    skill_target = ROOT / agent_map["agents"]["codex"]["bootstrap"]["skill_target"]
    skill_source = SKILLS_DIR / "cppcheck-misra-fix" / "SKILL.md"
    src = read_text(skill_source, "")
    old = read_text(skill_target, "")
    changed = src != old
    print(f"[SKILL.md] target={skill_target} changed={changed} mode={mode} dry_run={dry_run}")
    if changed and not dry_run:
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
    compat_skill = AGENTS_DIR / "compat" / ".codex" / "skills" / "cppcheck-misra-fix" / "SKILL.md"

    if args.dry_run:
        print(f"[DRY-RUN] would sync compat AGENTS to {compat_agents}")
        print(f"[DRY-RUN] would sync compat SKILL to {compat_skill}")
        return

    write_text(compat_agents, read_text(ROOT / "AGENTS.md", ""))
    write_text(compat_skill, read_text(SKILLS_DIR / "cppcheck-misra-fix" / "SKILL.md", ""))
    print("Bootstrap completed.")

if __name__ == "__main__":
    main()
