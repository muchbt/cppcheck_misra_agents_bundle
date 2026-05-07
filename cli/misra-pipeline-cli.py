#!/usr/bin/env python3
"""MISRA Pipeline CLI - Distribution and project initialization tool.

Primary commands:
  init         Initialize .agents/ directory
  run          Run the MISRA fix pipeline (split→agent→merge)
  status       Show current pipeline run progress
  policy       Manage rule policy configuration
  doctor       Diagnose pipeline environment
  env-check    Check CLI installation

Advanced commands:
  split        Split cppcheck XML (use 'run --stage split')
  merge        Merge results (use 'run --stage merge')
  verify       Verify one chunk result
  bootstrap    Generate agent compatibility files
  validate     Provider validation test
  export       Export processed chunk results to a bundle
  collect      Import chunk results from remote workers
  config       Manage CLI configuration
  upgrade      Upgrade .agents/ to a new version
  version      Show CLI and project version

Deprecated:
  oneshot      Use 'run' instead
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ── Constants ────────────────────────────────────────────────────────────────

DEFAULT_REPO_URL = "https://github.com/muchbt/cppcheck_misra_agents_bundle"
DEFAULT_DOWNLOAD_MODE = "release"
DEFAULT_URL_TEMPLATE = (
    "{repo_url}/releases/download/{version}/agents-{version}.tar.gz"
)

INSTALL_DIR = Path.home() / ".misra-pipeline"
CLI_DIR = INSTALL_DIR / "bin" / "cli"
CONFIG_FILE = INSTALL_DIR / "config.json"
VERSION_FILE = CLI_DIR / "VERSION"

MIN_PYTHON = (3, 8)

# Pipeline command mapping: subcommand -> module_name in .agents/tools/
# Note: 'run' and 'oneshot' are handled separately (cmd_run / deprecated alias)
PIPELINE_COMMANDS: Dict[str, str] = {
    "split": "split_cppcheck_xml",
    "merge": "merge_results",
    "verify": "verify_chunk",
    "bootstrap": "bootstrap_agents",
    "doctor": "doctor",
    "validate": "validate_real",
    "export": "export_chunks",
    "collect": "collect_chunks",
}

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

# Version check at entry
if sys.version_info < MIN_PYTHON:
    version = ".".join(map(str, MIN_PYTHON))
    print(
        f"Error: Python {version} or higher is required (current: {sys.version.split()[0]}).",
        file=sys.stderr,
    )
    raise SystemExit(1)


# ── Configuration ────────────────────────────────────────────────────────────

class UserConfig:
    """User-level configuration for download sources."""

    def __init__(self, data: Optional[Dict[str, Any]] = None) -> None:
        data = data or {}
        download = data.get("download", {})
        self.download_mode: str = download.get("mode", DEFAULT_DOWNLOAD_MODE)
        self.url_template: str = download.get("url_template", DEFAULT_URL_TEMPLATE)
        self.fallback_mode: str = download.get("fallback_mode", "git_clone")
        self.repo_url: str = data.get("repo_url", DEFAULT_REPO_URL)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo_url": self.repo_url,
            "download": {
                "mode": self.download_mode,
                "url_template": self.url_template,
                "fallback_mode": self.fallback_mode,
            },
        }

    def resolve_url(self, version: str) -> str:
        """Resolve URL template with version variable."""
        return self.url_template.format(version=version, repo_url=self.repo_url)


def load_user_config() -> UserConfig:
    """Load user configuration from ~/.misra-pipeline/config.json."""
    if CONFIG_FILE.exists():
        try:
            data = json.loads(CONFIG_FILE.read_text())
            return UserConfig(data)
        except (json.JSONDecodeError, OSError):
            pass
    return UserConfig()


def save_user_config(config: UserConfig) -> None:
    """Save user configuration to ~/.misra-pipeline/config.json."""
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config.to_dict(), indent=2))


# ── Argument parsing ─────────────────────────────────────────────────────────

def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="misra-pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="""MISRA Pipeline CLI - Distribution and project initialization tool.

Primary commands:
  init          Initialize .agents/ in current project.
  run           Run the MISRA fix pipeline (split -> agent -> merge).
  status        Show current pipeline run progress.
  policy        Manage rule policy configuration.
  doctor        Diagnose pipeline environment.
  env-check     Check CLI installation and environment.

Advanced commands:
  split         Split cppcheck XML into runtime chunks.
  merge         Merge runtime results into reports.
  verify        Verify one chunk result.
  bootstrap     Generate agent compatibility files.
  validate      Provider validation test.
  config        Manage CLI configuration.
  upgrade       Upgrade .agents/ to latest version.
  version       Show CLI and project version.

