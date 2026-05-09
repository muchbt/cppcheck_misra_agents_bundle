from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_OVERRIDE_ENV = "PIPELINE_PROJECT_ROOT"
ROOT_OVERRIDE_VALUE = os.environ.get(ROOT_OVERRIDE_ENV, "").strip()
ROOT = Path(ROOT_OVERRIDE_VALUE).resolve() if ROOT_OVERRIDE_VALUE else Path(__file__).resolve().parents[2]
AGENTS_DIR = ROOT / ".agents"
CONFIG_DIR = AGENTS_DIR / "config"
PROMPTS_DIR = AGENTS_DIR / "prompts"
SKILLS_DIR = AGENTS_DIR / "skills"
RUNTIME_DIR = AGENTS_DIR / "runtime"
RUNS_DIR = AGENTS_DIR / "runs"
CHUNKS_DIR = RUNTIME_DIR / "chunks"
RESULTS_DIR = RUNTIME_DIR / "results"
LOGS_DIR = RUNTIME_DIR / "logs"
REPORTS_DIR = AGENTS_DIR / "reports"
FIX_PATTERNS_PATH = CONFIG_DIR / "fix_patterns.json"
TZ = timezone(timedelta(hours=8))
RUN_ID_RE = re.compile(r"^(?P<date>\d{8})-(?P<seq>\d{3})$")

AUTO_BLOCK_BEGIN = "<!-- BEGIN AUTO-GENERATED: cppcheck-misra-fix -->"
AUTO_BLOCK_END = "<!-- END AUTO-GENERATED: cppcheck-misra-fix -->"

# Error kinds for agent execution
ERROR_KIND_LAUNCH_FAILED = "launch_failed"
ERROR_KIND_TIMEOUT = "timeout"
ERROR_KIND_AUTH_ERROR = "auth_error"
ERROR_KIND_NETWORK_ERROR = "network_error"
ERROR_KIND_RUNTIME_ERROR = "runtime_error"
ERROR_KIND_SUCCESS = "success"
ERROR_KIND_CONFIG_ERROR = "config_error"
ERROR_KIND_SPAWN_ERROR = "spawn_error"
ERROR_KIND_IMPORT_ERROR = "import_error"


def resolve_path_under_root(value: str, root: Path = ROOT) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    resolved_root = root.resolve(strict=False)
    resolved_path = path.resolve(strict=False)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise ValueError(f"path must stay under project root: {value}") from exc
    return resolved_path


def resolve_agent_staging_dir(config: Dict[str, Any], root: Path = ROOT) -> Path:
    staging_dir = str(config.get("agent", {}).get("staging_dir", "")).strip()
    if not staging_dir:
        raise ValueError("agent.staging_dir must be a non-empty string")
    return resolve_path_under_root(staging_dir, root=root)


def resolve_chunk_staging_dir(config: Dict[str, Any], chunk_index: int, root: Path = ROOT) -> Path:
    return resolve_agent_staging_dir(config, root=root) / f"chunk_{int(chunk_index):03d}"


def get_selected_agent_provider_name(config: Dict[str, Any]) -> str:
    # Priority: env var > config
    env_provider = os.environ.get("PIPELINE_AGENT_PROVIDER", "").strip()
    if env_provider:
        return env_provider
    return str(config.get("agent", {}).get("provider", "")).strip()


def get_selected_agent_config(config: Dict[str, Any]) -> Dict[str, Any]:
    agent = config.get("agent", {})
    if not isinstance(agent, dict):
        return {}

    provider_name = get_selected_agent_provider_name(config)
    providers = agent.get("providers", {})
    selected_provider = {}
    if isinstance(providers, dict) and isinstance(providers.get(provider_name), dict):
        selected_provider = providers.get(provider_name, {})

    launch = selected_provider.get("launch", agent.get("launch", {}))
    capabilities = selected_provider.get("capabilities", agent.get("capabilities", {}))
    merged = {
        "provider": provider_name,
        "staging_dir": agent.get("staging_dir", ""),
        "launch": launch if isinstance(launch, dict) else {},
        "capabilities": capabilities if isinstance(capabilities, dict) else {},
        "auto_bootstrap_compat": bool(agent.get("auto_bootstrap_compat", False)),
    }
    return merged

def ensure_dirs() -> None:
    for path in [
        AGENTS_DIR,
        CONFIG_DIR,
        PROMPTS_DIR,
        SKILLS_DIR,
        RUNTIME_DIR,
        RUNS_DIR,
        CHUNKS_DIR,
        RESULTS_DIR,
        REPORTS_DIR,
        LOGS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)

