from __future__ import annotations

import argparse
import importlib
import sys
from typing import List


COMMANDS = {
    "split": ("split_cppcheck_xml", "Split cppcheck XML into runtime chunks."),
    "run": ("run_fix_pipeline", "Run the agent fixing pipeline."),
    "merge": ("merge_results", "Merge runtime results into reports."),
    "verify": ("verify_chunk", "Verify one chunk result."),
    "bootstrap": ("bootstrap_agents", "Generate agent compatibility files."),
    "doctor": ("doctor", "Run pipeline diagnostics."),
    "oneshot": ("oneshot", "Run the one-shot agent entrypoint."),
}


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="cppcheck/MISRA agent pipeline CLI.")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("args", nargs=argparse.REMAINDER)
    return parser.parse_args(argv)


def main() -> None:
    args = parse_args(sys.argv[1:])
    module_name = COMMANDS[args.command][0]
    module = importlib.import_module(module_name)
    sys.argv = [f"{module_name}.py", *args.args]
    result = module.main()
    if isinstance(result, int):
        raise SystemExit(result)


if __name__ == "__main__":
    main()
