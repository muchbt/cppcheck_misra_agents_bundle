from __future__ import annotations

import argparse
import importlib
import os
import sys
from typing import List


COMMANDS = {
    "split": ("split_cppcheck_xml", "Split cppcheck XML into runtime chunks."),
    "run": ("run_fix_pipeline", "Run the agent fixing pipeline."),
    "merge": ("merge_results", "Merge runtime results into reports."),
    "verify": ("verify_chunk", "Verify one chunk result."),
    "bootstrap": ("bootstrap_agents", "Generate agent compatibility files."),
    "doctor": ("doctor", "Run pipeline diagnostics."),
    "validate-real": ("validate_real", "Run real 1 issue / 1 chunk provider validation."),
    "oneshot": ("oneshot", "Run the one-shot agent entrypoint."),
    "policy": ("policy_init", "Initialize policy configuration from templates."),
}


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="cppcheck/MISRA agent pipeline CLI.")
    parser.add_argument(
        "--provider",
        choices=["codex", "claude", "opencode"],
        default=None,
        help="Override agent provider from pipeline.json (codex, claude, or opencode).",
    )
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])

    # Save original env var value to restore after subcommand
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")

    try:
        # Set/clear provider env var based on CLI arg
        if args.provider:
            os.environ["PIPELINE_AGENT_PROVIDER"] = args.provider
        elif original_provider is not None:
            # Clear stale env var from previous invocation
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        module_name = COMMANDS[args.command][0]
        module = importlib.import_module(module_name)
        sys.argv = [f"{module_name}.py", *args.args]
        result = module.main()
        if isinstance(result, int):
            raise SystemExit(result)
    finally:
        # Restore original env var state
        if original_provider is not None:
            os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
        else:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)


if __name__ == "__main__":
    main()
