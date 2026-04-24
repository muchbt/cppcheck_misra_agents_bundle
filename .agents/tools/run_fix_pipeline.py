from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Optional, Set

from agent_runner import run_chunk_agent
from common import CONFIG_DIR, RESULTS_DIR, RUNTIME_DIR, append_pipeline_event, load_json, now_iso, save_json
from verify_chunk import verify_chunk_result

VALID_STRATEGIES = {"conservative", "all_auto"}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run chunk-based agent fixing pipeline with optional chunk limit, "
            "automatic retries, and rule-based filtering."
        )
    )
    parser.add_argument(
        "--max-chunks",
        type=int,
        default=0,
        help="Process at most N eligible chunks in this run. 0 means no limit.",
    )
    parser.add_argument(
        "--retry-failed",
        type=int,
        default=0,
        help="Retry a failed chunk up to N additional times before marking it failed.",
    )
    parser.add_argument(
        "--rule-id",
        action="append",
        default=[],
        help=(
            "Only process chunks containing at least one matching rule_id. "
            "Can be specified multiple times. Matching is case-insensitive exact match."
        ),
    )
    parser.add_argument(
        "--misra-only",
        action="store_true",
        help="Only process chunks containing MISRA issues.",
    )
    parser.add_argument(
        "--include-failed",
        action="store_true",
        help="Allow previously failed chunks to be reconsidered in this run.",
    )
    parser.add_argument(
        "--strategy",
        choices=sorted(VALID_STRATEGIES),
        default=None,
        help=(
            "Expected fix strategy for this run. Must match the strategy used by "
            "split_cppcheck_xml.py."
        ),
    )
    return parser.parse_args(argv)


def normalize_rule_set(rule_ids: Iterable[str]) -> Set[str]:
    return {item.strip().lower() for item in rule_ids if item and item.strip()}


def load_chunk_payload(chunk_index: int) -> dict:
    path = RUNTIME_DIR / "chunks" / f"chunk_{chunk_index:03d}.json"
    return load_json(path, {})


def chunk_matches_filters(chunk_index: int, selected_rules: Set[str], misra_only: bool) -> bool:
    if not selected_rules and not misra_only:
        return True

    payload = load_chunk_payload(chunk_index)
    issues = payload.get("issues", [])
    if not issues:
        return False

    has_selected_rule = not selected_rules
    has_misra = not misra_only

    for issue in issues:
        rule_id = str(issue.get("rule_id", "")).strip().lower()
        is_misra = bool(issue.get("is_misra", False))

        if selected_rules and rule_id in selected_rules:
            has_selected_rule = True
        if misra_only and is_misra:
            has_misra = True

        if has_selected_rule and has_misra:
            return True

    return has_selected_rule and has_misra


def next_chunk(progress: dict, selected_rules: Set[str], misra_only: bool, include_failed: bool) -> Optional[int]:
    done = set(progress.get("completed_chunks", []))
    failed = set(progress.get("failed_chunks", []))
    total = int(progress.get("total_chunks", 0))

    for idx in range(1, total + 1):
        if idx in done:
            continue
        if not include_failed and idx in failed:
            continue
        if not chunk_matches_filters(idx, selected_rules, misra_only):
            continue
        return idx
    return None