Deprecated:
  oneshot       Use 'run' instead.
        """,
    )
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # init subcommand
    init_parser = subparsers.add_parser("init", help="Initialize .agents/ in current project.")
    init_parser.add_argument("--force", "-f", action="store_true", help="Force overwrite existing .agents/")
    init_parser.add_argument("--version", "-v", default=None, help="Version to install (e.g., v1.2.3)")
    init_parser.add_argument(
        "--source",
        "-s",
        choices=["release", "git_archive", "git_clone", "direct", "local"],
        default=None,
        help="Download source mode (overrides config)",
    )
    init_parser.add_argument("--url", "-u", default=None, help="Override download URL or local path")

    # upgrade subcommand
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade .agents/ to latest version. (advanced)")
    upgrade_parser.add_argument("--version", "-v", default=None, help="Target version (e.g., v1.2.3)")
    upgrade_parser.add_argument(
        "--source",
        "-s",
        choices=["release", "git_archive", "git_clone", "direct", "local"],
        default=None,
        help="Download source mode (overrides config)",
    )
    upgrade_parser.add_argument("--url", "-u", default=None, help="Override download URL or local path")

    # version subcommand
    subparsers.add_parser("version", help="Show CLI and project version. (advanced)")

    # env-check subcommand
    subparsers.add_parser("env-check", help="Check CLI installation and environment.")

    # config subcommand
    config_parser = subparsers.add_parser("config", help="Manage CLI configuration. (advanced)")
    config_subparsers = config_parser.add_subparsers(dest="config_action", required=True)
    config_show = config_subparsers.add_parser("show", help="Show current configuration.")
    config_set = config_subparsers.add_parser("set", help="Set configuration value.")
    config_set.add_argument("key", choices=["mode", "url_template", "repo_url", "fallback_mode"], help="Config key to set")
    config_set.add_argument("value", help="Value to set")
    config_reset = config_subparsers.add_parser("reset", help="Reset configuration to defaults.")
    config_reset.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")

    # Pipeline commands (forward to .agents/tools/ modules)
    for cmd_name, module_name in PIPELINE_COMMANDS.items():
        cmd_help = {
            "split": "Split cppcheck XML into runtime chunks (advanced)",
            "merge": "Merge runtime results into reports (advanced)",
            "verify": "Verify one chunk result (advanced)",
            "bootstrap": "Generate agent compatibility files (advanced)",
            "doctor": "Run pipeline diagnostics",
            "validate": "Provider validation test (advanced)",
            "export": "Export processed chunk results to a bundle",
            "collect": "Import chunk results from remote workers",
        }.get(cmd_name, f"Run {module_name}")
        cmd_parser = subparsers.add_parser(cmd_name, help=cmd_help)
        cmd_parser.add_argument(
            "--provider", "-P",
            choices=["codex", "claude", "opencode", "kimi"],
            default=None,
            help="Override agent provider (sets PIPELINE_AGENT_PROVIDER env var)",
        )

    # policy subcommand (forward remaining args to policy_init)
    policy_parser = subparsers.add_parser(
        "policy",
        help="Manage policy configuration",
    )
    policy_parser.add_argument(
        "--provider", "-P",
        choices=["codex", "claude", "opencode", "kimi"],
        default=None,
        help="Override agent provider (sets PIPELINE_AGENT_PROVIDER env var)",
    )

    # run subcommand (absorbs oneshot functionality)
    run_parser = subparsers.add_parser("run", help="Run the MISRA fix pipeline (split→agent→merge)")
    run_parser.add_argument("--fresh", action="store_true", help="Force fresh start, ignore existing progress")
    run_parser.add_argument("--resume", action="store_true", help="Explicit resume mode")
    run_parser.add_argument("--dry-run", action="store_true", help="Preview mode: show chunk summary without starting agents")
    run_parser.add_argument("--status", action="store_true", help="Show current run progress and exit")
    run_parser.add_argument("--stage", choices=["split", "agent", "merge"], default=None, help="Run a single stage only")
    run_parser.add_argument("--strategy", choices=["conservative", "all_auto"], default=None, help="Fix strategy")
    run_parser.add_argument("--max-chunks", type=int, default=None, help="Maximum number of chunks")
    run_parser.add_argument("--retry-failed", type=int, default=None, help="Retry failed chunks N times")
    run_parser.add_argument("--rule-id", action="append", default=[], help="Rule ID filter (can be repeated)")
    run_parser.add_argument("--misra-only", action="store_true", help="Only process MISRA rules")
    run_parser.add_argument("--include-failed", action="store_true", help="Include previously failed chunks")
    run_parser.add_argument("--chunk-id", action="append", default=[],
                            help="Run only this chunk id or range (e.g. 5 or 3-7). Repeatable.")
    run_parser.add_argument("--run-id", default=None, help="Specify run ID (format: YYYYMMDD-XXX)")
    run_parser.add_argument("--verbose", action="store_true", help="Print full stdout/stderr for each chunk")
    run_parser.add_argument(
        "--provider", "-P",
        choices=["codex", "claude", "opencode", "kimi"],
        default=None,
        help="Override agent provider",
    )

    # status subcommand
    subparsers.add_parser("status", help="Show current pipeline run progress")

    # oneshot deprecated alias
    subparsers.add_parser("oneshot", help="(deprecated) Use 'run' instead")

    # Use parse_known_args so --flags like --dry-run pass through to subcommands
    parsed, forwarded = parser.parse_known_args(argv if argv is not None else sys.argv[1:])
    # Attach forwarded args to the namespace
    if parsed.subcommand in PIPELINE_COMMANDS:
        parsed.args = forwarded
    elif parsed.subcommand == "policy":
        parsed.policy_args = forwarded

    return parsed


# ── Version helpers ──────────────────────────────────────────────────────────

def get_current_version() -> str:
    """Get current CLI version from VERSION file."""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
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


def write_version_file(path: Path, version: str, commit: str = "unknown", repo_url: str = DEFAULT_REPO_URL) -> None:
    """Write .agents-version JSON file."""
    data = {
        "tag": version,
        "commit": commit,
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "repo_url": repo_url,
    }
    path.write_text(json.dumps(data, indent=2))


# ── Environment checks ───────────────────────────────────────────────────────

def check_python_version() -> bool:
    """Check Python version >= 3.8."""
    return sys.version_info >= MIN_PYTHON


def check_cli_installed() -> bool:
    """Check CLI is installed in ~/.misra-pipeline."""
    return CLI_DIR.exists() and (CLI_DIR / "misra-pipeline-cli.py").exists()


def check_git_available() -> bool:
    """Check git command is available."""
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def check_project_initialized() -> bool:
    """Check .agents/ exists in current directory."""
    return (Path.cwd() / ".agents").exists()


def check_project_initialized_mock(cwd: Path) -> bool:
    """Mock check for project initialization (for testing)."""
    return (cwd / ".agents").exists()


# ── Download backends ────────────────────────────────────────────────────────

def _download_http(url: str, dest: Path) -> bool:
    """Download file from HTTP(S) URL to destination."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "misra-pipeline-cli/1.0"},
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            dest.write_bytes(response.read())
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP error {e.code}: {e.reason}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"URL error: {e.reason}", file=sys.stderr)
        return False
    except OSError as e:
        print(f"Download failed: {e}", file=sys.stderr)
        return False


