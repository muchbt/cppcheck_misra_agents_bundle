from __future__ import annotations

from common import CONFIG_DIR, PROMPTS_DIR, RUNTIME_DIR, load_json, read_text, run_command

def build_strategy_instructions(chunk_index: int) -> str:
    chunk = load_json(RUNTIME_DIR / "chunks" / f"chunk_{chunk_index:03d}.json", {})
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

def build_prompt(chunk_index: int) -> str:
    template = read_text(PROMPTS_DIR / "fix_chunk_prompt.txt", "")
    return template.format(
        chunk_index=chunk_index,
        strategy_instructions=build_strategy_instructions(chunk_index),
    )

def run_chunk(chunk_index: int) -> int:
    config = load_json(CONFIG_DIR / "pipeline.json", {})
    agent_cmd = config["agent"]["command"]
    prompt = build_prompt(chunk_index)
    proc = run_command([agent_cmd, prompt])
    return proc.returncode