def mark_failure(progress: dict, idx: int, returncode: int, attempt: int, exhausted: bool) -> None:
    append_pipeline_event(
        RUNTIME_DIR,
        event="chunk_failed" if exhausted else "chunk_retry_scheduled",
        stage="run",
        level="error" if exhausted else "warning",
        message=f"chunk {idx} 执行失败。" if exhausted else f"chunk {idx} 执行失败，准备重试。",
        chunk_index=idx,
        returncode=returncode,
        data={
            "attempt": attempt,
            "exhausted": exhausted,
        },
    )

    if exhausted and idx not in progress["failed_chunks"]:
        progress["failed_chunks"].append(idx)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    selected_rules = normalize_rule_set(args.rule_id)

    progress_path = RUNTIME_DIR / "progress.json"
    progress = load_json(progress_path, {})
    if not progress:
        raise SystemExit("progress.json not found or empty. Run split_cppcheck_xml.py first.")

    progress_strategy = progress.get("fix_strategy", "conservative")
    requested_strategy = args.strategy or progress_strategy
    if requested_strategy != progress_strategy:
        raise SystemExit(
            "Strategy mismatch: chunks were generated with "
            f"'{progress_strategy}', but run requested '{requested_strategy}'. "
            "Run split_cppcheck_xml.py again with the requested --strategy."
        )

    progress["status"] = "running"
    progress["last_run_filters"] = {
        "max_chunks": args.max_chunks,
        "retry_failed": args.retry_failed,
        "rule_ids": sorted(selected_rules),
        "misra_only": args.misra_only,
        "include_failed": args.include_failed,
        "strategy": requested_strategy,
    }
    save_json(progress_path, progress)
    append_pipeline_event(
        RUNTIME_DIR,
        event="run_started",
        stage="run",
        message="开始执行 run 阶段。",
        data={
            "filters": progress["last_run_filters"],
            "total_chunks": int(progress.get("total_chunks", 0)),
        },
    )

    processed_this_run = 0

    while True:
        if args.max_chunks > 0 and processed_this_run >= args.max_chunks:
            progress["status"] = "partial"
            save_json(progress_path, progress)
            append_pipeline_event(
                RUNTIME_DIR,
                event="run_partial",
                stage="run",
                level="warning",
                message="达到 --max-chunks 限制，run 阶段部分完成。",
                data={
                    "processed": processed_this_run,
                    "max_chunks": args.max_chunks,
                },
            )
            print(f"Stopped after processing {processed_this_run} chunk(s) due to --max-chunks.")
            return 0

        idx = next_chunk(progress, selected_rules, args.misra_only, args.include_failed)
        if idx is None:
            progress["status"] = "done"
            save_json(progress_path, progress)
            append_pipeline_event(
                RUNTIME_DIR,
                event="run_completed",
                stage="run",
                message="run 阶段已完成，无可处理 chunk。",
                data={
                    "processed": processed_this_run,
                    "completed_chunks": len(progress.get("completed_chunks", [])),
                    "failed_chunks": len(progress.get("failed_chunks", [])),
                },
            )
            print("No more eligible chunks to process.")
            return 0

        progress["current_chunk"] = idx
        progress["last_chunk_started_at"] = now_iso()
        save_json(progress_path, progress)
        total = int(progress.get("total_chunks", 0))
        print(f"正在处理 chunk {idx}/{total}")
        append_pipeline_event(
            RUNTIME_DIR,
            event="chunk_started",
            stage="run",
            message=f"开始处理 chunk {idx}。",
            chunk_index=idx,
            data={
                "total_chunks": total,
            },
        )

        max_attempts = max(1, args.retry_failed + 1)
        success = False
        last_rc = 0
        last_error_kind = ""

        for attempt in range(1, max_attempts + 1):
            config = load_json(CONFIG_DIR / "pipeline.json", {})
            chunk_payload = load_chunk_payload(idx)
            result = run_chunk_agent(config, chunk_payload)
            rc = int(result.get("returncode", 1))
            last_rc = rc
            last_error_kind = str(result.get("error_kind", "")).strip()
            result_json = RESULTS_DIR / f"chunk_{idx:03d}_result.json"
            imported_paths = result.get("imported_paths", {})
            imported_result_json = None
            if isinstance(imported_paths, dict):
                imported_path_value = imported_paths.get("chunk_result_json_path")
                if imported_path_value:
                    imported_result_json = Path(str(imported_path_value))
            success = rc == 0 and (
                (imported_result_json is not None and imported_result_json.exists())
                or result_json.exists()
            )

            if success:
                if idx not in progress["completed_chunks"]:
                    progress["completed_chunks"].append(idx)
                if idx in progress["failed_chunks"]:
                    progress["failed_chunks"].remove(idx)
                verification = verify_chunk_result(idx)
                append_pipeline_event(
                    RUNTIME_DIR,
                    event="chunk_completed",
                    stage="run",
                    message=f"chunk {idx} 处理完成。",
                    chunk_index=idx,
                    returncode=rc,
                    data={
                        "attempt": attempt,
                        "verification_passed": bool(verification.get("passed")),
                        "verification_mode": verification.get("mode", ""),
                        "imported_result_json": str(imported_result_json) if imported_result_json is not None else "",
                    },
                )
                break

            exhausted = attempt >= max_attempts
            mark_failure(progress, idx, rc, attempt, exhausted)
            if result.get("returncode") != 0:
                stderr_preview = (result.get("stderr") or "")[:200]
                print(f"[run] Chunk {idx} 失败: {result.get('error_kind', 'unknown')} - {stderr_preview}")
            save_json(progress_path, progress)

        if not success:
            progress["status"] = "failed"
            progress["last_chunk_finished_at"] = now_iso()
            progress["last_failure"] = {
                "chunk_index": idx,
                "returncode": last_rc,
                "retries": args.retry_failed,
                "error_kind": last_error_kind or "runtime_error",
            }
            save_json(progress_path, progress)
            print(f"Chunk {idx} failed after {max_attempts} attempt(s).")
            return 1

        processed_this_run += 1
        progress["last_chunk_finished_at"] = now_iso()
        save_json(progress_path, progress)


if __name__ == "__main__":
    raise SystemExit(main())
