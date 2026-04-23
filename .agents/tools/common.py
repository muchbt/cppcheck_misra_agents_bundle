from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path.cwd()
AGENTS_DIR = ROOT / ".agents"
CONFIG_DIR = AGENTS_DIR / "config"
PROMPTS_DIR = AGENTS_DIR / "prompts"
SKILLS_DIR = AGENTS_DIR / "skills"
RUNTIME_DIR = AGENTS_DIR / "runtime"
CHUNKS_DIR = RUNTIME_DIR / "chunks"
RESULTS_DIR = RUNTIME_DIR / "results"
REPORTS_DIR = AGENTS_DIR / "reports"

AUTO_BLOCK_BEGIN = "<!-- BEGIN AUTO-GENERATED: cppcheck-misra-fix -->"
AUTO_BLOCK_END = "<!-- END AUTO-GENERATED: cppcheck-misra-fix -->"

def ensure_dirs() -> None:
    for path in [
        AGENTS_DIR,
        CONFIG_DIR,
        PROMPTS_DIR,
        SKILLS_DIR,
        RUNTIME_DIR,
        CHUNKS_DIR,
        RESULTS_DIR,
        REPORTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)

def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")

def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def short_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]

def normalize_msg(msg: str) -> str:
    return " ".join((msg or "").split())

def build_issue_key(file_path: str, line: int, rule_id: str, msg: str) -> str:
    return f"{file_path}:{line}:{rule_id}:{short_hash(normalize_msg(msg))}"

def append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def run_command(cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd or ROOT), check=False)

def replace_or_append_marked_block(original: str, block_body: str) -> str:
    new_block = f"{AUTO_BLOCK_BEGIN}\n{block_body.rstrip()}\n{AUTO_BLOCK_END}\n"
    if AUTO_BLOCK_BEGIN in original and AUTO_BLOCK_END in original:
        start = original.index(AUTO_BLOCK_BEGIN)
        end = original.index(AUTO_BLOCK_END) + len(AUTO_BLOCK_END)
        prefix = original[:start].rstrip()
        suffix = original[end:].lstrip("\n")
        if prefix and suffix:
            return f"{prefix}\n\n{new_block}\n{suffix}".rstrip() + "\n"
        if prefix:
            return f"{prefix}\n\n{new_block}"
        if suffix:
            return f"{new_block}\n{suffix}".rstrip() + "\n"
        return new_block
    if original.strip():
        return original.rstrip() + "\n\n" + new_block
    return new_block

def next_edit_id(file_path: str, file_change_index: Dict[str, Any]) -> str:
    data = file_change_index.get(file_path, {})
    edits = data.get("edits", [])
    seq = len(edits) + 1
    return f"{file_path}#{seq:03d}"

def sha8_of_file(path: Path) -> str:
    if not path.exists():
        return ""
    return short_hash(path.read_text(encoding="utf-8", errors="ignore"))

def relative(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")
