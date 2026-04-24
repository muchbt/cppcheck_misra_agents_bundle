from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import doctor
from common import RUNTIME_DIR, ROOT, append_pipeline_event, load_json

VALID_STRATEGIES = {"conservative", "all_auto"}
UNFINISHED_STATUSES = {"ready", "running", "partial", "failed"}
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


def execute_stage(stage: str, argv: List[str]) -> int:
    print(f"[oneshot] 正在执行 {stage} 阶段...")
    append_pipeline_event(
        RUNTIME_DIR,
        event=f"{stage}_stage_started",
        stage="oneshot",
        message=f"oneshot 开始执行 {stage} 阶段。",
        data={"argv": argv},
    )
    rc = run_stage(stage, argv)
    if rc == 0:
        append_pipeline_event(
            RUNTIME_DIR,
            event=f"{stage}_stage_completed",
            stage="oneshot",
            message=f"oneshot 完成 {stage} 阶段。",
            data={"argv": argv},
        )
        return 0
    append_pipeline_event(
        RUNTIME_DIR,
        event=f"{stage}_stage_failed",
        stage="oneshot",
        level="error",
        message=f"oneshot 执行 {stage} 阶段失败。",
        returncode=rc,
        data={"argv": argv},
    )
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


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    if args.fresh and args.resume:
        print("[oneshot] --fresh 和 --resume 不能同时使用。")
        return 2
    progress_path = RUNTIME_DIR / "progress.json"
    progress = safe_load_progress(progress_path)

    mode = "fresh"
    if not args.fresh and has_unfinished_runtime(progress):
        mode = "resume"

    # Warn if --resume requested but no unfinished runtime exists
    if args.resume and mode == "fresh":
        print("[oneshot] 注意：--resume 请求续跑但当前无未完成运行，将执行 fresh 模式。")

    progress_status = str(progress.get("status", "")).strip()
    progress_strategy = str(progress.get("fix_strategy", "")).strip()
    progress_run_id = str(progress.get("run_id", "")).strip()

    if mode == "resume":
        print(
            "[oneshot] 检测到未完成运行，默认继续执行: "
            f"run_id={progress_run_id or '未设置'}, "
            f"status={progress_status or '未设置'}, "
            f"completed={len(progress.get('completed_chunks', []))}/"
            f"{int(progress.get('total_chunks', 0))}"
        )

        if args.strategy and progress_strategy and args.strategy != progress_strategy:
            print(
                "[oneshot] 恢复执行时策略冲突: "
                f"progress={progress_strategy}, requested={args.strategy}。"
            )
            print(f"[oneshot] 请改用 --fresh --strategy {args.strategy}")
            return 2

        if args.run_id and progress_run_id and args.run_id != progress_run_id:
            print(
                "[oneshot] 恢复执行时 run_id 冲突: "
                f"progress={progress_run_id}, requested={args.run_id}。"
            )
            print("[oneshot] 续跑请使用当前 run_id，或改用 --fresh --run-id <new_run_id>")
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
        print("[oneshot] 预检查未通过。请先执行 `python3 .agents/tools/pipeline_cli.py doctor`。")
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
            print("[oneshot] 执行失败。建议先运行 `python3 .agents/tools/pipeline_cli.py doctor`。")
            return rc

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
        print("[oneshot] 执行失败。建议先运行 `python3 .agents/tools/pipeline_cli.py doctor`。")
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
        print("[oneshot] 执行失败。建议先运行 `python3 .agents/tools/pipeline_cli.py doctor`。")
        return rc

    append_pipeline_event(
        RUNTIME_DIR,
        event="oneshot_completed",
        stage="oneshot",
        message="oneshot 已完成 split/run/merge。",
        data={"mode": mode},
    )
    print("[oneshot] 全部阶段执行完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
