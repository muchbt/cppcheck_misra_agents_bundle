from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Protocol

from common import PROMPTS_DIR, get_selected_agent_config, read_text, relative, resolve_agent_staging_dir


LaunchSpec = Dict[str, Any]
ExecutionResult = Dict[str, Any]
ProviderSpec = Dict[str, Any]


class ProviderProtocol(Protocol):
    """Structural typing contract for provider modules.

    Each provider module must define the following module-level attributes
    and functions:

    - PROVIDER_NAME: str - Unique identifier for the provider
    - SANITIZED_ENV_KEYS: set[str] - Environment keys to sanitize in logs
    - prepare_launch_env(env: Dict[str, str]) -> None
    - classify_runtime_error(stderr: str) -> str
    - build_launch_spec(config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]

    Note: Providers implement these as module-level attributes and functions,
    not as class instances. This Protocol serves as a documented interface
    contract. To verify a new provider conforms, ensure it defines all five
    members with matching signatures.
    """

    PROVIDER_NAME: str
    SANITIZED_ENV_KEYS: set[str]

    def prepare_launch_env(self, env: Dict[str, str]) -> None:
        """Prepare environment variables for the provider launch."""
        ...

    def classify_runtime_error(self, stderr: str) -> str:
        """Classify runtime errors from stderr output."""
        ...

    def build_launch_spec(self, config: Dict[str, Any], chunk: Dict[str, Any]) -> Dict[str, Any]:
        """Build launch specification for agent execution."""
        ...


def get_selected_launch(config: Dict[str, Any]) -> Dict[str, Any]:
    return get_selected_agent_config(config).get("launch", {})


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


def build_chunk_prompt(config: Dict[str, Any], chunk: Dict[str, Any]) -> str:
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