def _extract_archive(archive_path: Path, target: Path, strip_components: int = 0) -> bool:
    """Extract tar.gz archive to target directory."""
    try:
        # Try tar command first (handles strip-components)
        target.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["tar", "-xzf", str(archive_path), "-C", str(target), "--strip-components", str(strip_components)],
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        # Fallback: Python tarfile
        import tarfile
        with tarfile.open(archive_path, "r:gz") as tar:
            tar.extractall(target)
        return True
    except Exception as e:
        print(f"Extraction failed: {e}", file=sys.stderr)
        return False


def download_from_release(url: str, target: Path, source_path: str = ".agents") -> bool:
    """Download from a release archive URL.

    Args:
        url: Full URL to the tar.gz archive
        target: Target directory to extract files to
        source_path: Expected subdirectory in archive (e.g., ".agents")

    Returns:
        True if successful, False otherwise
    """
    with tempfile.TemporaryDirectory() as tmp:
        archive_path = Path(tmp) / "download.tar.gz"
        print(f"Downloading from release: {url}")
        if not _download_http(url, archive_path):
            return False

        print("Extracting archive...")
        extract_dir = Path(tmp) / "extracted"
        if not _extract_archive(archive_path, extract_dir):
            return False

        # Find the source directory in extracted contents
        # The archive might contain a top-level folder like "agents-v1.0.0/"
        found_source = None
        for item in extract_dir.iterdir():
            if item.is_dir():
                candidate = item / source_path
                if candidate.exists():
                    found_source = candidate
                    break
                # Also check if the dir itself is the source
                if item.name == source_path.lstrip("./"):
                    found_source = item
                    break

        if found_source is None:
            # Try direct extraction (no nested folder)
            found_source = extract_dir / source_path
            if not found_source.exists():
                print(f"Error: Could not find '{source_path}' in archive", file=sys.stderr)
                return False

        # Copy to target
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(found_source, target)
        return True