def now_iso() -> str:
    return datetime.now(TZ).isoformat()

def next_run_id(runs_dir: Path = RUNS_DIR, now: Optional[datetime] = None) -> str:
    current = now or datetime.now(TZ)
    if current.tzinfo is None:
        current = current.replace(tzinfo=TZ)
    else:
        current = current.astimezone(TZ)

    date_key = current.strftime("%Y%m%d")
    max_seq = 0
    if runs_dir.exists():
        for path in runs_dir.iterdir():
            if not path.is_dir():
                continue
            match = RUN_ID_RE.match(path.name)
            if not match or match.group("date") != date_key:
                continue
            max_seq = max(max_seq, int(match.group("seq")))
    return f"{date_key}-{max_seq + 1:03d}"

def validate_pipeline_config(config: Any) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(config, dict):
        return ["pipeline config must be a JSON object"], warnings

    required_sections = ("project", "input", "chunking", "filter", "misra", "fix_strategy", "verification", "agent")
    for section in required_sections:
        if section not in config:
            errors.append(f"missing section: {section}")
            continue
        if not isinstance(config[section], dict):
            errors.append(f"section {section} must be an object")

    project = config.get("project", {})
    if isinstance(project, dict):
        for key in ("runtime_dir", "reports_dir", "chunks_dir", "results_dir"):
            value = project.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"project.{key} must be a non-empty string")

    input_cfg = config.get("input", {})
    if isinstance(input_cfg, dict):
        cppcheck_xml = input_cfg.get("cppcheck_xml")
        if not isinstance(cppcheck_xml, str) or not cppcheck_xml.strip():
            errors.append("input.cppcheck_xml must be a non-empty string")

    chunking = config.get("chunking", {})
    if isinstance(chunking, dict):
        for key in ("max_issues_per_chunk", "max_files_per_chunk"):
            value = chunking.get(key)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                errors.append(f"chunking.{key} must be a positive integer")
        for key in ("prefer_group_by_file", "split_high_risk_alone"):
            value = chunking.get(key)
            if not isinstance(value, bool):
                errors.append(f"chunking.{key} must be a boolean")

    filter_cfg = config.get("filter", {})
    if isinstance(filter_cfg, dict):
        include_severity = filter_cfg.get("include_severity")
        if not isinstance(include_severity, list) or not include_severity or not all(isinstance(item, str) and item.strip() for item in include_severity):
            errors.append("filter.include_severity must be a non-empty list of strings")
        if not isinstance(filter_cfg.get("exclude_information"), bool):
            errors.append("filter.exclude_information must be a boolean")

    misra = config.get("misra", {})
    if isinstance(misra, dict):
        if not isinstance(misra.get("enabled"), bool):
            errors.append("misra.enabled must be a boolean")
        detect_prefixes = misra.get("detect_prefixes")
        if not isinstance(detect_prefixes, list) or not detect_prefixes or not all(isinstance(item, str) and item.strip() for item in detect_prefixes):
            errors.append("misra.detect_prefixes must be a non-empty list of strings")

    fix_strategy = config.get("fix_strategy", {})
    if isinstance(fix_strategy, dict):
        mode = fix_strategy.get("mode")
        if mode not in {"conservative", "all_auto"}:
            errors.append("fix_strategy.mode must be one of: conservative, all_auto")
        for key in ("mark_high_risk_in_all_auto", "require_review_after_high_risk_fix"):
            if not isinstance(fix_strategy.get(key), bool):
                errors.append(f"fix_strategy.{key} must be a boolean")

    verification = config.get("verification", {})
    if isinstance(verification, dict):
        if not isinstance(verification.get("mode"), str) or not verification.get("mode", "").strip():
            errors.append("verification.mode must be a non-empty string")
        for key in ("rerun_cppcheck_for_touched_files",):
            if not isinstance(verification.get(key), bool):
                errors.append(f"verification.{key} must be a boolean")
        custom_command = verification.get("custom_command")
        if not isinstance(custom_command, str):
            errors.append("verification.custom_command must be a string")

    agent = config.get("agent", {})
    if isinstance(agent, dict):
        # Check provider - allow env var override to skip config requirement
        env_provider = os.environ.get("PIPELINE_AGENT_PROVIDER", "").strip()
        provider = agent.get("provider")

        if env_provider:
            # Env var override active - validate the specified provider exists
            providers = agent.get("providers")
            if not isinstance(providers, dict):
                errors.append("agent.providers must be an object when provider override is active")
            elif env_provider not in providers:
                errors.append(f"agent.providers must include env-specified provider: {env_provider}")
        else:
            # No env override - require config provider
            if not isinstance(provider, str) or not provider.strip():
                errors.append("agent.provider must be a non-empty string")

        staging_dir = agent.get("staging_dir")
        if not isinstance(staging_dir, str) or not staging_dir.strip():
            errors.append("agent.staging_dir must be a non-empty string")
        else:
            try:
                resolve_agent_staging_dir(config)
            except ValueError:
                errors.append("agent.staging_dir must resolve under project root")

        providers = agent.get("providers")
        if providers is not None and not isinstance(providers, dict):
            errors.append("agent.providers must be an object")
        elif isinstance(providers, dict):
            # If config has provider, check it's in providers
            if provider and isinstance(provider, str) and provider.strip():
                if provider not in providers:
                    errors.append("agent.providers must include the selected agent.provider")
            for name, provider_config in providers.items():
                if not isinstance(name, str) or not name.strip():
                    errors.append("agent.providers keys must be non-empty strings")
                    continue
                if not isinstance(provider_config, dict):
                    errors.append(f"agent.providers.{name} must be an object")
                    continue

        selected_agent = get_selected_agent_config(config)

        launch = selected_agent.get("launch", {})
        if not isinstance(launch, dict):
            errors.append("agent.launch must be an object")
        else:
            argv = launch.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item.strip() for item in argv):
                errors.append("agent.launch.argv must be a non-empty list of strings")

            prompt_via = launch.get("prompt_via")
            if prompt_via not in {"stdin", "arg", "file"}:
                errors.append("agent.launch.prompt_via must be one of: stdin, arg, file")

            cwd = launch.get("cwd")
            if cwd not in {"project_root", "runtime_dir", "custom"}:
                errors.append("agent.launch.cwd must be one of: project_root, runtime_dir, custom")
            if cwd == "custom":
                custom_cwd = launch.get("cwd_path")
                if not isinstance(custom_cwd, str) or not custom_cwd.strip():
                    errors.append("agent.launch.cwd_path must be a non-empty string when cwd is custom")

            env = launch.get("env")
            if not isinstance(env, dict) or not all(isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip() for key, value in env.items()):
                errors.append("agent.launch.env must be an object of non-empty string pairs")

            if not isinstance(launch.get("requires_tty"), bool):
                errors.append("agent.launch.requires_tty must be a boolean")

            output = launch.get("output")
            if not isinstance(output, dict):
                errors.append("agent.launch.output must be an object")
            else:
                mode = output.get("mode")
                if mode not in {"exit_code", "stdout_json", "file"}:
                    errors.append("agent.launch.output.mode must be one of: exit_code, stdout_json, file")

        capabilities = selected_agent.get("capabilities", {})
        if not isinstance(capabilities, dict):
            errors.append("agent.capabilities must be an object")
        else:
            for key in ("non_interactive", "workspace_write_required"):
                if not isinstance(capabilities.get(key), bool):
                    errors.append(f"agent.capabilities.{key} must be a boolean")

        if not isinstance(agent.get("auto_bootstrap_compat"), bool):
            errors.append("agent.auto_bootstrap_compat must be a boolean")

    return errors, warnings


