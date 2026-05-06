from __future__ import annotations

"""DEPRECATED: Use 'misra-pipeline run' instead. This module is kept for backward compatibility."""

import argparse
import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import doctor
from common import RUNTIME_DIR, ROOT, append_pipeline_event, load_json

VALID_STRATEGIES = {"conservative", "all_auto"}
UNFINISHED_STATUSES = {"ready", "running", "partial", "failed"}
USER_STATUS_MAP = {
    "done": "DONE",
    "partial": "NEEDS_CONTEXT",
    "failed": "BLOCKED",
    "ready": "NEEDS_CONTEXT",
    "running": "NEEDS_CONTEXT",
}
RESUME_IGNORED_ERROR_CODES = {"cppcheck_xml_missing", "cppcheck_xml_invalid"}
STAGE_MODULES = {
    "split": "split_cppcheck_xml",
    "run": "run_fix_pipeline",
    "merge": "merge_results",
}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="一键执行 split -> run -> merge，可自动续跑。")
    parser.add_argument("--fresh", action="store_true", help="忽略已有运行状态，强制从 split 重新开始。")
    parser.add_argument("--resume", action="store_true", help="显式续跑模式，与默认续跑行为一致，用于脚本中表达意图。")
    parser.add_argument("--strategy", choices=sorted(VALID_STRATEGIES), default=None)
    parser.add_argument("--run-id", default=None, help="仅 fresh 模式允许传入，格式 YYYYMMDD-XXX。")
    parser.add_argument("--max-chunks", type=int, default=None)
    parser.add_argument("--retry-failed", type=int, default=None)
    parser.add_argument("--rule-id", action="append", default=[])
    parser.add_argument("--misra-only", action="store_true")
    parser.add_argument("--include-failed", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="打印每个 chunk 完整 stdout/stderr。")
    parser.add_argument("--dry-run", action="store_true", help="预览模式：split 后打印 chunk 摘要，不启动 agent。")
    parser.add_argument("--status", action="store_true", help="查询当前运行进度并输出人类可读摘要。")
    return parser.parse_args(sys.argv[1:] if argv is None else argv)


def collect_precheck_results(root: Path = ROOT) -> List[Dict[str, Any]]:
    return doctor.collect_checks(root=root)


def safe_load_progress(path: Path) -> Dict[str, Any]:
    try:
        progress = load_json(path, {})
    except (OSError, json.JSONDecodeError):
        return {}
    return progress if isinstance(progress, dict) else {}


def has_unfinished_runtime(progress: Dict[str, Any]) -> bool:
    return str(progress.get("status", "")).strip() in UNFINISHED_STATUSES


