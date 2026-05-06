"""Policy initialization and management commands.

Commands:
  policy init --template <name>    Initialize policy from template
  policy list [--rule-id <pattern>]  List templates or rules matching pattern
  policy test --rule-id <id> --file <path>  Test rule matching for file
  policy add --rule-id <id> --action <action>  Add/update a rule
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Template directory relative to this module
TEMPLATES_DIR = Path(__file__).parent.parent / "config" / "templates"

# Default policy file path
DEFAULT_POLICY_PATH = Path(__file__).parent.parent / "config" / "rule_policy.json"

AVAILABLE_TEMPLATES = {
    "misra_c2012_conservative": "MISRA C:2012 conservative policy - all rules require manual review",
    "misra_c2012_relaxed": "MISRA C:2012 relaxed policy - low risk auto_fix, medium risk careful_fix",
    "autosar_baseline": "AUTOSAR baseline policy - RTE/MCAL/BSW require manual review",
    "cppcheck_common": "Cppcheck native rule policy - common error/warning strategies",
}

VALID_RULE_ACTIONS = {"fix", "skip", "needs_manual_review", "careful_fix", "auto_fix"}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage policy configuration for cppcheck/MISRA agent pipeline."
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available templates and exit.",
    )
    parser.add_argument(
        "--policy-file",
        "-p",
        default=None,
        help="Path to policy file. Default: .agents/config/rule_policy.json",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # init subcommand
    init_parser = subparsers.add_parser(
        "init", help="Initialize policy configuration from one or more templates (merged)."
    )
    init_parser.add_argument(
        "--template",
        "-t",
        action="append",
        default=[],
        dest="templates",
        choices=list(AVAILABLE_TEMPLATES.keys()),
        help="Template name(s) to initialize from. Can be specified multiple times to merge templates. If omitted, defaults to first available template.",
    )
    init_parser.add_argument(
        "--output",
        "-o",
        default=None,
        help="Output path for the policy file. Default: .agents/config/rule_policy.json",
    )
    init_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Overwrite existing output file if it exists.",
    )

    # list subcommand
    list_parser = subparsers.add_parser(
        "list", help="List available templates or rules matching pattern."
    )
    list_parser.add_argument(
        "--rule-id",
        "-r",
        default=None,
        help="Filter rules by pattern (supports wildcards like 'misra*' or '*variable*').",
    )

    # test subcommand
    test_parser = subparsers.add_parser(
        "test", help="Test rule matching for a specific file."
    )
    test_parser.add_argument(
        "--rule-id",
        "-r",
        required=True,
        help="Rule ID to test (e.g., 'unusedVariable', 'misra-c2012-2.2').",
    )
    test_parser.add_argument(
        "--file",
        "-f",
        required=True,
        help="File path to test against patterns.",
    )

    # add subcommand
    add_parser = subparsers.add_parser(
        "add", help="Add or update a rule action."
    )
    add_parser.add_argument(
        "--rule-id",
        "-r",
        required=True,
        help="Rule ID to add or update (e.g., 'unusedVariable', 'misra-c2012-2.2').",
    )
    add_parser.add_argument(
        "--action",
        "-a",
        required=True,
        choices=sorted(VALID_RULE_ACTIONS),
        help="Action for the rule: fix, skip, needs_manual_review, careful_fix, auto_fix.",
    )
    add_parser.add_argument(
        "--risk-level",
        "-l",
        choices=["low", "medium", "high"],
        default=None,
        help="Risk level for the rule (default: auto-assigned based on action).",
    )
    add_parser.add_argument(
        "--risk-tags",
        "-t",
        default=None,
        help="Comma-separated risk tags (e.g., 'volatile,concurrency').",
    )
    add_parser.add_argument(
        "--risk-reason",
        "-m",
        default=None,
        help="Reason for the risk assignment.",
    )
    add_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force overwrite if rule already exists.",
    )

    return parser.parse_args(argv)


def list_templates() -> None:
    """Print available templates with descriptions."""
    print("Available templates:\n")
    for name, description in AVAILABLE_TEMPLATES.items():
        print(f"  {name}:")
        print(f"    {description}\n")


def load_policy(policy_path: Path) -> Dict[str, Any]:
    """Load policy from file, returning empty dict on error."""
    if not policy_path.exists():
        print(f"Error: Policy file not found: {policy_path}", file=sys.stderr)
        return {}
    try:
        with open(policy_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in policy file: {e}", file=sys.stderr)
        return {}


def find_policy_for_rule(rule_id: str, text: str, policy: Dict[str, Any]) -> Dict[str, Any]:
    """Find the matching policy for a rule ID and text.

    Args:
        rule_id: The rule ID to match.
        text: Additional text (e.g., file path, message) for pattern matching.
        policy: The policy dictionary.

    Returns:
        The matching action configuration with source info added.
    """
    rid = (rule_id or "").lower()
    combined_text = f"{rid} {text}".lower()

    # Check for exact rule ID match
    actions = policy.get("actions", {})
    for key, value in actions.items():
        if rid == key.lower():
            result = dict(value)
            result["_source"] = "actions"
            result["_matched_key"] = key
            return result

    # Check patterns for text matching
    for item in policy.get("patterns", []):
        match_contains = item.get("match_contains", "")
        if match_contains.lower() in combined_text:
            result = dict(item)
            result["_source"] = "patterns"
            result["_matched_pattern"] = match_contains
            return result

    # Return default
    result = dict(policy.get("default", {"action": "needs_manual_review"}))
    result["_source"] = "default"
    return result


def list_rules(policy_path: Path, pattern: Optional[str]) -> int:
    """List rules from policy file, optionally filtered by pattern.

    Args:
        policy_path: Path to the policy file.
        pattern: Optional glob pattern to filter rule IDs.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    policy = load_policy(policy_path)
    if not policy:
        return 1

    # Show default policy
    default = policy.get("default", {})
    print("Default Policy:")
    print(f"  action: {default.get('action', 'N/A')}")
    print(f"  risk_level: {default.get('risk_level', 'N/A')}")
    if default.get("risk_tags"):
        print(f"  risk_tags: {', '.join(default.get('risk_tags', []))}")
    if default.get("risk_reason"):
        print(f"  risk_reason: {default.get('risk_reason')}")
    print()

    # Show matching rules from actions
    actions = policy.get("actions", {})
    matching_rules = []

    if pattern:
        pattern_lower = pattern.lower()
        for rule_id in actions:
            # Support glob-style patterns
            if fnmatch.fnmatch(rule_id.lower(), pattern_lower):
                matching_rules.append(rule_id)
            elif pattern_lower in rule_id.lower():
                matching_rules.append(rule_id)
    else:
        matching_rules = list(actions.keys())

    if matching_rules:
        print(f"Rules ({len(matching_rules)} matching):")
        for rule_id in sorted(matching_rules):
            action_config = actions[rule_id]
            action = action_config.get("action", "N/A")
            risk_level = action_config.get("risk_level", "N/A")
            tags = action_config.get("risk_tags", [])
            reason = action_config.get("risk_reason", "")

            print(f"\n  {rule_id}:")
            print(f"    action: {action}")
            print(f"    risk_level: {risk_level}")
            if tags:
                print(f"    risk_tags: {', '.join(tags)}")
            if reason:
                print(f"    risk_reason: {reason}")
        print()

    # Show patterns
    patterns = policy.get("patterns", [])
    if patterns:
        print(f"\nPatterns ({len(patterns)} defined):")
        for idx, pattern_config in enumerate(patterns):
            match_contains = pattern_config.get("match_contains", "")
            action = pattern_config.get("action", "N/A")
            risk_level = pattern_config.get("risk_level", "N/A")
            print(f"\n  [{idx}] match_contains: '{match_contains}'")
            print(f"      action: {action}")
            print(f"      risk_level: {risk_level}")

    return 0