VALID_RULE_ACTIONS = {"fix", "skip", "needs_manual_review", "careful_fix", "auto_fix"}
VALID_RISK_LEVELS = {"low", "medium", "high"}


def validate_rule_policy(config: Any) -> Tuple[List[str], List[str]]:
    """Validate rule_policy.json configuration.

    Args:
        config: The parsed rule_policy JSON object.

    Returns:
        Tuple of (errors, warnings) lists.
    """
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(config, dict):
        return ["rule_policy config must be a JSON object"], warnings

    # Validate default exists and is valid
    default = config.get("default")
    if default is None:
        errors.append("missing required field: default")
    else:
        default_errors = _validate_action_config(default, "default")
        errors.extend(default_errors)

    # Validate actions
    actions = config.get("actions")
    if actions is None:
        errors.append("missing required field: actions")
    elif not isinstance(actions, dict):
        errors.append("actions must be an object")
    else:
        for rule_id, action_config in actions.items():
            if not isinstance(rule_id, str) or not rule_id.strip():
                errors.append("actions keys must be non-empty strings")
                continue
            if not isinstance(action_config, dict):
                errors.append(f"actions.{rule_id} must be an object")
                continue
            action_errors = _validate_action_config(action_config, f"actions.{rule_id}")
            errors.extend(action_errors)

    # Validate patterns
    patterns = config.get("patterns")
    if patterns is None:
        errors.append("missing required field: patterns")
    elif not isinstance(patterns, list):
        errors.append("patterns must be an array")
    else:
        for idx, pattern_config in enumerate(patterns):
            if not isinstance(pattern_config, dict):
                errors.append(f"patterns[{idx}] must be an object")
                continue
            pattern_errors = _validate_pattern_config(pattern_config, f"patterns[{idx}]")
            errors.extend(pattern_errors)

    return errors, warnings