def get_current_commit_sha(root: Path = ROOT) -> str:
    """Get the current git commit SHA, return empty string if not in a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()[:8]
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def compute_user_status(progress: Dict[str, Any], failed_count: int) -> str:
    """Compute user-facing status from internal progress status."""
    internal_status = str(progress.get("status", "")).strip()
    base_status = USER_STATUS_MAP.get(internal_status, "NEEDS_CONTEXT")
    # If done but has failed chunks, report DONE_WITH_CONCERNS
    if internal_status == "done" and failed_count > 0:
        return "DONE_WITH_CONCERNS"
    return base_status


def print_status_summary(runtime_dir: Path = RUNTIME_DIR, root: Path = ROOT) -> int:
    """Print human-readable progress summary and return exit code."""
    progress_path = runtime_dir / "progress.json"
    progress = safe_load_progress(progress_path)

    if not progress:
        print("[run] --status: 无运行记录 (progress.json 不存在或为空)")
        return 0

    run_id = str(progress.get("run_id", "")).strip() or "unknown"
    total = int(progress.get("total_chunks", 0))
    completed = len(progress.get("completed_chunks", []) or [])
    failed = len(progress.get("failed_chunks", []) or [])
    internal_status = str(progress.get("status", "")).strip() or "unknown"
    strategy = str(progress.get("fix_strategy", "")).strip() or "unknown"
    commit_sha = get_current_commit_sha(root)

    user_status = compute_user_status(progress, failed)

    print(f"[run] --status 查询结果:")
    print(f"  run_id: {run_id}")
    print(f"  status: {user_status}")
    print(f"  strategy: {strategy}")
    print(f"  progress: {completed}/{total} chunks completed")
    if failed > 0:
        print(f"  failed_chunks: {failed}")
    if commit_sha:
        print(f"  commit: {commit_sha}")
    print()

    return 0


def run_module_stage(module_name: str, argv: List[str]) -> int:
    module = importlib.import_module(module_name)
    original_argv = list(sys.argv)
    try:
        sys.argv = [f"{module_name}.py", *argv]
        result = module.main()
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 1
    finally:
        sys.argv = original_argv
    if isinstance(result, int):
        return result
    return 0


def run_stage(stage: str, argv: List[str]) -> int:
    module_name = STAGE_MODULES[stage]
    return run_module_stage(module_name, argv)


def _log_stage_event(
    stage: str, event_suffix: str, message: str, argv: List[str],
    level: Optional[str] = None, returncode: Optional[int] = None
) -> None:
    """Helper to log stage events with common parameters."""
    kwargs = {
        "event": f"{stage}_stage_{event_suffix}",
        "stage": "oneshot",
        "message": message,
        "data": {"argv": argv},
    }
    if level is not None:
        kwargs["level"] = level
    if returncode is not None:
        kwargs["returncode"] = returncode
    append_pipeline_event(RUNTIME_DIR, **kwargs)


def execute_stage(stage: str, argv: List[str]) -> int:
    """Run a stage with logging. Returns exit code."""
    print(f"[run] 正在执行 {stage} 阶段...")
    _log_stage_event(stage, "started", f"oneshot 开始执行 {stage} 阶段。", argv)
    rc = run_stage(stage, argv)
    if rc == 0:
        _log_stage_event(stage, "completed", f"oneshot 完成 {stage} 阶段。", argv)
    else:
        _log_stage_event(stage, "failed", f"oneshot 执行 {stage} 阶段失败。", argv, level="error", returncode=rc)
    return rc


def build_split_args(args: argparse.Namespace) -> List[str]:
    stage_args: List[str] = []
    if args.strategy:
        stage_args.extend(["--strategy", args.strategy])
    if args.run_id:
        stage_args.extend(["--run-id", args.run_id])
    return stage_args


def build_run_args(args: argparse.Namespace, resume_status: str) -> List[str]:
    stage_args: List[str] = []
    if args.strategy:
        stage_args.extend(["--strategy", args.strategy])
    if args.max_chunks is not None:
        stage_args.extend(["--max-chunks", str(args.max_chunks)])
    if args.retry_failed is not None:
        stage_args.extend(["--retry-failed", str(args.retry_failed)])
    for rule_id in args.rule_id:
        stage_args.extend(["--rule-id", rule_id])
    if args.misra_only:
        stage_args.append("--misra-only")
    if args.include_failed or resume_status == "failed":
        stage_args.append("--include-failed")
    if args.verbose:
        stage_args.append("--verbose")
    return stage_args


def filter_blockers(results: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    blockers: List[Dict[str, Any]] = []
    for result in results:
        if result.get("level") != "error":
            continue
        if mode == "resume" and result.get("code") in RESUME_IGNORED_ERROR_CODES:
            continue
        blockers.append(result)
    return blockers


def print_dry_run_summary(runtime_dir: Path) -> None:
    """Print a summary of chunks after split for --dry-run mode."""
    progress = safe_load_progress(runtime_dir / "progress.json")
    issues = load_json(runtime_dir / "issues_master.json", [])
    total_chunks = progress.get("total_chunks", 0)
    total_issues = len(issues) if isinstance(issues, list) else 0
    run_id = progress.get("run_id", "unknown")
    strategy = progress.get("fix_strategy", "unknown")

    print("\n[run] === DRY-RUN PREVIEW ===")
    print(f"[run] run_id: {run_id}")
    print(f"[run] strategy: {strategy}")
    print(f"[run] total_issues: {total_issues}")
    print(f"[run] total_chunks: {total_chunks}")
    print()

    # Load and summarize each chunk
    chunks_dir = runtime_dir / "chunks"
    if chunks_dir.exists():
        chunk_files = sorted(chunks_dir.glob("chunk_*.json"))
        for chunk_file in chunk_files:
            chunk_data = load_json(chunk_file, {})
            if not isinstance(chunk_data, dict):
                continue
            chunk_idx = chunk_data.get("chunk_index", "?")
            issue_count = chunk_data.get("issue_count", 0)
            files = chunk_data.get("files", [])
            high_risk = chunk_data.get("contains_high_risk", False)
            review_count = chunk_data.get("requires_review_after_fix_count", 0)

            status_flags = []
            if high_risk:
                status_flags.append("HIGH_RISK")
            if review_count > 0:
                status_flags.append(f"NEEDS_REVIEW:{review_count}")

            flags_str = f" [{', '.join(status_flags)}]" if status_flags else ""
            print(f"[run] chunk_{chunk_idx:03d}: {issue_count} issues, {len(files)} file(s){flags_str}")
            for f in files[:5]:
                print(f"    - {f}")
            if len(files) > 5:
                print(f"    ... and {len(files) - 5} more file(s)")

    print("\n[run] DRY-RUN complete. No agents were started.")
    print("[run] To execute, run without --dry-run or use --fresh.\n")


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)

    # Handle --status early: just print progress summary and exit
    if args.status:
        return print_status_summary(RUNTIME_DIR, ROOT)

    if args.fresh and args.resume:
        print("[run] --fresh 和 --resume 不能同时使用。")
        return 2
    progress_path = RUNTIME_DIR / "progress.json"
    progress = safe_load_progress(progress_path)

    mode = "fresh"
    if not args.fresh and has_unfinished_runtime(progress):
        mode = "resume"

    # Warn if --resume requested but no unfinished runtime exists
    if args.resume and mode == "fresh":
        print("[run] 注意：--resume 请求续跑但当前无未完成运行，将执行 fresh 模式。")

    progress_status = str(progress.get("status", "")).strip()
    progress_strategy = str(progress.get("fix_strategy", "")).strip()
    progress_run_id = str(progress.get("run_id", "")).strip()

    if mode == "resume":
        print(
            "[run] 检测到未完成运行，默认继续执行: "
            f"run_id={progress_run_id or '未设置'}, "
            f"status={progress_status or '未设置'}, "
            f"completed={len(progress.get('completed_chunks', []))}/"
            f"{int(progress.get('total_chunks', 0))}"
        )

        if args.strategy and progress_strategy and args.strategy != progress_strategy:
            print(
                "[run] 恢复执行时策略冲突: "
                f"progress={progress_strategy}, requested={args.strategy}。"
            )
            print(f"[run] 请改用 --fresh --strategy {args.strategy}")
            return 2

        if args.run_id and progress_run_id and args.run_id != progress_run_id:
            print(
                "[run] 恢复执行时 run_id 冲突: "
                f"progress={progress_run_id}, requested={args.run_id}。"
            )
            print("[run] 续跑请使用当前 run_id，或改用 --fresh --run-id <new_run_id>")
            return 2

    checks = collect_precheck_results(ROOT)
    doctor.print_checks(checks)
    blockers = filter_blockers(checks, mode)
    if blockers:
        append_pipeline_event(
            RUNTIME_DIR,
            event="oneshot_precheck_failed",
            stage="oneshot",
            level="error",
            message="oneshot 预检查失败。",
            data={"mode": mode, "blockers": [item.get("code", "") for item in blockers]},
        )
        print("[run] 预检查未通过。请先执行 `misra-pipeline doctor`。")
        return 1

    append_pipeline_event(
        RUNTIME_DIR,
        event="oneshot_started",
        stage="oneshot",
        message="oneshot 启动。",
        data={
            "mode": mode,
            "requested_strategy": args.strategy or "",
            "requested_run_id": args.run_id or "",
        },
    )

    if mode == "fresh":
        rc = execute_stage("split", build_split_args(args))
        if rc != 0:
            append_pipeline_event(
                RUNTIME_DIR,
                event="oneshot_failed",
                stage="oneshot",
                level="error",
                message="oneshot 在 split 阶段失败。",
                returncode=rc,
                data={"mode": mode},
            )
            print("[run] 执行失败。建议先运行 `misra-pipeline doctor`。")
            return rc

    # --dry-run: print chunk summary and exit without starting agents
    if args.dry_run:
        append_pipeline_event(
            RUNTIME_DIR,
            event="oneshot_dry_run",
            stage="oneshot",
            message="oneshot dry-run 预览模式，跳过 run/merge。",
            data={"mode": mode},
        )
        print_dry_run_summary(RUNTIME_DIR)
        return 0

    rc = execute_stage("run", build_run_args(args, progress_status))
    if rc != 0:
        append_pipeline_event(
            RUNTIME_DIR,
            event="oneshot_failed",
            stage="oneshot",
            level="error",
            message="oneshot 在 run 阶段失败。",
            returncode=rc,
            data={"mode": mode},
        )
        print("[run] 执行失败。建议先运行 `misra-pipeline doctor`。")
        return rc

    rc = execute_stage("merge", [])
    if rc != 0:
        append_pipeline_event(
            RUNTIME_DIR,
            event="oneshot_failed",
            stage="oneshot",
            level="error",
            message="oneshot 在 merge 阶段失败。",
            returncode=rc,
            data={"mode": mode},
        )
        print("[run] 执行失败。建议先运行 `misra-pipeline doctor`。")
        return rc

    append_pipeline_event(
        RUNTIME_DIR,
        event="oneshot_completed",
        stage="oneshot",
        message="oneshot 已完成 split/run/merge。",
        data={"mode": mode},
    )
    print("[run] 全部阶段执行完成。")
    return 0
