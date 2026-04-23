from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from common import (
    CONFIG_DIR,
    REPORTS_DIR,
    RUNTIME_DIR,
    RUNS_DIR,
    copy_current_run_archive,
    ensure_dirs,
    load_json,
    now_iso,
    save_json,
    write_text,
)


def collect_summary(
    issue_status: Dict[str, Any], file_change_index: Dict[str, Any], progress: Dict[str, Any]
) -> Dict[str, Any]:
    status_counts = Counter()
    strategy_counts = Counter()
    fixed_by_rule = Counter()
    fixed_by_file = Counter()
    fixed_high_risk: List[str] = []
    review_required_after_fix: List[str] = []

    for issue_key, item in issue_status.items():
        status = str(item.get("status", "unknown"))
        status_counts[status] += 1
        strategy_counts[str(item.get("fix_strategy", "unknown"))] += 1
        if status == "fixed":
            fixed_by_rule[str(item.get("rule_id", ""))] += 1
            fixed_by_file[str(item.get("file", ""))] += 1
            if item.get("risk_level") == "high":
                fixed_high_risk.append(issue_key)
            if item.get("requires_review_after_fix"):
                review_required_after_fix.append(issue_key)

    verification_entries: List[Dict[str, Any]] = []
    verification_modes = Counter()
    verification_passed = 0
    verification_failed = 0
    verification_custom_ran = False
    results_dir = RUNTIME_DIR / "results"
    for path in sorted(results_dir.glob("chunk_*_result.json")):
        result = load_json(path, {})
        verification = result.get("verification", {})
        if not isinstance(verification, dict) or not verification:
            continue
        verification_entries.append(verification)
        verification_modes[str(verification.get("mode", "unknown"))] += 1
        if verification.get("passed"):
            verification_passed += 1
        else:
            verification_failed += 1
        if str(verification.get("command", "")).strip():
            verification_custom_ran = True

    total_chunks = int(progress.get("total_chunks", 0))
    completed_chunks = list(progress.get("completed_chunks", []))
    failed_chunks = list(progress.get("failed_chunks", []))

    return {
        "run_id": str(progress.get("run_id", "")).strip(),
        "started_at": str(progress.get("started_at", "")).strip(),
        "finished_at": str(progress.get("last_chunk_finished_at", "")).strip() or now_iso(),
        "status": str(progress.get("status", "")).strip(),
        "input_xml": str(progress.get("xml_file", "")).strip(),
        "strategy": str(progress.get("fix_strategy", "")).strip(),
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
        "chunk_counts": {
            "total": total_chunks,
            "completed": len(completed_chunks),
            "failed": len(failed_chunks),
        },
        "completed_chunks": completed_chunks,
        "failed_chunks": failed_chunks,
        "verification": {
            "total": len(verification_entries),
            "passed": verification_passed,
            "failed": verification_failed,
            "modes": dict(verification_modes),
            "custom_command_ran": verification_custom_ran,
        },
    }


def build_review_markdown(
    summary: Dict[str, Any], issue_status: Dict[str, Any], file_change_index: Dict[str, Any]
) -> str:
    status_counts = summary["status_counts"]
    chunk_counts = summary["chunk_counts"]
    verification = summary["verification"]
    lines = [
        "# 运行总结",
        "",
        f"- 运行编号：{summary.get('run_id') or '未记录'}",
        f"- 输入 XML：{summary.get('input_xml') or '未记录'}",
        f"- 修复策略：{summary.get('strategy') or '未记录'}",
        f"- 开始时间：{summary.get('started_at') or '未记录'}",
        f"- 完成时间：{summary.get('finished_at') or '未记录'}",
        f"- 运行状态：{summary.get('status') or '未记录'}",
        "",
        "## 问题汇总",
        f"- 总问题数：{summary['total_issues']}",
        f"- 已修复：{status_counts.get('fixed', 0)}",
        f"- 已跳过：{status_counts.get('skipped', 0)}",
        f"- 需人工复核（needs manual review）：{status_counts.get('needs_manual_review', 0)}",
        f"- 执行失败：{status_counts.get('failed', 0)}",
        "",
        "## Chunk 汇总",
        f"- 总 chunk 数：{chunk_counts.get('total', 0)}",
        f"- 已完成 chunk：{chunk_counts.get('completed', 0)}",
        f"- 失败 chunk：{chunk_counts.get('failed', 0)}",
        "",
        "## 验证汇总",
        f"- 已记录验证结果：{verification.get('total', 0)}",
    ]

    if verification.get("custom_command_ran"):
        lines.append(f"- 工程级验证通过：{verification.get('passed', 0)}")
        lines.append(f"- 工程级验证失败：{verification.get('failed', 0)}")
        mode_labels = ", ".join(
            f"{mode}={count}" for mode, count in sorted(verification.get("modes", {}).items())
        )
        lines.append(f"- 工程级验证：已执行；模式统计：{mode_labels or '无'}")
    else:
        lines.append(
            f"- 轻量验证记录：通过 {verification.get('passed', 0)}，失败 {verification.get('failed', 0)}"
        )
        lines.append("- 工程级验证：未执行工程级验证")

    lines.extend(
        [
            "",
            "## 人工复核重点",
            f"- 高风险已修复：{summary.get('fixed_high_risk_count', 0)}",
            f"- 修复后仍需复核：{summary.get('review_required_after_fix_count', 0)}",
        ]
    )
    if summary.get("review_required_after_fix"):
        for issue_key in summary["review_required_after_fix"]:
            item = issue_status.get(issue_key, {})
            lines.append(
                f"- {issue_key}：{item.get('risk_reason', '未提供原因')} "
                f"(文件：{item.get('file', '')}，规则：{item.get('rule_id', '')})"
            )
    else:
        lines.append("- 本次未出现“修复后仍需复核”的问题。")

    lines.extend(["", "## 修改文件"])
    if summary.get("touched_files"):
        for file_path in summary["touched_files"]:
            edit_count = len(file_change_index.get(file_path, {}).get("edits", []))
            lines.append(f"- {file_path}：{edit_count} 处修改")
    else:
        lines.append("- 本次没有记录到文件修改。")

    return "\n".join(lines) + "\n"


