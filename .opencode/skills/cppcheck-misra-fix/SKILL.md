---
name: cppcheck-misra-fix
description: Process one cppcheck/MISRA chunk at a time, apply minimal safe fixes, record edit points, and verify touched files.
---

# Goal

Fix high-confidence cppcheck and MISRA findings from one chunk at a time.

# Rules

- Only process the current chunk
- Follow the chunk's `fix_strategy` and each issue's `strategy_action`
- In `conservative` mode, prefer local, high-confidence fixes only
- In `all_auto` mode, attempt every issue when a technically valid minimal edit is possible
- Keep edits minimal — change only the lines necessary to resolve each issue; do not reformat, refactor, or restructure surrounding code
- For every code change, add a brief inline comment at the modified line(s) identifying the fixed issue and the fix method, e.g. `/* fix: misra-c2012-11.3 — added explicit cast */` or `/* fix: nullPointer — added NULL guard */`
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
- When `unique_fix_patterns` does NOT contain a pattern for an issue's rule_id:
  - Still add an inline fix comment using the mandatory format: `/* fix: <rule_id> — <action> */`
  - The `<action>` must briefly describe: what the error was, why it occurred, and what was changed — e.g. `/* fix: misra-c2012-8.13 — added const qualifier to pointer parameter (data not modified) */`
  - Prefer the simplest single-line change that resolves the issue
  - Do NOT choose an elaborate fix when a minimal one suffices; do NOT refactor surrounding code
- Do not infer code intent from comments
- For high-risk fixes, keep edits isolated and mark them for human review
- In `conservative` mode, mark high-risk MISRA/volatile/interrupt/register/RTE/MCAL findings as `needs_manual_review`
- Record every independent edit point with issue links
- Update runtime state files after finishing the chunk
- Prefer completing work inside the current workspace
- If one issue is blocked, record the blocker and continue with other safe issues in the same chunk
- Do not wait indefinitely for sandbox, tool, or environment side effects; write blockers into runtime state and result files
- Ask users only when explicit authorization is required and no safe workspace-only path exists

# Required outputs

- fixed issues
- skipped issues
- needs_manual_review
- high-risk fixed issues with risk_level, risk_reason, and review_required_after_fix=true
- touched files
- edit records
- verification results

# Staging output format contract

The staging directory output files must follow these formats:

**issue_status_delta.json:**
- Option A: Flat object `{issue_key: patch}` where patch contains status, risk_level, risk_reason, etc.
- Option B: Wrapper object `{status_changes: [{issue_key, new_status, ...}]}` or `{issue_status_changes: [...]}`

**file_change_delta.json:**
- Option A: Flat object `{file_path: {edits: [...], change_summary: "..."}}` where each key is an actual file path
- Option B: Wrapper array `{file_changes: [{file, summary, linked_issues, edits: [...]}]}` — for chunks with code edits
- Option C: Inspection-only `{files_inspected: [{file, change_summary}]}` — for chunks where NO edits were applied (e.g. manual review)

⚠️ Use ONLY the key names above. Do NOT invent alternative key names (e.g. `changed_files`, `file_edits`).

Keep field names stable and deterministic. Each edit must include `edit_id`, `summary`, `chunk_index`, and `related_issue_keys`.
