from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from common import REPORTS_DIR, RUNTIME_DIR, load_json, read_text, save_json

def main() -> None:
    issue_status = load_json(RUNTIME_DIR / "issue_status.json", {})
    file_change_index = load_json(RUNTIME_DIR / "file_change_index.json", {})

    status_counts = Counter()
    fixed_by_rule = Counter()
    fixed_by_file = Counter()
    strategy_counts = Counter()
    fixed_high_risk = []
    review_required_after_fix = []

    for issue_key, item in issue_status.items():
        status = item.get("status", "unknown")
        status_counts[status] += 1
        strategy_counts[item.get("fix_strategy", "unknown")] += 1
        if status == "fixed":
            fixed_by_rule[item.get("rule_id", "")] += 1
            fixed_by_file[item.get("file", "")] += 1
            if item.get("risk_level") == "high":
                fixed_high_risk.append(issue_key)
            if item.get("requires_review_after_fix"):
                review_required_after_fix.append(issue_key)

    summary = {
        "total_issues": len(issue_status),
        "status_counts": dict(status_counts),
        "strategy_counts": dict(strategy_counts),
        "fixed_high_risk_count": len(fixed_high_risk),
        "review_required_after_fix_count": len(review_required_after_fix),
        "fixed_high_risk": fixed_high_risk,
        "review_required_after_fix": review_required_after_fix,
        "fixed_by_rule": dict(fixed_by_rule),
        "fixed_by_file": dict(fixed_by_file),
        "touched_files": sorted(file_change_index.keys()),
    }
    save_json(REPORTS_DIR / "final_summary.json", summary)

    lines = [
        "# Final Summary",
        "",
        f"- Total issues: {len(issue_status)}",
        f"- Fixed: {status_counts.get('fixed', 0)}",
        f"- Fixed high risk: {len(fixed_high_risk)}",
        f"- Review required after fix: {len(review_required_after_fix)}",
        f"- Skipped: {status_counts.get('skipped', 0)}",
        f"- Needs manual review: {status_counts.get('needs_manual_review', 0)}",
        f"- Failed: {status_counts.get('failed', 0)}",
        "",
        "## Strategy counts",
    ]
    for strategy, count in strategy_counts.most_common():
        lines.append(f"- {strategy}: {count}")

    lines += ["", "## Review required after fix"]
    if review_required_after_fix:
        for issue_key in review_required_after_fix:
            item = issue_status.get(issue_key, {})
            lines.append(
                f"- {issue_key}: {item.get('risk_reason', '')} "
                f"(file={item.get('file', '')}, rule={item.get('rule_id', '')})"
            )
    else:
        lines.append("- None")

    lines += [
        "",
        "## Fixed by rule",
    ]
    for rule_id, count in fixed_by_rule.most_common():
        lines.append(f"- {rule_id}: {count}")

    lines += ["", "## Fixed by file"]
    for file_path, count in fixed_by_file.most_common():
        lines.append(f"- {file_path}: {count}")

    (REPORTS_DIR / "final_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    patch_lines = ["# Final Patch Index", ""]
    for file_path, data in sorted(file_change_index.items()):
        patch_lines.append(f"## {file_path}")
        for edit in data.get("edits", []):
            patch_lines.append(
                f"- {edit.get('edit_id')}: {edit.get('summary', '')} "
                f"(chunk {edit.get('chunk_index')}, issues={len(edit.get('related_issue_keys', []))})"
            )
        patch_lines.append("")
    (REPORTS_DIR / "final_patch_index.md").write_text("\n".join(patch_lines), encoding="utf-8")
    print("Summary generated.")

if __name__ == "__main__":
    main()