def build_review_checklist(
    summary: Dict[str, Any], issue_status: Dict[str, Any], file_change_index: Dict[str, Any]
) -> str:
    lines = [
        "# 人工复核清单",
        "",
        "| issue_key | 文件 | 规则 | 状态 | edit_ids | 复核原因 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    rows: List[str] = []
    review_statuses = {"needs_manual_review", "failed"}
    for issue_key in summary.get("review_required_after_fix", []):
        item = issue_status.get(issue_key, {})
        edit_ids = ", ".join(item.get("edit_ids", [])) or "-"
        rows.append(
            f"| {issue_key} | {item.get('file', '')} | {item.get('rule_id', '')} | "
            f"{item.get('status', '')} | {edit_ids} | 修复后仍需人工确认 |"
        )

    for issue_key, item in sorted(issue_status.items()):
        if item.get("status") not in review_statuses:
            continue
        edit_ids = ", ".join(item.get("edit_ids", [])) or "-"
        reason = item.get("risk_reason", "") or "未自动修复，需人工确认"
        rows.append(
            f"| {issue_key} | {item.get('file', '')} | {item.get('rule_id', '')} | "
            f"{item.get('status', '')} | {edit_ids} | {reason} |"
        )

    if not rows:
        rows.append("| - | - | - | - | - | 本次没有需人工复核的条目 |")

    lines.extend(rows)
    lines.extend(["", "## 修改点索引"])
    if file_change_index:
        for file_path, data in sorted(file_change_index.items()):
            lines.append(f"- 文件：{file_path}")
            for edit in data.get("edits", []):
                edit_id = edit.get("edit_id", "")
                summary_text = edit.get("summary", "")
                chunk_index = edit.get("chunk_index", "")
                related = ", ".join(edit.get("related_issue_keys", [])) or "-"
                lines.append(
                    f"  - {edit_id}：{summary_text}；chunk={chunk_index}；关联问题={related}"
                )
    else:
        lines.append("- 没有记录到修改点。")

    return "\n".join(lines) + "\n"


def write_run_manifest(archive_dir: Path, summary: Dict[str, Any], progress: Dict[str, Any]) -> Dict[str, Any]:
    archived_at = now_iso()
    manifest = {
        "run_id": summary.get("run_id") or archive_dir.name,
        "started_at": summary.get("started_at") or str(progress.get("started_at", "")).strip(),
        "finished_at": summary.get("finished_at") or str(progress.get("last_chunk_finished_at", "")).strip(),
        "archived_at": archived_at,
        "input_xml": summary.get("input_xml") or str(progress.get("xml_file", "")).strip(),
        "strategy": summary.get("strategy") or str(progress.get("fix_strategy", "")).strip(),
        "issue_counts": {
            "total": summary.get("total_issues", 0),
            "fixed": summary.get("status_counts", {}).get("fixed", 0),
            "skipped": summary.get("status_counts", {}).get("skipped", 0),
            "needs_manual_review": summary.get("status_counts", {}).get("needs_manual_review", 0),
            "failed": summary.get("status_counts", {}).get("failed", 0),
        },
        "chunk_counts": summary.get("chunk_counts", {}),
        "completed_chunks": summary.get("completed_chunks", []),
        "failed_chunks": summary.get("failed_chunks", []),
        "report_paths": {
            "final_summary_md": ".agents/reports/final_summary.md",
            "final_summary_json": ".agents/reports/final_summary.json",
            "review_checklist_md": ".agents/reports/review_checklist.md",
            "run_manifest_json": ".agents/reports/run_manifest.json",
        },
    }
    save_json(archive_dir / "reports" / "run_manifest.json", manifest)
    return manifest


def main() -> int:
    ensure_dirs()
    config = load_json(CONFIG_DIR / "pipeline.json", {})
    issue_status = load_json(RUNTIME_DIR / "issue_status.json", {})
    file_change_index = load_json(RUNTIME_DIR / "file_change_index.json", {})
    progress = load_json(RUNTIME_DIR / "progress.json", {})

    summary = collect_summary(issue_status, file_change_index, progress)
    save_json(REPORTS_DIR / "final_summary.json", summary)
    write_text(REPORTS_DIR / "final_summary.md", build_review_markdown(summary, issue_status, file_change_index))
    write_text(
        REPORTS_DIR / "review_checklist.md",
        build_review_checklist(summary, issue_status, file_change_index),
    )

    run_id = summary.get("run_id") or now_iso().split("T", 1)[0].replace("-", "") + "-000"
    archive_dir = RUNS_DIR / str(run_id)
    copy_current_run_archive(RUNTIME_DIR, REPORTS_DIR, archive_dir)

    manifest = write_run_manifest(archive_dir, summary, progress)
    save_json(REPORTS_DIR / "run_manifest.json", manifest)
    save_json(archive_dir / "reports" / "final_summary.json", summary)
    write_text(archive_dir / "reports" / "final_summary.md", build_review_markdown(summary, issue_status, file_change_index))
    write_text(
        archive_dir / "reports" / "review_checklist.md",
        build_review_checklist(summary, issue_status, file_change_index),
    )

    print("中文总结、复核清单和运行归档已生成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
