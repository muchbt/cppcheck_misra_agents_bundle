#!/usr/bin/env python3
"""MISRA Pipeline CLI - Distribution and project initialization tool.

Commands:
  init       Initialize .agents/ directory in current project
  upgrade    Upgrade installed .agents/ to latest version
  version    Show CLI and project version
  doctor     Check installation and environment
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Constants
REPO_URL = "https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
INSTALL_DIR = Path.home() / ".misra-pipeline"
CLI_DIR = INSTALL_DIR / "bin" / "cli"
VERSION_FILE = CLI_DIR / "VERSION"

# Minimum Python version
MIN_PYTHON = (3, 8)

# Version check at entry
if sys.version_info < MIN_PYTHON:
    version = ".".join(map(str, MIN_PYTHON))
    print(f"Error: Python {version} or higher is required (current: {sys.version.split()[0]}).", file=sys.stderr)
    raise SystemExit(1)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="misra-pipeline",
        description="MISRA Pipeline CLI - Distribution and project initialization tool.",
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize .agents/ in current project.")
    init_parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing .agents/")
    init_parser.add_argument("--version", "-v", default=None, help="Version to install (e.g., v1.2.3)")

    # upgrade subcommand
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade .agents/ to latest version.")
    upgrade_parser.add_argument("--version", "-v", default=None, help="Target version (e.g., v1.2.3)")

    # version subcommand
    version_parser = subparsers.add_parser("version", help="Show CLI and project version.")

    # doctor subcommand
    doctor_parser = subparsers.add_parser("doctor", help="Check installation and environment.")

    return parser.parse_args(argv if argv is not None else sys.argv[1:])


def get_current_version() -> str:
    """Get current CLI version from VERSION file."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    # Fallback: read from local cli/VERSION if running from repo
    local_version = Path(__file__).parent / "VERSION"
    if local_version.exists():
        return local_version.read_text().strip()
    return "unknown"


def read_version_file(path: Path) -> Dict[str, Any]:
    """Read .agents-version JSON file."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}


def write_version_file(path: Path, version: str, commit: str = "unknown") -> None:
    """Write .agents-version JSON file."""
    data = {
        "tag": version,
        "commit": commit,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "repo_url": REPO_URL,
    }
    path.write_text(json.dumps(data, indent=2))


def cmd_version(args: argparse.Namespace) -> int:
    """Show CLI and project version."""
    cli_version = get_current_version()
    print(f"CLI version: {cli_version}")

    target_dir = Path.cwd() / ".agents"
    version_file = target_dir / ".agents-version"
    if version_file.exists():
        version_info = read_version_file(version_file)
        project_version = version_info.get("tag", "unknown")
        print(f"Project version: {project_version}")

    return 0


def cmd_version_mock() -> str:
    """Mock version command for testing."""
    return f"CLI version: {get_current_version()}"


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.subcommand == "version":
        return cmd_version(args)
    elif args.subcommand == "init":
        return cmd_init(args)
    elif args.subcommand == "upgrade":
        return cmd_upgrade(args)
    elif args.subcommand == "doctor":
        return cmd_doctor(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())