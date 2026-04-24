from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    RUN_ID_RE,
    CONFIG_DIR,
    CHUNKS_DIR,
    RESULTS_DIR,
    RUNTIME_DIR,
    append_pipeline_event,
    build_issue_key,
    ensure_dirs,
    load_json,
    next_run_id,
    now_iso,
    normalize_msg,
    reset_runtime_logs,
    save_json,
    validate_rule_policy,
)

VALID_STRATEGIES = {"conservative", "all_auto"}

def is_misra_rule(rule_id: str, detect_prefixes: List[str]) -> bool:
    rid = (rule_id or "").lower()
    return any(rid.startswith(prefix.lower()) for prefix in detect_prefixes)

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split cppcheck XML into agent-ready chunks.")
    parser.add_argument(
        "--strategy",
        choices=sorted(VALID_STRATEGIES),
        default=None,
        help="Override fix_strategy.mode from pipeline.json for this split run.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Override run ID for this fresh split, format YYYYMMDD-XXX.",
    )
    return parser.parse_args(sys.argv[1:] if argv is None else argv)

def resolve_strategy(config: Dict[str, Any], override: Optional[str]) -> str:
    if override:
        return override
    mode = config.get("fix_strategy", {}).get("mode", "conservative")
    if mode not in VALID_STRATEGIES:
        valid = ", ".join(sorted(VALID_STRATEGIES))
        raise SystemExit(f"Invalid fix_strategy.mode '{mode}'. Valid values: {valid}.")
    return mode

def resolve_cppcheck_xml_path(config: Dict[str, Any]) -> Path:
    configured = str(config.get("input", {}).get("cppcheck_xml", "cppcheck.xml")).strip() or "cppcheck.xml"
    xml_path = Path(configured)
    if xml_path.is_absolute():
        return xml_path
    return CONFIG_DIR.parents[1] / xml_path

def as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]

