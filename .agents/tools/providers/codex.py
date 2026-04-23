from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from common import PROMPTS_DIR, RUNTIME_DIR, read_text, relative, resolve_agent_staging_dir

SUPPORTED_PROMPT_VIA = {"stdin", "arg"}
NON_INTERACTIVE_COMMAND_PREFIX = ["codex", "exec"]


def build_strategy_instructions(chunk: Dict[str, Any]) -> str:
    strategy = chunk.get("fix_strategy", "conservative")
    contains_high_risk = bool(chunk.get("contains_high_risk", False))

    if strategy == "all_auto":
        text = [
            "Fix strategy: all_auto.",
            "Attempt to fix every issue in this chunk when a technically valid minimal edit is possible.",
            "High-risk issues are allowed to be modified, but every high-risk edit must be explicitly marked with risk_level, risk_reason, and review_required_after_fix=true in the result JSON.",
            "If verification fails or the required edit is ambiguous, mark the issue as failed or needs_manual_review instead of claiming it is fixed.",
        ]
        if contains_high_risk:
            text.append("This chunk contains high-risk issues; keep those edits isolated and easy to review.")
        return "\n".join(text)

    return "\n".join(
        [
            "Fix strategy: conservative.",
            "Only fix high-confidence issues with local and unambiguous remediation.",
            "Do not modify high-risk MISRA, volatile, interrupt, register, RTE, MCAL, or communication stack paths; mark those issues as needs_manual_review.",
        ]
    )


def build_chunk_staging_paths(config: Dict[str, Any], chunk_index: int) -> Dict[str, Path]:
    chunk_dir = resolve_agent_staging_dir(config) / f"chunk_{chunk_index:03d}"
    return {
        "chunk_dir": chunk_dir,
        "issue_status_delta_path": chunk_dir / "issue_status_delta.json",
        "file_change_delta_path": chunk_dir / "file_change_delta.json",
        "chunk_result_json_path": chunk_dir / "chunk_result.json",
        "chunk_result_md_path": chunk_dir / "chunk_result.md",
    }


def build_prompt(config: Dict[str, Any], chunk: Dict[str, Any]) -> str:
    template = read_text(PROMPTS_DIR / "fix_chunk_prompt.txt", "")
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_paths = build_chunk_staging_paths(config, chunk_index)
    return template.format(
        chunk_index=chunk_index,
        strategy_instructions=build_strategy_instructions(chunk),
        issue_status_delta_path=relative(staging_paths["issue_status_delta_path"]),
        file_change_delta_path=relative(staging_paths["file_change_delta_path"]),
        chunk_result_json_path=relative(staging_paths["chunk_result_json_path"]),
        chunk_result_md_path=relative(staging_paths["chunk_result_md_path"]),
    )


def build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    launch = config["agent"]["launch"]
    chunk_index = int(chunk.get("chunk_index", 0))
    staging_paths = build_chunk_staging_paths(config, chunk_index)
    argv = list(launch["argv"])
    if "--add-dir" not in argv:
        argv.extend(["--add-dir", str(staging_paths["chunk_dir"])])
    return {
        "argv": argv,
        "prompt_via": launch["prompt_via"],
        "cwd_mode": launch["cwd"],
        "env": dict(launch.get("env", {})),
        "requires_tty": bool(launch["requires_tty"]),
        "output_mode": launch.get("output", {}).get("mode", "exit_code"),
        "prompt": build_prompt(config, chunk),
        "chunk_index": chunk_index,
        "runtime_dir": str(RUNTIME_DIR),
        "staging_dir": str(staging_paths["chunk_dir"]),
    }
