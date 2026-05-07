# Project AGENTS

<!-- BEGIN AUTO-GENERATED: cppcheck-misra-fix -->
## Static analysis / cppcheck / MISRA workflow

- Read the current chunk JSON first
- Only process the current chunk
- Only inspect files listed in the current chunk unless strictly necessary
- Apply minimal edits only — change only the lines necessary to resolve each issue; do not reformat, refactor, or restructure surrounding code
- For every code change, add a brief inline comment at the modified line(s) identifying the fixed issue and the fix method, e.g. `/* fix: misra-c2012-11.3 — added explicit cast */`
- Inline fix comments MUST use exactly this format: `/* fix: <rule_id> — <action> */`
  - Use C block comment `/* */`, never C++ line comment `//`
  - Use em-dash `—` as separator, not hyphen `-` or double-hyphen `--`
  - `<action>` must be a short past-tense verb phrase, e.g. `added explicit cast`, `removed unused variable`, `added NULL guard`
  - If `unique_fix_patterns` provides an `example` for the rule_id, replicate its comment text exactly
  - Do NOT add extra commentary, trailing periods, or alternative phrasings
- Process issues strictly in chunk JSON array order (issues are pre-sorted by file path then line number ascending)
- Within each file, apply fixes top-to-bottom by line number — never jump ahead or reorder
- When multiple issues affect the same line, fix them left-to-right in the order they appear in the issues array
- Do NOT batch-rewrite a file region; apply one issue's fix at a time in sequence
- When `unique_fix_patterns` contains a pattern for an issue's rule_id, apply that exact fix approach — do not choose an alternative method
- When no pattern is provided, prefer the simplest single-line change that resolves the issue
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
<!-- END AUTO-GENERATED: cppcheck-misra-fix -->