def test_rule(policy_path: Path, rule_id: str, file_path: str) -> int:
    """Test rule matching for a specific file.

    Args:
        policy_path: Path to the policy file.
        rule_id: Rule ID to test.
        file_path: File path to test against patterns.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    policy = load_policy(policy_path)
    if not policy:
        return 1

    print(f"Testing rule: {rule_id}")
    print(f"File path: {file_path}")
    print()

    result = find_policy_for_rule(rule_id, file_path, policy)

    source = result.pop("_source", "unknown")
    matched_key = result.pop("_matched_key", None)
    matched_pattern = result.pop("_matched_pattern", None)

    print(f"Match source: {source}")
    if matched_key:
        print(f"Matched rule ID: {matched_key}")
    if matched_pattern:
        print(f"Matched pattern: '{matched_pattern}'")
    print()

    print("Resolved policy:")
    print(f"  action: {result.get('action', 'N/A')}")
    print(f"  risk_level: {result.get('risk_level', 'N/A')}")
    if result.get("risk_tags"):
        print(f"  risk_tags: {', '.join(result.get('risk_tags', []))}")
    if result.get("risk_reason"):
        print(f"  risk_reason: {result.get('risk_reason')}")

    return 0


def add_rule(
    policy_path: Path,
    rule_id: str,
    action: str,
    risk_level: Optional[str],
    risk_tags: Optional[str],
    risk_reason: Optional[str],
    force: bool,
) -> int:
    """Add or update a rule in the policy file.

    Args:
        policy_path: Path to the policy file.
        rule_id: Rule ID to add or update.
        action: Action for the rule.
        risk_level: Optional risk level.
        risk_tags: Optional comma-separated risk tags.
        risk_reason: Optional risk reason.
        force: Force overwrite if rule already exists.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    policy = load_policy(policy_path)
    if not policy:
        return 1

    actions = policy.get("actions", {})

    # Check if rule already exists (before we modify)
    rule_already_exists = rule_id in actions

    # Check if rule already exists
    if rule_already_exists and not force:
        print(
            f"Error: Rule '{rule_id}' already exists. Use --force to overwrite.",
            file=sys.stderr,
        )
        return 1

    # Build the action config
    action_config: Dict[str, Any] = {"action": action}

    # Auto-assign risk_level if not provided
    if risk_level:
        action_config["risk_level"] = risk_level
    else:
        # Auto-assign based on action
        if action in ("auto_fix", "fix"):
            action_config["risk_level"] = "low"
        elif action == "careful_fix":
            action_config["risk_level"] = "medium"
        else:
            action_config["risk_level"] = "high"

    # Add risk_tags if provided
    if risk_tags:
        tags_list = [tag.strip() for tag in risk_tags.split(",") if tag.strip()]
        if tags_list:
            action_config["risk_tags"] = tags_list

    # Add risk_reason if provided
    if risk_reason:
        action_config["risk_reason"] = risk_reason

    # Update the policy
    if "actions" not in policy:
        policy["actions"] = {}
    policy["actions"][rule_id] = action_config

    # Validate the updated policy
    from common import validate_rule_policy

    errors, warnings = validate_rule_policy(policy)
    if errors:
        print("Error: Validation failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if warnings:
        print("Warnings:")
        for warning in warnings:
            print(f"  - {warning}")

    # Save the policy
    try:
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        with open(policy_path, "w", encoding="utf-8") as f:
            json.dump(policy, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error: Failed to save policy file: {e}", file=sys.stderr)
        return 1

    action_type = "Updated" if rule_already_exists else "Added"
    print(f"{action_type} rule '{rule_id}':")
    print(f"  action: {action_config['action']}")
    print(f"  risk_level: {action_config['risk_level']}")
    if "risk_tags" in action_config:
        print(f"  risk_tags: {', '.join(action_config['risk_tags'])}")
    if "risk_reason" in action_config:
        print(f"  risk_reason: {action_config['risk_reason']}")
    print(f"\nPolicy file: {policy_path}")

    return 0


def _select_template_interactive() -> List[str]:
    """Interactively select one or more templates when none specified."""
    template_list = list(AVAILABLE_TEMPLATES.items())
    default_template = "misra_c2012_relaxed"
    if not sys.stdin.isatty():
        print(f"Warning: No --template specified and not running in a terminal. Using default: '{default_template}'", file=sys.stderr)
        return [default_template]

    print("Available templates:\n")
    for i, (name, description) in enumerate(template_list, 1):
        print(f"  [{i}] {name:30s} - {description}")
    print()

    default_choice = "2"
    while True:
        choice = input(f"Select template number(s) [{default_choice}] (comma/space-separated for multiple): ").strip()
        if not choice:
            choice = default_choice
        # Split by comma or whitespace
        parts = choice.replace(",", " ").split()
        try:
            indices = [int(p) for p in parts]
        except ValueError:
            print(f"Invalid input. Enter numbers between 1 and {len(template_list)}.", file=sys.stderr)
            continue
        if all(1 <= idx <= len(template_list) for idx in indices):
            selected = [template_list[idx - 1][0] for idx in indices]
            if len(selected) == 1:
                print(f"\nSelected: {selected[0]}")
            else:
                print(f"\nSelected: {', '.join(selected)}")
            return selected
        print(f"Invalid choice. Enter numbers between 1 and {len(template_list)}.", file=sys.stderr)


def init_policy(templates: List[str], output_path: Path, force: bool) -> int:
    """Initialize policy from one or more templates (merged)."""
    if not templates:
        templates = _select_template_interactive()

    if output_path.exists() and not force:
        print(
            f"Error: Output file already exists: {output_path}",
            file=sys.stderr,
        )
        print("Use --force to overwrite.", file=sys.stderr)
        return 1

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load and merge all templates (last one wins on conflict)
    merged: Dict[str, Any] = {
        "$schema": "../rule_policy.schema.json",
        "_description": f"Merged from: {', '.join(templates)}",
        "default": {"action": "needs_manual_review", "risk_level": "high", "risk_tags": [], "risk_reason": ""},
        "actions": {},
        "patterns": [],
    }
    merged_descriptions: List[str] = []

    for name in templates:
        template_file = TEMPLATES_DIR / f"{name}.json"
        if not template_file.exists():
            print(f"Error: Template file not found: {template_file}", file=sys.stderr)
            return 1
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged_descriptions.append(data.get("_description", name))
            # Merge actions (later template overrides earlier)
            for key, value in data.get("actions", {}).items():
                merged["actions"][key] = value
            # Merge patterns (dedup by match_contains)
            seen_patterns = {p["match_contains"] for p in merged["patterns"]}
            for p in data.get("patterns", []):
                if p["match_contains"] not in seen_patterns:
                    merged["patterns"].append(p)
                    seen_patterns.add(p["match_contains"])
            # Use first template's default if available
            if "default" in data and merged["default"] == {"action": "needs_manual_review", "risk_level": "high", "risk_tags": [], "risk_reason": ""}:
                merged["default"] = data["default"]
        except json.JSONDecodeError as e:
            print(f"Error: Template '{name}' is not valid JSON: {e}", file=sys.stderr)
            return 1

    # Write merged policy
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        print(f"Policy initialized from template(s): {', '.join(templates)}")
        print(f"Output: {output_path}")
        print(f"Rules configured: {len(merged['actions'])}")
        print(f"Patterns configured: {len(merged['patterns'])}")
        return 0
    except Exception as e:
        print(f"Error writing policy file: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for policy command."""
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    # Determine policy file path
    if hasattr(args, "policy_file") and args.policy_file:
        policy_path = Path(args.policy_file)
    else:
        policy_path = DEFAULT_POLICY_PATH

    # Handle --list flag at top level
    if args.list:
        list_templates()
        return 0

    # Handle "list" subcommand
    if args.subcommand == "list":
        if hasattr(args, "rule_id") and args.rule_id:
            return list_rules(policy_path, args.rule_id)
        else:
            list_templates()
            return 0

    # Handle "init" subcommand
    if args.subcommand == "init":
        if args.output is None:
            # Default output path
            output_path = Path.cwd() / ".agents" / "config" / "rule_policy.json"
        else:
            output_path = Path(args.output)

        return init_policy(args.templates, output_path, args.force)

    # Handle "test" subcommand
    if args.subcommand == "test":
        return test_rule(policy_path, args.rule_id, args.file)

    # Handle "add" subcommand
    if args.subcommand == "add":
        return add_rule(
            policy_path=policy_path,
            rule_id=args.rule_id,
            action=args.action,
            risk_level=args.risk_level,
            risk_tags=args.risk_tags,
            risk_reason=args.risk_reason,
            force=args.force,
        )

    # No subcommand and no --list, show help
    list_templates()
    return 0