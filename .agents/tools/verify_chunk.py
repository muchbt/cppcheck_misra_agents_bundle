from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import CONFIG_DIR, RESULTS_DIR, ROOT, load_json, run_command, save_json

def main() -> None:
    parser = argparse.ArgumentParser(description="Lightweight verification for one chunk result.")
    parser.add_argument("chunk_index", type=int)
    args = parser.parse_args()

    config = load_json(CONFIG_DIR / "pipeline.json", {})
    result_path = RESULTS_DIR / f"chunk_{args.chunk_index:03d}_result.json"
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
            import shlex
            proc = run_command(shlex.split(custom_cmd), cwd=ROOT)
        verification["command"] = custom_cmd
        verification["returncode"] = proc.returncode
        verification["passed"] = proc.returncode == 0
        verification["notes"] = "custom command executed"
    else:
        verification["notes"] = "light verification only; no custom command configured"

    result["verification"] = verification
    save_json(result_path, result)
    print(json.dumps(verification, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