def find_policy(rule_id: str, msg: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    rid = (rule_id or "").lower()
    text = f"{rid} {msg}".lower()

    actions = policy.get("actions", {})
    for key, value in actions.items():
        if rid == key.lower():
            return dict(value)

    for item in policy.get("patterns", []):
        if item["match_contains"].lower() in text:
            return dict(item)

    return dict(policy.get("default", {"action": "needs_manual_review"}))

def classify_issue(
    rule_id: str,
    msg: str,
    policy: Dict[str, Any],
    strategy: str,
    strategy_config: Dict[str, Any],
) -> Dict[str, Any]:
    item = find_policy(rule_id, msg, policy)
    action = item.get("action", "needs_manual_review")
    risk_level = item.get("risk_level")
    if not risk_level:
        risk_level = "high" if action == "needs_manual_review" else "low"

    risk_tags = as_list(item.get("risk_tags"))
    risk_reason = item.get("risk_reason", "")
    strategy_action = action
    requires_review_after_fix = False

    if strategy == "all_auto" and action == "needs_manual_review":
        strategy_action = "careful_fix"

    require_high_risk_review = bool(strategy_config.get("require_review_after_high_risk_fix", True))
    if strategy == "all_auto" and risk_level == "high" and require_high_risk_review:
        requires_review_after_fix = True

    return {
        "action": action,
        "strategy_action": strategy_action,
        "risk_level": risk_level,
        "risk_tags": risk_tags,
        "risk_reason": risk_reason,
        "requires_review_after_fix": requires_review_after_fix,
    }

def parse_xml(xml_file: Path, config: Dict[str, Any], policy: Dict[str, Any], strategy: str) -> List[Dict[str, Any]]:
    try:
        tree = ET.parse(xml_file)
    except FileNotFoundError as exc:
        raise SystemExit(f"cppcheck XML file not found: {xml_file}") from exc
    except ET.ParseError as exc:
        raise SystemExit(f"Invalid cppcheck XML file '{xml_file}': {exc}") from exc
    root = tree.getroot()
    include_severity = set(config["filter"]["include_severity"])
    exclude_information = bool(config["filter"].get("exclude_information", True))
    detect_prefixes = config["misra"]["detect_prefixes"]
    strategy_config = config.get("fix_strategy", {})

    dedup = {}
    for err in root.findall(".//error"):
        severity = err.attrib.get("severity", "")
        if severity not in include_severity:
            continue
        if exclude_information and severity == "information":
            continue

        rule_id = err.attrib.get("id", "")
        msg = err.attrib.get("msg", "") or err.attrib.get("verbose", "")
        locations = err.findall("location")
        if not locations:
            continue

        loc = locations[0]
        file_path = loc.attrib.get("file", "<unknown>")
        try:
            line = int(loc.attrib.get("line", "0"))
        except ValueError as exc:
            raise SystemExit(
                f"Invalid line number in cppcheck XML for file '{file_path}': "
                f"{loc.attrib.get('line')!r}"
            ) from exc
        issue_policy = classify_issue(rule_id, msg, policy, strategy, strategy_config)

        key = (file_path, line, rule_id, normalize_msg(msg))
        if key in dedup:
            continue

        dedup[key] = {
            "issue_key": build_issue_key(file_path, line, rule_id, msg),
            "file": file_path,
            "line": line,
            "severity": severity,
            "rule_id": rule_id,
            "msg": msg,
            "is_misra": is_misra_rule(rule_id, detect_prefixes),
            "fix_strategy": strategy,
            **issue_policy,
        }

    return list(dedup.values())

def build_chunks(issues: List[Dict[str, Any]], config: Dict[str, Any]) -> List[List[Dict[str, Any]]]:
    max_issues = int(config["chunking"]["max_issues_per_chunk"])
    max_files = int(config["chunking"]["max_files_per_chunk"])
    split_high = bool(config["chunking"].get("split_high_risk_alone", True))

    high = []
    grouped = defaultdict(list)

    for item in issues:
        if split_high and item["strategy_action"] == "needs_manual_review":
            high.append(item)
        else:
            grouped[item["file"]].append(item)

    chunks = [[x] for x in high]

    current = []
    current_files = set()

    for file_path, items in sorted(grouped.items()):
        items = sorted(items, key=lambda x: (x["line"], x["rule_id"]))
        if (
            len(current) + len(items) > max_issues
            or (file_path not in current_files and len(current_files) >= max_files)
        ):
            if current:
                chunks.append(current)
            current = []
            current_files = set()

        current.extend(items)
        current_files.add(file_path)

    if current:
        chunks.append(current)

    return chunks

def clear_previous_run_files() -> None:
    for path in CHUNKS_DIR.glob("chunk_*.json"):
        path.unlink()
    for pattern in ["chunk_*_result.json", "chunk_*_result.md"]:
        for path in RESULTS_DIR.glob(pattern):
            path.unlink()

def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    config = load_json(CONFIG_DIR / "pipeline.json", {})
    policy = load_json(CONFIG_DIR / "rule_policy.json", {})
    policy_errors, policy_warnings = validate_rule_policy(policy)
    if policy_errors:
        for err in policy_errors:
            print(f"rule_policy.json validation error: {err}")
        raise SystemExit(f"rule_policy.json validation failed with {len(policy_errors)} errors")

    strategy = resolve_strategy(config, args.strategy)
    run_id = args.run_id or next_run_id()
    if not RUN_ID_RE.match(run_id):
        raise SystemExit(f"Invalid --run-id '{run_id}'. Expected format: YYYYMMDD-XXX.")
    started_at = now_iso()
    xml_file = resolve_cppcheck_xml_path(config)

    issues = parse_xml(xml_file, config, policy, strategy)
    ensure_dirs()
    reset_runtime_logs(RUNTIME_DIR)
    append_pipeline_event(
        RUNTIME_DIR,
        event="split_started",
        stage="split",
        message="开始拆分 cppcheck.xml。",
        data={
            "run_id": run_id,
            "xml_file": str(xml_file).replace("\\", "/"),
            "strategy": strategy,
        },
    )
    clear_previous_run_files()
    save_json(RUNTIME_DIR / "issues_master.json", issues)

    issue_status = {
        x["issue_key"]: {
            "status": "pending",
            "file": x["file"],
            "line": x["line"],
            "severity": x["severity"],
            "rule_id": x["rule_id"],
            "is_misra": x["is_misra"],
            "fix_strategy": x["fix_strategy"],
            "action": x["action"],
            "strategy_action": x["strategy_action"],
            "risk_level": x["risk_level"],
            "risk_tags": x["risk_tags"],
            "risk_reason": x["risk_reason"],
            "requires_review_after_fix": x["requires_review_after_fix"],
            "chunk_index": None,
            "edit_ids": [],
            "reason": "",
            "verified": False,
        }
        for x in issues
    }
    save_json(RUNTIME_DIR / "issue_status.json", issue_status)
    save_json(RUNTIME_DIR / "file_change_index.json", {})

    chunks = build_chunks(issues, config)
    total = len(chunks)
    for idx, chunk in enumerate(chunks, start=1):
        payload = {
            "chunk_index": idx,
            "chunk_total": total,
            "issue_count": len(chunk),
            "files": sorted({x["file"] for x in chunk}),
            "fix_strategy": strategy,
            "contains_high_risk": any(x.get("risk_level") == "high" for x in chunk),
            "requires_review_after_fix_count": sum(1 for x in chunk if x.get("requires_review_after_fix")),
            "issues": chunk,
        }
        save_json(CHUNKS_DIR / f"chunk_{idx:03d}.json", payload)

    progress = {
        "run_id": run_id,
        "started_at": started_at,
        "xml_file": str(xml_file).replace("\\", "/"),
        "total_chunks": total,
        "completed_chunks": [],
        "failed_chunks": [],
        "current_chunk": 1 if total else None,
        "fix_strategy": strategy,
        "status": "ready",
    }
    save_json(RUNTIME_DIR / "progress.json", progress)
    append_pipeline_event(
        RUNTIME_DIR,
        event="split_completed",
        stage="split",
        message="拆分完成。",
        data={
            "run_id": run_id,
            "total_issues": len(issues),
            "total_chunks": total,
            "strategy": strategy,
        },
    )

    print(f"Generated {total} chunks from {len(issues)} issues with strategy '{strategy}' (run_id={run_id}).")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
