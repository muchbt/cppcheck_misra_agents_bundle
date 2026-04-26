from __future__ import annotations

import argparse
import json
import platform
import shlex
from pathlib import Path
from typing import Any, Dict, List

from common import CONFIG_DIR, RESULTS_DIR, ROOT, load_json, run_command, save_json


def _split_command(command: str) -> List[str]:
    """Split command string into tokens, handling platform differences."""
    if platform.system() == "Windows":
        return command.split()
    return shlex.split(command)


def verify_chunk_result(chunk_index: int) -> Dict[str, Any]:
    config = load_json(CONFIG_DIR / "pipeline.json", {})
    result_path = RESULTS_DIR / f"chunk_{chunk_index:03d}_result.json"
    result = load_json(result_path, {})

    verification = {
        "performed": True,
        "passed": True,
        "mode": config["verification"]["mode"],
        "notes": "",
        "command": "",
        "returncode": 0,
    }

    custom_cmd = config["verification"].get("custom_command", "").strip()
    if custom_cmd:
        if Path(custom_cmd).exists():
            proc = run_command([custom_cmd], cwd=ROOT)
        else:
            proc = run_command(_split_command(custom_cmd), cwd=ROOT)
        verification["command"] = custom_cmd
        verification["returncode"] = proc.returncode
        verification["passed"] = proc.returncode == 0
        verification["notes"] = "custom command executed"
    else:
        verification["notes"] = "light verification only; no custom command configured"

    result["verification"] = verification
    save_json(result_path, result)
    return verification


def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight verification for one chunk result.")
    parser.add_argument("chunk_index", type=int)
    args = parser.parse_args()
    verification = verify_chunk_result(args.chunk_index)
    print(json.dumps(verification, ensure_ascii=False, indent=2))
