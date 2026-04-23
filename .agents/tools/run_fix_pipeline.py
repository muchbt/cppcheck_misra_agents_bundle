from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Iterable, Optional, Set

from agent_adapter_codex import run_chunk
from common import RESULTS_DIR, RUNTIME_DIR, append_jsonl, load_json, save_json

TZ = timezone(timedelta(hours=8))
VALID_STRATEGIES = {"conservative", "all_auto"}


def now() -> str:
    return datetime.now(TZ).isoformat()


def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


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
    append_jsonl(
        RUNTIME_DIR / "run_log.jsonl",
        {
            "chunk_index": idx,
            "status": "failed" if exhausted else "retry_scheduled",
            "finished_at": now(),
            "returncode": returncode,
            "attempt": attempt,
            "exhausted": exhausted,
        },
    )

    if exhausted and idx not in progress["failed_chunks"]:
        progress["failed_chunks"].append(idx)


def main() -> None:
    args = parse_args()
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

    processed_this_run = 0

    while True:
        if args.max_chunks > 0 and processed_this_run >= args.max_chunks:
            progress["status"] = "partial"
            save_json(progress_path, progress)
            print(f"Stopped after processing {processed_this_run} chunk(s) due to --max-chunks.")
            return

        idx = next_chunk(progress, selected_rules, args.misra_only, args.include_failed)
        if idx is None:
            progress["status"] = "done"
            save_json(progress_path, progress)
            print("No more eligible chunks to process.")
            return

        progress["current_chunk"] = idx
        progress["last_chunk_started_at"] = now()
        save_json(progress_path, progress)

        max_attempts = max(1, args.retry_failed + 1)
        success = False
        last_rc = 0

        for attempt in range(1, max_attempts + 1):
            rc = run_chunk(idx)
            last_rc = rc
            result_json = RESULTS_DIR / f"chunk_{idx:03d}_result.json"
            success = rc == 0 and result_json.exists()

            if success:
                if idx not in progress["completed_chunks"]:
                    progress["completed_chunks"].append(idx)
                if idx in progress["failed_chunks"]:
                    progress["failed_chunks"].remove(idx)
                append_jsonl(
                    RUNTIME_DIR / "run_log.jsonl",
                    {
                        "chunk_index": idx,
                        "status": "completed",
                        "finished_at": now(),
                        "attempt": attempt,
                    },
                )
                break

            exhausted = attempt >= max_attempts
            mark_failure(progress, idx, rc, attempt, exhausted)
            save_json(progress_path, progress)

        if not success:
            progress["status"] = "failed"
            progress["last_chunk_finished_at"] = now()
            progress["last_failure"] = {
                "chunk_index": idx,
                "returncode": last_rc,
                "retries": args.retry_failed,
            }
            save_json(progress_path, progress)
            print(f"Chunk {idx} failed after {max_attempts} attempt(s).")
            return

        processed_this_run += 1
        progress["last_chunk_finished_at"] = now()
        save_json(progress_path, progress)


if __name__ == "__main__":
    main()
