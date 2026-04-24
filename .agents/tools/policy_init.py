"""Policy initialization command - copies templates to user-specified path."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

# Template directory relative to this module
TEMPLATES_DIR = Path(__file__).parent.parent / "config" / "templates"

AVAILABLE_TEMPLATES = {
    "misra_c2012_conservative": "MISRA C:2012 conservative policy - all rules require manual review",
    "misra_c2012_relaxed": "MISRA C:2012 relaxed policy - low risk auto_fix, medium risk careful_fix",
    "autosar_baseline": "AUTOSAR baseline policy - RTE/MCAL/BSW require manual review",
    "cppcheck_common": "Cppcheck native rule policy - common error/warning strategies",
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize policy configuration from templates."
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List available templates and exit.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    init_parser = subparsers.add_parser(
        "init", help="Initialize policy configuration from a template."
    )
    init_parser.add_argument(
        "--template",
        required=True,
        choices=list(AVAILABLE_TEMPLATES.keys()),
        help="Template name to use for initialization.",
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

    list_parser = subparsers.add_parser(
        "list", help="List available templates."
    )

    return parser.parse_args(argv)


def list_templates() -> None:
    """Print available templates with descriptions."""
    print("Available templates:\n")
    for name, description in AVAILABLE_TEMPLATES.items():
        print(f"  {name}:")
        print(f"    {description}\n")


def init_policy(template_name: str, output_path: Path, force: bool) -> int:
    """Initialize policy from template."""
    template_file = TEMPLATES_DIR / f"{template_name}.json"

    if not template_file.exists():
        print(f"Error: Template file not found: {template_file}", file=sys.stderr)
        return 1

    if output_path.exists() and not force:
        print(
            f"Error: Output file already exists: {output_path}",
            file=sys.stderr,
        )
        print("Use --force to overwrite.", file=sys.stderr)
        return 1

    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy template to output path
    try:
        shutil.copy2(template_file, output_path)
        print(f"Policy initialized from template '{template_name}'")
        print(f"Output: {output_path}")

        # Validate the copied file is valid JSON
        with open(output_path, "r", encoding="utf-8") as f:
            policy_data = json.load(f)

        # Count rules for summary
        rule_count = len(policy_data.get("actions", {}))
        pattern_count = len(policy_data.get("patterns", []))
        print(f"Rules configured: {rule_count}")
        print(f"Patterns configured: {pattern_count}")

        return 0
    except json.JSONDecodeError as e:
        print(f"Error: Template file is not valid JSON: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error copying template: {e}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    """Main entry point for policy command."""
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    # Handle --list flag at top level
    if args.list:
        list_templates()
        return 0

    # Handle "list" subcommand
    if args.subcommand == "list":
        list_templates()
        return 0

    # Handle "init" subcommand
    if args.subcommand == "init":
        if args.output is None:
            # Default output path
            output_path = Path.cwd() / ".agents" / "config" / "rule_policy.json"
        else:
            output_path = Path(args.output)

        return init_policy(args.template, output_path, args.force)

    # No subcommand and no --list, show help
    list_templates()
    return 0


if __name__ == "__main__":
    sys.exit(main())