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
- Keep edits minimal — change only the lines necessary; do not reformat, refactor, or restructure surrounding code
- Every fix line MUST have: `/* fix: <rule_id> — <action> */` (C block comment, em-dash `—`, past-tense verb phrase)
  - If `unique_fix_patterns` has an `example` for the rule_id, replicate that comment exactly
  - Otherwise keep `<action>` minimal, no trailing periods or extra commentary
  - Never use `//`, hyphen, or double-hyphen as separator
- Process issues in chunk array order (pre-sorted: file path → line number). Fix top-to-bottom, one at a time; same-line issues left-to-right
- Do NOT batch-rewrite a region or reorder issues
- When `unique_fix_patterns` contains a pattern for the rule_id, apply that exact fix — do not choose alternatives
- When no pattern is provided: still add the mandatory `/* fix: ... */` comment; `<action>` should describe error, cause, and change. Prefer simplest single-line fix; do NOT refactor
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
- Option B: Wrapper object with array under one of these keys: `status_changes`, `issue_status_changes`, or `issue_status_delta`
  - Each entry must include `issue_key` and `new_status`
  - Accepted field aliases: `review_required_after_fix` or `requires_review` → normalized to `requires_review_after_fix`; `fix_method` → normalized to `fix_summary`; `status_after` or `status` → normalized to `status`
  - Normalized passthrough fields: `risk_level`, `risk_reason`, `requires_review_after_fix`, `verified`, `fix_summary`
  - Accepted reason aliases: `reason`, `blocker_reason`, `message`

**file_change_delta.json:**
- Option A: Flat object `{file_path: {edits: [...], change_summary: "..."}}` where each key is an actual file path
- Option B: Wrapper array under one of these keys: `file_changes`, `files_changed`, `files_touched`, `changes`, `modified_files`, or `file_edits` — each entry uses `file` (or `file_path`/`path`) to identify the file
- Option C: Inspection-only `{files_inspected: [{file, change_summary}]}` — for chunks where NO edits were applied (e.g. manual review)

⚠️ The normalization layer accepts the aliases above, but prefer canonical key names when possible. Each edit must include `edit_id`, `summary`, `chunk_index`, and `related_issue_keys` (alternatives: `linked_issues` or `linked_issue_keys`).