def _validate_action_config(config: Dict[str, Any], path: str) -> List[str]:
    """Validate an action configuration object."""
    errors: List[str] = []

    action = config.get("action")
    if action is None:
        errors.append(f"{path}.action is required")
    elif not isinstance(action, str):
        errors.append(f"{path}.action must be a string")
    elif action not in VALID_RULE_ACTIONS:
        valid_actions = ", ".join(sorted(VALID_RULE_ACTIONS))
        errors.append(f"{path}.action must be one of: {valid_actions}")

    risk_level = config.get("risk_level")
    if risk_level is not None:
        if not isinstance(risk_level, str):
            errors.append(f"{path}.risk_level must be a string")
        elif risk_level not in VALID_RISK_LEVELS:
            valid_levels = ", ".join(sorted(VALID_RISK_LEVELS))
            errors.append(f"{path}.risk_level must be one of: {valid_levels}")

    risk_tags = config.get("risk_tags")
    if risk_tags is not None:
        if not isinstance(risk_tags, list):
            errors.append(f"{path}.risk_tags must be an array")
        elif not all(isinstance(tag, str) and tag.strip() for tag in risk_tags):
            errors.append(f"{path}.risk_tags must be an array of non-empty strings")

    risk_reason = config.get("risk_reason")
    if risk_reason is not None and not isinstance(risk_reason, str):
        errors.append(f"{path}.risk_reason must be a string")

    return errors


def _validate_pattern_config(config: Dict[str, Any], path: str) -> List[str]:
    """Validate a pattern configuration object."""
    errors: List[str] = []

    match_contains = config.get("match_contains")
    if match_contains is None:
        errors.append(f"{path}.match_contains is required")
    elif not isinstance(match_contains, str):
        errors.append(f"{path}.match_contains must be a string")
    elif not match_contains.strip():
        errors.append(f"{path}.match_contains must be a non-empty string")

    # Reuse action config validation for the rest
    action_errors = _validate_action_config(config, path)
    errors.extend(action_errors)

    return errors


def append_pipeline_event(
    runtime_dir: Path,
    event: str,
    stage: str,
    message: str,
    level: str = "info",
    chunk_index: Optional[int] = None,
    returncode: Optional[int] = None,
    data: Optional[Dict[str, Any]] = None,
) -> None:
    event_obj = {
        "time": now_iso(),
        "event": event,
        "stage": stage,
        "level": level,
        "message": message,
        "chunk_index": chunk_index,
        "returncode": returncode,
        "data": data or {},
    }
    runtime_dir.mkdir(parents=True, exist_ok=True)
    pipeline_log = runtime_dir / "pipeline.log"
    line_parts = [
        event_obj["time"],
        f"[{level}]",
        stage,
        event,
    ]
    if chunk_index is not None:
        line_parts.append(f"chunk={chunk_index}")
    if returncode is not None:
        line_parts.append(f"returncode={returncode}")
    line_parts.append(message)
    with open(pipeline_log, "a", encoding="utf-8") as f:
        f.write(" ".join(line_parts) + "\n")
    append_jsonl(runtime_dir / "run_log.jsonl", event_obj)

