<!-- BEGIN AUTO-GENERATED: cppcheck-misra-fix -->
## Static analysis / cppcheck / MISRA workflow

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
- Prefer completing work inside the current workspace
- If one issue is blocked, record the blocker and continue with other safe issues in the same chunk
- Do not wait indefinitely for sandbox, tool, or environment side effects; write blockers into runtime state and result files
- Ask users only when explicit authorization is required and no safe workspace-only path exists
- After edits, write the current chunk's staging delta files only (do not overwrite canonical runtime files directly):
  - <staging_dir>/chunk_XXX/issue_status_delta.json
  - <staging_dir>/chunk_XXX/file_change_delta.json
  - <staging_dir>/chunk_XXX/chunk_result.json
  - <staging_dir>/chunk_XXX/chunk_result.md
- Follow the staging output format contract defined in the cppcheck-misra-fix SKILL.md
- Keep a clear mapping from issues to edit points via edit_id and related_issue_keys
<!-- END AUTO-GENERATED: cppcheck-misra-fix -->