def download_from_git(target: Path, version: str, source_path: str = ".agents", repo_url: str = DEFAULT_REPO_URL) -> bool:
    """Download files from Git repository using shallow clone.

    Args:
        target: Target directory to extract files to
        version: Git tag or branch name
        source_path: Path in repo to extract (e.g., ".agents" or "cli")
        repo_url: Git repository URL

    Returns:
        True if successful, False otherwise
    """
    import tempfile as tempfile_mod
    try:
        tmpdir = tempfile_mod.mkdtemp(prefix="misra_clone_")
        clone_cmd = [
            "git", "clone", "--depth=1",
            "--branch", version,
            "--single-branch",
            repo_url, tmpdir,
        ]
        result = subprocess.run(clone_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            stderr = result.stderr.strip() if result.stderr else "unknown error"
            print(f"Error cloning repository: {stderr}", file=sys.stderr)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return False

        source_dir = Path(tmpdir) / source_path
        if not source_dir.exists():
            print(f"Error: '{source_path}' not found in repository", file=sys.stderr)
            shutil.rmtree(tmpdir, ignore_errors=True)
            return False

        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source_dir, target)
        shutil.rmtree(tmpdir, ignore_errors=True)
        return True
    except Exception as e:
        print(f"Error downloading from Git: {e}", file=sys.stderr)
        return False


def download_from_direct(url: str, target: Path, source_path: str = ".agents") -> bool:
    """Download from a direct URL (same as release, just different intent)."""
    return download_from_release(url, target, source_path)


def download_from_local(path: str, target: Path, source_path: str = ".agents") -> bool:
    """Copy from a local path (file or directory).

    Args:
        path: Local path to tar.gz archive or directory
        target: Target directory
        source_path: Expected subdirectory if archive

    Returns:
        True if successful, False otherwise
    """
    local_path = Path(path).expanduser().resolve()
    if not local_path.exists():
        print(f"Local path not found: {local_path}", file=sys.stderr)
        return False

    if local_path.is_dir():
        # Copy directory directly
        source = local_path / source_path
        if not source.exists():
            source = local_path
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        return True

    if local_path.suffix in (".gz", ".tgz", ".tar.gz"):
        # Extract archive
        with tempfile.TemporaryDirectory() as tmp:
            extract_dir = Path(tmp) / "extracted"
            if not _extract_archive(local_path, extract_dir):
                return False
            found_source = None
            for item in extract_dir.iterdir():
                if item.is_dir():
                    candidate = item / source_path
                    if candidate.exists():
                        found_source = candidate
                        break
                    if item.name == source_path.lstrip("./"):
                        found_source = item
                        break
            if found_source is None:
                found_source = extract_dir / source_path
                if not found_source.exists():
                    print(f"Error: Could not find '{source_path}' in local archive", file=sys.stderr)
                    return False
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(found_source, target)
            return True

    print(f"Unsupported local file type: {local_path.suffix}", file=sys.stderr)
    return False