def reset_runtime_logs(runtime_dir: Path = RUNTIME_DIR) -> None:
    for name in ("pipeline.log", "run_log.jsonl"):
        path = runtime_dir / name
        if path.exists():
            path.unlink()
    logs_dir = runtime_dir / "logs"
    if logs_dir.exists():
        shutil.rmtree(logs_dir, ignore_errors=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

def copy_current_run_archive(runtime_dir: Path, reports_dir: Path, archive_dir: Path) -> None:
    runtime_archive = archive_dir / "runtime"
    reports_archive = archive_dir / "reports"
    logs_archive = archive_dir / "logs"
    runtime_archive.mkdir(parents=True, exist_ok=True)
    reports_archive.mkdir(parents=True, exist_ok=True)
    logs_archive.mkdir(parents=True, exist_ok=True)

    if runtime_dir.exists():
        for path in runtime_dir.iterdir():
            if path.is_file() and path.suffix == ".json":
                shutil.copy2(path, runtime_archive / path.name)
        for name in ("chunks", "results", "logs"):
            src_dir = runtime_dir / name
            dest_dir = runtime_archive / name
            dest_dir.mkdir(parents=True, exist_ok=True)
            if src_dir.exists():
                for src in src_dir.rglob("*"):
                    if src.is_dir():
                        continue
                    dest = dest_dir / src.relative_to(src_dir)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
        for name in ("pipeline.log", "run_log.jsonl"):
            src = runtime_dir / name
            if src.exists():
                shutil.copy2(src, logs_archive / name)

    if reports_dir.exists():
        for src in reports_dir.rglob("*"):
            if src.is_dir():
                continue
            dest = reports_archive / src.relative_to(reports_dir)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)

def archive_size_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for src in path.rglob("*"):
        if src.is_file():
            total += src.stat().st_size
    if path.is_file():
        total += path.stat().st_size
    return total

def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")

def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content.encode("utf-8"))


def _repair_json_string(raw: str, default: Any) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        first_nl = text.find("\n")
        if first_nl != -1:
            text = text[first_nl + 1:]
        if text.endswith("```"):
            text = text[:-3].rstrip()
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for close_char in ("}", "]"):
        if text.rstrip().endswith("," + close_char):
            cleaned = text.rstrip()[:-len(close_char)].rstrip().rstrip(",") + close_char
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
    return default if isinstance(default, (dict, list)) else {}


def _ensure_dict(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        return {"status_changes": data}
    return {}

def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return {} if default is None else default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        raw = path.read_text(encoding="utf-8")
        return _repair_json_string(raw, default if default is not None else {})

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


def prepare_chunk_staging_dir(staging_dir: Path) -> Path:
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)
    return staging_dir


def _load_required_json_object(path: Path) -> Dict[str, Any]:
    data = load_json(path, {})
    if isinstance(data, dict):
        return data
    coerced = _ensure_dict(data)
    if coerced:
        return coerced
    raise ValueError(f"expected JSON object or array: {path}")


