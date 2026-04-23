from __future__ import annotations

from typing import Any, Dict

from common import PROMPTS_DIR, RUNTIME_DIR, read_text

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


def build_prompt(chunk: Dict[str, Any]) -> str:
    template = read_text(PROMPTS_DIR / "fix_chunk_prompt.txt", "")
    chunk_index = int(chunk.get("chunk_index", 0))
    return template.format(
        chunk_index=chunk_index,
        strategy_instructions=build_strategy_instructions(chunk),
    )


def build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
    launch = config["agent"]["launch"]
    return {
        "argv": list(launch["argv"]),
        "prompt_via": launch["prompt_via"],
        "cwd_mode": launch["cwd"],
        "env": dict(launch.get("env", {})),
        "requires_tty": bool(launch["requires_tty"]),
        "output_mode": launch.get("output", {}).get("mode", "exit_code"),
        "prompt": build_prompt(chunk),
        "chunk_index": int(chunk.get("chunk_index", 0)),
        "runtime_dir": str(RUNTIME_DIR),
    }