def download_agents(
    target: Path,
    version: str,
    source_path: str = ".agents",
    mode: Optional[str] = None,
    url: Optional[str] = None,
    config: Optional[UserConfig] = None,
) -> bool:
    """Download agents using configured or specified source.

    Priority:
    1. Explicit --url (uses mode to determine handler)
    2. Explicit --source with config URL template
    3. Configured download mode
    4. Fallback mode

    Args:
        target: Target directory
        version: Version to download
        source_path: Path within archive/repo
        mode: Override download mode
        url: Override URL/path
        config: User configuration

    Returns:
        True if successful
    """
    cfg = config or load_user_config()
    effective_mode = mode or cfg.download_mode
    effective_url = url

    if effective_url is None:
        if effective_mode in ("release", "direct"):
            effective_url = cfg.resolve_url(version)
        elif effective_mode == "git_archive":
            effective_url = None  # Uses repo_url instead
        elif effective_mode == "local":
            effective_url = cfg.resolve_url(version)

    # Try primary mode
    primary_failed_reason = None
    if effective_mode == "release" and effective_url:
        if download_from_release(effective_url, target, source_path):
            return True
        primary_failed_reason = f"Release download from {effective_url} failed."
    elif effective_mode == "direct" and effective_url:
        if download_from_direct(effective_url, target, source_path):
            return True
        primary_failed_reason = f"Direct download from {effective_url} failed."
    elif effective_mode == "local" and effective_url:
        if download_from_local(effective_url, target, source_path):
            return True
        primary_failed_reason = f"Local path {effective_url} not found or invalid."
    elif effective_mode in ("git_archive", "git_clone"):
        if download_from_git(target, version, source_path, cfg.repo_url):
            return True
        primary_failed_reason = f"Git clone from {cfg.repo_url} (branch {version}) failed."

    # Fallback
    fallback = cfg.fallback_mode
    fallback_failed_reason = None
    if fallback != effective_mode:
        print(f"Primary mode '{effective_mode}' failed, trying fallback '{fallback}'...", file=sys.stderr)
        if fallback in ("git_archive", "git_clone"):
            if download_from_git(target, version, source_path, cfg.repo_url):
                return True
            fallback_failed_reason = f"Git clone from {cfg.repo_url} (branch {version}) failed."
        elif fallback in ("release", "direct"):
            fallback_url = cfg.resolve_url(version)
            if download_from_release(fallback_url, target, source_path):
                return True
            fallback_failed_reason = f"Release download from {fallback_url} failed."
        elif fallback == "local":
            fallback_url = cfg.resolve_url(version)
            if download_from_local(fallback_url, target, source_path):
                return True
            fallback_failed_reason = f"Local path {fallback_url} not found or invalid."

    print(f"All download methods failed:", file=sys.stderr)
    if primary_failed_reason:
        print(f"  - {primary_failed_reason}", file=sys.stderr)
    if fallback_failed_reason:
        print(f"  - {fallback_failed_reason}", file=sys.stderr)
    print("Suggestions:", file=sys.stderr)
    print("  1. Check your network connection and proxy settings.", file=sys.stderr)
    print(f"  2. Try: misra-pipeline upgrade --source git_clone -v {version}", file=sys.stderr)
    print(f"  3. Try: misra-pipeline upgrade --source local --url /path/to/agents-v{version}.tar.gz", file=sys.stderr)
    return False


def get_git_commit_for_version(version: str, repo_url: str = DEFAULT_REPO_URL) -> str:
    """Get commit hash for a Git tag."""
    try:
        cmd = ["git", "ls-remote", repo_url, f"refs/tags/{version}"]
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        if result.stdout:
            return result.stdout.split()[0]
        cmd = ["git", "ls-remote", repo_url, f"refs/heads/{version}"]
        result = subprocess.run(cmd, capture_output=True, check=True, text=True)
        return result.stdout.split()[0] if result.stdout else "unknown"
    except subprocess.CalledProcessError:
        return "unknown"


# ── Command implementations ──────────────────────────────────────────────────

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


def cmd_config(args: argparse.Namespace) -> int:
    """Manage CLI configuration."""
    config = load_user_config()

    if args.config_action == "show":
        print(json.dumps(config.to_dict(), indent=2))
        return 0

    if args.config_action == "reset":
        if not args.yes:
            confirm = input("Reset configuration to defaults? [y/N]: ")
            if confirm.lower() not in ("y", "yes"):
                print("Aborted.")
                return 1
        save_user_config(UserConfig())
        print("Configuration reset to defaults.")
        return 0

    if args.config_action == "set":
        if args.key == "mode":
            config.download_mode = args.value
        elif args.key == "url_template":
            config.url_template = args.value
        elif args.key == "repo_url":
            config.repo_url = args.value
            # Also update default url_template if it still uses the old repo
            if DEFAULT_REPO_URL in config.url_template and args.value != DEFAULT_REPO_URL:
                config.url_template = config.url_template.replace(DEFAULT_REPO_URL, args.value)
        elif args.key == "fallback_mode":
            config.fallback_mode = args.value
        save_user_config(config)
        print(f"Set {args.key} = {args.value}")
        return 0

    return 1


# ── Init command ─────────────────────────────────────────────────────────────

AGENTS_SUBDIRS_TO_CREATE = [
    "runtime",
    "runtime/chunks",
    "runtime/results",
    "reports",
    "runs",
    "staging",
]

AGENTS_DIRS_TO_COPY = [
    "tools",
    "config",
    "config/templates",
    "prompts",
    "skills",
    "compat",
]