def merge_file_change_index(base: Dict[str, Any], delta: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for file_path, delta_entry in delta.items():
        current_entry = merged.get(file_path, {})
        if not isinstance(current_entry, dict):
            current_entry = {}
        if not isinstance(delta_entry, dict):
            raise ValueError(f"file_change_index entry must be an object: {file_path}")

        next_entry = dict(current_entry)
        for key, value in delta_entry.items():
            if key == "edits":
                current_edits = current_entry.get("edits", [])
                if not isinstance(current_edits, list):
                    current_edits = []
                if not isinstance(value, list):
                    raise ValueError(f"file_change_index.edits must be a list: {file_path}")
                next_entry["edits"] = [*current_edits, *value]
            else:
                next_entry[key] = value
        merged[file_path] = next_entry
    return merged


def _as_string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _first_matching_str(item: Dict[str, Any], keys: Tuple[str, ...], default: str = "") -> str:
    for key in keys:
        candidate = str(item.get(key, "")).strip()
        if candidate:
            return candidate
    return default


_KNOWN_FILE_CHANGES_KEYS = (
    "file_changes", "files_changed", "files_touched", "files",
    "changes", "modified_files", "file_edits", "changed_files"
)
_KNOWN_FILE_PATH_KEYS = ("file", "file_path", "path", "filename")
_KNOWN_FCD_META_KEYS = frozenset({"chunk_index", "metadata", "notes", "summary", "status"})
_KNOWN_STATUS_CHANGES_KEYS = ("status_changes", "issue_status_changes", "issue_status_delta")
_STATUS_FIELD_ALIASES: Dict[str, str] = {
    "review_required_after_fix": "requires_review_after_fix",
    "requires_review": "requires_review_after_fix",
    "fix_method": "fix_summary",
    "status_after": "status",
    "status": "status",
}


def normalize_file_change_delta(
    base_file_change_index: Dict[str, Any],
    file_change_delta: Dict[str, Any],
    chunk_index: int,
) -> Dict[str, Any]:
    file_changes = None
    for key in _KNOWN_FILE_CHANGES_KEYS:
        candidate = file_change_delta.get(key)
        if isinstance(candidate, list):
            file_changes = candidate
            break
    if file_changes is not None:
        normalized: Dict[str, Any] = {}
        for item in file_changes:
            if isinstance(item, str) and item.strip():
                normalized[item.strip()] = {"edits": []}
                continue
            if not isinstance(item, dict):
                continue
            file_path = _first_matching_str(item, _KNOWN_FILE_PATH_KEYS)
            if not file_path:
                continue

            current_entry = normalized.get(file_path, {"edits": []})
            preview_entry = {
                "edits": [
                    *base_file_change_index.get(file_path, {}).get("edits", []),
                    *current_entry.get("edits", []),
                ]
            }
            edit_id = next_edit_id(file_path, {file_path: preview_entry})
            related_issue_keys = _as_string_list(item.get("linked_issues"))
            if not related_issue_keys:
                related_issue_keys = _as_string_list(item.get("linked_issue_keys"))
            edit = {
                "edit_id": edit_id,
                "summary": str(item.get("summary", "")).strip()
                or str(item.get("edit_summary", "")).strip()
                or str(item.get("change_type", "")).strip()
                or "staging imported change",
                "chunk_index": int(chunk_index),
                "related_issue_keys": related_issue_keys,
            }
            lines_modified = item.get("lines_modified")
            if isinstance(lines_modified, list):
                edit["lines_modified"] = list(lines_modified)
            else:
                lines_before = item.get("lines_before")
                lines_after = item.get("lines_after")
                if lines_before is not None:
                    edit["lines_before"] = lines_before
                if lines_after is not None:
                    edit["lines_after"] = lines_after
            change_type = str(item.get("change_type", "")).strip()
            if change_type:
                edit["change_type"] = change_type

            current_entry["edits"] = [*current_entry.get("edits", []), edit]
            normalized[file_path] = current_entry
        return normalized

    # Handle files_inspected format: inspection-only records with no code edits.
    # Agent may output this when issues are marked for manual review without changes.
    # Normalize to canonical {filepath: {edits: []}} WITHOUT generating edit records.
    files_inspected = file_change_delta.get("files_inspected")
    if isinstance(files_inspected, list):
        normalized: Dict[str, Any] = {}
        for item in files_inspected:
            if not isinstance(item, dict):
                continue
            file_path = _first_matching_str(item, _KNOWN_FILE_PATH_KEYS)
            if not file_path:
                continue
            entry: Dict[str, Any] = {"edits": []}
            change_summary = str(item.get("change_summary", "")).strip()
            if change_summary:
                entry["change_summary"] = change_summary
            normalized[file_path] = entry
        return normalized

    # Handle single-file format: {"file": "path/to/file", "edits": [...], ...}
    # This format is sometimes output by agents that don't wrap in file_changes array
    single_file_path = None
    for key in _KNOWN_FILE_PATH_KEYS:
        candidate = file_change_delta.get(key)
        if isinstance(candidate, str) and candidate.strip():
            single_file_path = candidate.strip()
            break
    if single_file_path is not None:
        file_path = single_file_path
        current_entry = {"edits": []}
        edits_raw = file_change_delta.get("edits", [])
        if isinstance(edits_raw, list):
            for edit_item in edits_raw:
                if not isinstance(edit_item, dict):
                    continue
                edit_id = str(edit_item.get("edit_id", "")).strip()
                if not edit_id:
                    preview_entry = {
                        "edits": [
                            *base_file_change_index.get(file_path, {}).get("edits", []),
                            *current_entry.get("edits", []),
                        ]
                    }
                    edit_id = next_edit_id(file_path, {file_path: preview_entry})
                related_issue_keys = _as_string_list(edit_item.get("related_issue_keys"))
                if not related_issue_keys:
                    related_issue_keys = _as_string_list(edit_item.get("linked_issues"))
                if not related_issue_keys:
                    related_issue_keys = _as_string_list(edit_item.get("linked_issue_keys"))
                edit = {
                    "edit_id": edit_id,
                    "summary": str(edit_item.get("summary", "")).strip()
                    or str(edit_item.get("edit_summary", "")).strip()
                    or str(file_change_delta.get("change_summary", "")).strip()
                    or str(file_change_delta.get("summary", "")).strip()
                    or "staging imported change",
                    "chunk_index": int(edit_item.get("chunk_index", chunk_index)),
                    "related_issue_keys": related_issue_keys,
                }
                lines_modified = edit_item.get("lines_modified")
                if isinstance(lines_modified, list):
                    edit["lines_modified"] = list(lines_modified)
                else:
                    lines_before = edit_item.get("lines_before")
                    lines_after = edit_item.get("lines_after")
                    if lines_before is not None:
                        edit["lines_before"] = lines_before
                    if lines_after is not None:
                        edit["lines_after"] = lines_after
                change_type = str(edit_item.get("change_type", "")).strip()
                if change_type:
                    edit["change_type"] = change_type
                current_entry["edits"] = [*current_entry.get("edits", []), edit]
        return {file_path: current_entry}

    # --- Structural inference: detect list-of-dict-with-file under unknown wrapper key ---
    for key, value in file_change_delta.items():
        if key in _KNOWN_FCD_META_KEYS:
            continue
        if (isinstance(value, list) and value
                and isinstance(value[0], dict)
                and any(value[0].get(k) for k in _KNOWN_FILE_PATH_KEYS)):
            return normalize_file_change_delta(
                base_file_change_index, {"file_changes": value}, chunk_index
            )
        if (isinstance(value, list) and value
                and isinstance(value[0], str)):
            normalized = {}
            for fname in value:
                if isinstance(fname, str) and fname.strip():
                    normalized[fname.strip()] = {"edits": []}
            return normalized
        if isinstance(value, str) and ("/" in value or value.endswith((".c", ".h", ".cpp", ".hpp"))):
            return {value.strip(): {"edits": []}}

    normalized = {}
    for file_path, delta_entry in file_change_delta.items():
        if file_path in _KNOWN_FCD_META_KEYS:
            continue
        if not isinstance(delta_entry, dict):
            print(f"[normalize] WARNING: skipping file_change_delta['{file_path}'] "
                  f"(expected dict, got {type(delta_entry).__name__})")
            continue
        normalized[file_path] = delta_entry
    return normalized


def _build_issue_edit_index(file_change_delta: Dict[str, Any]) -> Dict[str, List[str]]:
    issue_edit_ids: Dict[str, List[str]] = {}
    for file_data in file_change_delta.values():
        if not isinstance(file_data, dict):
            continue
        for edit in file_data.get("edits", []):
            if not isinstance(edit, dict):
                continue
            edit_id = str(edit.get("edit_id", "")).strip()
            if not edit_id:
                continue
            related_issue_keys = _as_string_list(edit.get("related_issue_keys"))
            if not related_issue_keys:
                related_issue_keys = _as_string_list(edit.get("linked_issues"))
            if not related_issue_keys:
                related_issue_keys = _as_string_list(edit.get("linked_issue_keys"))
            for issue_key in related_issue_keys:
                issue_edit_ids.setdefault(issue_key, []).append(edit_id)
    return issue_edit_ids


_PASSTHROUGH_STATUS_KEYS = ("risk_level", "risk_reason", "requires_review_after_fix", "verified", "fix_summary")
_REASON_ALIAS_KEYS = ("reason", "blocker_reason", "message")


def _normalize_status_item(
    item: Dict[str, Any],
    issue_key: str,
    edit_ids: List[str],
    chunk_index: int,
) -> Dict[str, Any]:
    patch: Dict[str, Any] = {
        "chunk_index": int(chunk_index),
        "edit_ids": edit_ids,
    }
    new_status = ""
    for alias in ("new_status", "status_after", "status"):
        candidate = str(item.get(alias, "")).strip()
        if candidate:
            new_status = candidate
            break
    if new_status:
        patch["status"] = new_status
    for key in _PASSTHROUGH_STATUS_KEYS:
        value = item.get(key)
        if value is not None:
            patch[key] = value
    for alias_key, canonical_key in _STATUS_FIELD_ALIASES.items():
        if alias_key not in item or canonical_key in patch:
            continue
        patch[canonical_key] = item[alias_key]
    reason = ""
    for alias in _REASON_ALIAS_KEYS:
        candidate = str(item.get(alias, "")).strip()
        if candidate:
            reason = candidate
            break
    if reason:
        patch["reason"] = reason
    return patch


def normalize_issue_status_delta(
    issue_status_delta: Dict[str, Any],
    file_change_delta: Dict[str, Any],
    chunk_index: int,
) -> Dict[str, Any]:
    status_changes = None
    for key in _KNOWN_STATUS_CHANGES_KEYS:
        candidate = issue_status_delta.get(key)
        if isinstance(candidate, list):
            status_changes = candidate
            break
    if isinstance(status_changes, list):
        issue_edit_ids = _build_issue_edit_index(file_change_delta)
        normalized: Dict[str, Any] = {}
        for item in status_changes:
            if not isinstance(item, dict):
                continue
            issue_key = str(item.get("issue_key", "")).strip()
            if not issue_key:
                continue
            patch = _normalize_status_item(item, issue_key, issue_edit_ids.get(issue_key, []), chunk_index)
            normalized[issue_key] = patch
        return normalized

    # Handle single-issue format: {"issue_key": "...", "new_status": "fixed", ...}
    # This format is sometimes output by agents that don't wrap in status_changes array
    single_issue_key = issue_status_delta.get("issue_key")
    if isinstance(single_issue_key, str) and single_issue_key.strip():
        issue_key = single_issue_key.strip()
        issue_edit_ids = _build_issue_edit_index(file_change_delta)
        patch = _normalize_status_item(issue_status_delta, issue_key, issue_edit_ids.get(issue_key, []), chunk_index)
        return {issue_key: patch}

    _KNOWN_ISD_META_KEYS = frozenset({
        "chunk_index", "metadata", "notes",
        "issue_status_delta", "status_changes", "issue_status_changes",
    })
    normalized = {}
    issue_edit_ids = _build_issue_edit_index(file_change_delta)
    for issue_key, patch in issue_status_delta.items():
        if issue_key in _KNOWN_ISD_META_KEYS:
            continue
        if not isinstance(patch, dict):
            print(f"[normalize] WARNING: skipping issue_status_delta['{issue_key}'] "
                  f"(expected dict, got {type(patch).__name__})")
            continue
        normalized_patch = dict(patch)
        if "chunk_index" not in normalized_patch:
            normalized_patch["chunk_index"] = int(chunk_index)
        if "edit_ids" not in normalized_patch:
            normalized_patch["edit_ids"] = issue_edit_ids.get(issue_key, [])
        normalized[issue_key] = normalized_patch
    return normalized


def import_chunk_staging_artifacts(
    staging_dir: Path,
    chunk_index: int,
    runtime_dir: Path = RUNTIME_DIR,
    results_dir: Path = RESULTS_DIR,
) -> Dict[str, Path]:
    issue_status_delta_path = staging_dir / "issue_status_delta.json"
    file_change_delta_path = staging_dir / "file_change_delta.json"
    chunk_result_json_path = staging_dir / "chunk_result.json"
    chunk_result_md_path = staging_dir / "chunk_result.md"

    for path in (
        issue_status_delta_path,
        file_change_delta_path,
        chunk_result_json_path,
        chunk_result_md_path,
    ):
        if not path.exists():
            raise FileNotFoundError(f"missing staging artifact: {path}")

    issue_status = _load_required_json_object(runtime_dir / "issue_status.json")
    raw_issue_status_delta = _load_required_json_object(issue_status_delta_path)
    file_change_index = _load_required_json_object(runtime_dir / "file_change_index.json")
    raw_file_change_delta = _load_required_json_object(file_change_delta_path)

    # --- Normalize with degradation safety net ---
    try:
        file_change_delta = normalize_file_change_delta(file_change_index, raw_file_change_delta, chunk_index)
        merged_file_change_index = merge_file_change_index(file_change_index, file_change_delta)
    except Exception as exc:
        print(f"[import] WARNING: file_change_delta normalization failed for chunk {chunk_index}: "
              f"{exc} — degrading to empty file changes")
        file_change_delta = {}
        merged_file_change_index = dict(file_change_index)

    try:
        issue_status_delta = normalize_issue_status_delta(raw_issue_status_delta, file_change_delta, chunk_index)
    except Exception as exc:
        print(f"[import] WARNING: issue_status_delta normalization failed for chunk {chunk_index}: "
              f"{exc} — degrading to empty status delta")
        issue_status_delta = {}

    issue_status.update(issue_status_delta)
    save_json(runtime_dir / "issue_status.json", issue_status)
    save_json(runtime_dir / "file_change_index.json", merged_file_change_index)

    imported_json_path = results_dir / f"chunk_{int(chunk_index):03d}_result.json"
    imported_md_path = results_dir / f"chunk_{int(chunk_index):03d}_result.md"
    imported_json_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(chunk_result_json_path, imported_json_path)
    shutil.copy2(chunk_result_md_path, imported_md_path)

    return {
        "issue_status_path": runtime_dir / "issue_status.json",
        "file_change_index_path": runtime_dir / "file_change_index.json",
        "chunk_result_json_path": imported_json_path,
        "chunk_result_md_path": imported_md_path,
    }