def cmd_init_mock(args: argparse.Namespace, cwd: Path) -> int:
    """Mock init command for testing (without actual download)."""
    target_dir = cwd / ".agents"

    if target_dir.exists() and not args.force:
        print(f"Error: {target_dir} already exists.", file=sys.stderr)
        return 1

    target_dir.mkdir(parents=True, exist_ok=True)

    for subdir in AGENTS_SUBDIRS_TO_CREATE:
        (target_dir / subdir).mkdir(parents=True, exist_ok=True)

    version = args.version or get_current_version()
    write_version_file(target_dir / ".agents-version", version, "test-commit")

    return 0


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize .agents/ directory in current project."""
    target_dir = Path.cwd() / ".agents"

    if target_dir.exists():
        if not args.force:
            print(f"Error: {target_dir} already exists.", file=sys.stderr)
            print("Please backup and remove it, or use --force to overwrite.", file=sys.stderr)
            return 1
        shutil.rmtree(target_dir)

    version = args.version or get_current_version()
    print(f"Initializing .agents/ from version: {version}")

    config = load_user_config()
    if not download_agents(
        target_dir,
        version,
        ".agents",
        mode=args.source,
        url=args.url,
        config=config,
    ):
        print("Error: Failed to download .agents/", file=sys.stderr)
        return 1

    for subdir in AGENTS_SUBDIRS_TO_CREATE:
        (target_dir / subdir).mkdir(parents=True, exist_ok=True)

    commit = get_git_commit_for_version(version, config.repo_url)
    write_version_file(target_dir / ".agents-version", version, commit, config.repo_url)

    print(f"Initialized: {target_dir}")
    print(f"Version: {version}")
    print("Next: configure .agents/config/pipeline.json and run policy init")

    return 0


# ── Upgrade command ──────────────────────────────────────────────────────────

UPGRADE_PRESERVE_FILES = {
    "config/pipeline.json",
    "config/rule_policy.json",
}

UPGRADE_CHECK_DIRS = ["tools", "config/templates"]


def compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def has_local_modifications(target_dir: Path) -> bool:
    """Check if files in tools/ or templates/ have been modified."""
    version_file = target_dir / ".agents-version"
    if not version_file.exists():
        return True
    return False


def cmd_upgrade_mock(args: argparse.Namespace, cwd: Path) -> int:
    """Mock upgrade command that always detects modifications."""
    target_dir = cwd / ".agents"
    if not target_dir.exists():
        print("Error: .agents/ not found. Run 'misra-pipeline init' first.", file=sys.stderr)
        return 1
    return 1


def cmd_upgrade_mock_clean(args: argparse.Namespace, cwd: Path) -> int:
    """Mock upgrade command for clean upgrade test."""
    target_dir = cwd / ".agents"
    version_file = target_dir / ".agents-version"

    if not target_dir.exists():
        return 1

    new_version = args.version or "v1.1.0"
    new_commit = "new-commit"
    write_version_file(version_file, new_version, new_commit)

    return 0


def cmd_upgrade(args: argparse.Namespace) -> int:
    """Upgrade installed .agents/ to latest version."""
    target_dir = Path.cwd() / ".agents"
    version_file = target_dir / ".agents-version"

    if not target_dir.exists():
        print("Error: .agents/ not found. Run 'misra-pipeline init' first.", file=sys.stderr)
        return 1

    if has_local_modifications(target_dir):
        print("Error: Local modifications detected in .agents/", file=sys.stderr)
        print("Please backup and resolve conflicts manually.", file=sys.stderr)
        return 1

    current_info = read_version_file(version_file)
    current = current_info.get("tag", "unknown")
    target_version = args.version or get_current_version()

    if current == target_version:
        print(f"Already at version: {current}")
        return 0

    print(f"Upgrading from {current} to {target_version}")

    config = load_user_config()
    with tempfile.TemporaryDirectory() as tmp:
        temp_agents = Path(tmp) / ".agents"
        if not download_agents(
            temp_agents,
            target_version,
            ".agents",
            mode=args.source,
            url=args.url,
            config=config,
        ):
            return 1

        for item in temp_agents.iterdir():
            rel_path = item.relative_to(temp_agents)
            target_item = target_dir / rel_path

            if str(rel_path) in UPGRADE_PRESERVE_FILES and target_item.exists():
                print(f"  Preserving: {rel_path}")
                continue

            if target_item.exists():
                if target_item.is_dir():
                    shutil.rmtree(target_item)
                else:
                    target_item.unlink()

            if item.is_dir():
                shutil.copytree(item, target_item)
            else:
                shutil.copy2(item, target_item)

    commit = get_git_commit_for_version(target_version, config.repo_url)
    write_version_file(version_file, target_version, commit, config.repo_url)

    print(f"Upgraded to: {target_version}")
    return 0


# ── Env-check command ────────────────────────────────────────────────────────

def cmd_env_check(args: argparse.Namespace) -> int:
    """Check CLI installation and environment."""
    checks = [
        ("Python version (>=3.8)", check_python_version()),
        ("CLI installed", check_cli_installed()),
        ("Git available", check_git_available()),
        ("Project initialized", check_project_initialized()),
    ]
    all_pass = True
    for name, result in checks:
        status = "OK" if result else "FAIL"
        print(f"  {name}: {status}")
        if not result:
            all_pass = False

    if all_pass:
        print("\nAll checks passed.")
        return 0
    else:
        print("\nSome checks failed. Fix issues before proceeding.")
        return 1


# ── Pipeline command dispatch ────────────────────────────────────────────────

def _call_module_main(module, args: list[str]) -> int:
    """Call module.main() with or without argv depending on its signature.

    merge_results, bootstrap_agents, verify_chunk have main() with no args.
    All other modules have main(argv=None).
    """
    sig = inspect.signature(module.main)
    if len(sig.parameters) > 0:
        result = module.main(args)
    else:
        result = module.main()
    return result if isinstance(result, int) else 0


def _dispatch_pipeline_command(command: str, args: list[str], provider: Optional[str] = None) -> int:
    """Dispatch a pipeline command to its implementation module in .agents/tools/."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(
            f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.",
            file=sys.stderr,
        )
        return 1

    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)

    module_name = PIPELINE_COMMANDS[command]
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        print(
            f"Error: Failed to import module '{module_name}': {exc}",
            file=sys.stderr,
        )
        print("Check that .agents/ is properly installed.", file=sys.stderr)
        return 1

    # Set PIPELINE_AGENT_PROVIDER env var if --provider is specified
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
    try:
        if provider:
            os.environ["PIPELINE_AGENT_PROVIDER"] = provider
        elif original_provider is not None:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

        original_argv = sys.argv
        try:
            sys.argv = [f"{module_name}.py", *args]
            return _call_module_main(module, args)
        except Exception as exc:
            print(f"Error running {command}: {exc}", file=sys.stderr)
            return 1
        finally:
            sys.argv = original_argv
    finally:
        # Restore original PIPELINE_AGENT_PROVIDER state
        if original_provider is not None:
            os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
        else:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)


def _dispatch_policy_command(policy_args: list[str]) -> int:
    """Dispatch policy command to policy_init module using REMAINDER forwarding."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(
            f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.",
            file=sys.stderr,
        )
        return 1

    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)

    try:
        policy_init = importlib.import_module("policy_init")
    except ImportError as exc:
        print(
            f"Error: Failed to import policy_init: {exc}",
            file=sys.stderr,
        )
        return 1

    original_argv = sys.argv
    try:
        sys.argv = ["policy_init.py", *policy_args]
        return _call_module_main(policy_init, policy_args)
    except Exception as exc:
        print(f"Error running policy: {exc}", file=sys.stderr)
        return 1
    finally:
        sys.argv = original_argv


# ── Run & Status commands ─────────────────────────────────────────────────────

def _import_oneshot_helpers():
    """Import oneshot module for helper functions."""
    tools_dir = Path.cwd() / ".agents" / "tools"
    if not tools_dir.exists():
        print(
            f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.",
            file=sys.stderr,
        )
        raise SystemExit(1)
    tools_dir_str = str(tools_dir.resolve())
    if tools_dir_str not in sys.path:
        sys.path.insert(0, tools_dir_str)
    return importlib.import_module("oneshot")


def cmd_run(args: argparse.Namespace) -> int:
    """Run the MISRA fix pipeline (split→agent→merge or single stage)."""
    # --fresh and --resume are mutually exclusive (no import needed)
    if args.fresh and args.resume:
        print("[run] --fresh and --resume cannot be used together.", file=sys.stderr)
        return 2

    # Single-stage mode: dispatch to a specific module (no oneshot import needed)
    if args.stage:
        stage_module_map = {
            "split": "split_cppcheck_xml",
            "agent": "run_fix_pipeline",
            "merge": "merge_results",
        }
        module_name = stage_module_map[args.stage]
        stage_args = []
        if args.stage == "split":
            if args.strategy:
                stage_args.extend(["--strategy", args.strategy])
            if args.run_id:
                stage_args.extend(["--run-id", args.run_id])
        elif args.stage == "agent":
            if args.strategy:
                stage_args.extend(["--strategy", args.strategy])
            if args.max_chunks is not None:
                stage_args.extend(["--max-chunks", str(args.max_chunks)])
            if args.retry_failed is not None:
                stage_args.extend(["--retry-failed", str(args.retry_failed)])
            for rule_id in args.rule_id:
                stage_args.extend(["--rule-id", rule_id])
            if args.misra_only:
                stage_args.append("--misra-only")
            if args.include_failed:
                stage_args.append("--include-failed")
            for cid in args.chunk_id:
                stage_args.extend(["--chunk-id", cid])
            if args.verbose:
                stage_args.append("--verbose")

        # Import and call the module
        tools_dir = Path.cwd() / ".agents" / "tools"
        if not tools_dir.exists():
            print(
                f"Error: {tools_dir} not found. Run 'misra-pipeline init' first.",
                file=sys.stderr,
            )
            return 1
        tools_dir_str = str(tools_dir.resolve())
        if tools_dir_str not in sys.path:
            sys.path.insert(0, tools_dir_str)
        try:
            module = importlib.import_module(module_name)
        except ImportError as exc:
            print(f"Error: Failed to import module '{module_name}': {exc}", file=sys.stderr)
            return 1

        # Set provider env var
        provider = getattr(args, "provider", None)
        original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
        try:
            if provider:
                os.environ["PIPELINE_AGENT_PROVIDER"] = provider
            elif original_provider is not None:
                os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

            original_argv = sys.argv
            try:
                sys.argv = [f"{module_name}.py", *stage_args]
                return _call_module_main(module, stage_args)
            except Exception as exc:
                print(f"Error running {args.stage}: {exc}", file=sys.stderr)
                return 1
            finally:
                sys.argv = original_argv
        finally:
            if original_provider is not None:
                os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
            else:
                os.environ.pop("PIPELINE_AGENT_PROVIDER", None)

    # Full-flow mode: import oneshot (only needed here and for --status)
    oneshot = _import_oneshot_helpers()

    # --status: print progress and exit
    if args.status:
        return oneshot.print_status_summary()

    # Build oneshot argv from CLI args
    oneshot_argv = []
    if args.fresh:
        oneshot_argv.append("--fresh")
    if args.resume:
        oneshot_argv.append("--resume")
    if args.strategy:
        oneshot_argv.extend(["--strategy", args.strategy])
    if args.run_id:
        oneshot_argv.extend(["--run-id", args.run_id])
    if args.max_chunks is not None:
        oneshot_argv.extend(["--max-chunks", str(args.max_chunks)])
    if args.retry_failed is not None:
        oneshot_argv.extend(["--retry-failed", str(args.retry_failed)])
    for rule_id in args.rule_id:
        oneshot_argv.extend(["--rule-id", rule_id])
    if args.misra_only:
        oneshot_argv.append("--misra-only")
    if args.include_failed:
        oneshot_argv.append("--include-failed")
    for cid in args.chunk_id:
        oneshot_argv.extend(["--chunk-id", cid])
    if args.dry_run:
        oneshot_argv.append("--dry-run")
    if getattr(args, "verbose", False):
        oneshot_argv.append("--verbose")

    provider = getattr(args, "provider", None)
    original_provider = os.environ.get("PIPELINE_AGENT_PROVIDER")
    try:
        if provider:
            os.environ["PIPELINE_AGENT_PROVIDER"] = provider
        elif original_provider is not None:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)
        return oneshot.main(oneshot_argv)
    finally:
        if original_provider is not None:
            os.environ["PIPELINE_AGENT_PROVIDER"] = original_provider
        else:
            os.environ.pop("PIPELINE_AGENT_PROVIDER", None)


def cmd_status(args: argparse.Namespace) -> int:
    """Show current pipeline run progress."""
    oneshot = _import_oneshot_helpers()
    return oneshot.print_status_summary()


def main(argv: Optional[list[str]] = None) -> int:
    """Main entry point."""
    args = parse_args(argv)

    if args.subcommand == "version":
        return cmd_version(args)
    elif args.subcommand == "init":
        return cmd_init(args)
    elif args.subcommand == "upgrade":
        return cmd_upgrade(args)
    elif args.subcommand == "env-check":
        return cmd_env_check(args)
    elif args.subcommand == "run":
        return cmd_run(args)
    elif args.subcommand == "status":
        return cmd_status(args)
    elif args.subcommand == "config":
        return cmd_config(args)
    elif args.subcommand == "oneshot":
        print("'oneshot' has been merged into 'run'. Use 'misra-pipeline run' instead.", file=sys.stderr)
        return 1
    elif args.subcommand in PIPELINE_COMMANDS:
        provider = getattr(args, "provider", None)
        return _dispatch_pipeline_command(args.subcommand, args.args, provider=provider)
    elif args.subcommand == "policy":
        return _dispatch_policy_command(args.policy_args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
