from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import doctor
from common import ROOT_OVERRIDE_ENV, load_json, next_run_id, now_iso, save_json


SCRIPT_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_CLI_PATH = Path(__file__).resolve().with_name("pipeline_cli.py")
PROVIDERS = ("codex", "claude", "opencode")
OPENCODE_CREDENTIALS_RE = re.compile(r"\b([1-9]\d*) credentials\b", re.IGNORECASE)
AUTH_PROBE_TIMEOUT_SECONDS = 10
CLI_STAGE_TIMEOUT_SECONDS = 120
DEFAULT_REPORT_PATH = Path(tempfile.gettempdir()) / "cppcheck_misra_real_validation.json"
RUN_STAGE_TIMEOUT_RETRIES = 1
CODEX_WORKSPACE_BASE = Path.home() / ".cache" / "cppcheck_misra_validation" / "codex"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="真实执行 1 issue / 1 chunk provider 验收。")
    parser.add_argument(
        "--provider",
        choices=(*PROVIDERS, "all"),
        default="all",
        help="要验证的 provider，默认 all。",
    )
    parser.add_argument(
        "--report",
        default=str(DEFAULT_REPORT_PATH),
        help="结果报告输出路径。",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="保留临时样例工作区，便于排查。",
    )
    parser.add_argument(
        "--run-id",
        default="",
        help="可选的固定 run id，格式应与 split 命令一致。",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def determine_provider_status(
    provider: str,
    checks: List[Dict[str, Any]],
    auth_ok: bool,
    auth_detail: str,
) -> Tuple[str, str]:
    del provider
    codes = {str(item.get("code", "")) for item in checks}
    missing_codes = {"agent_launch_executable_missing", "opencode_executable_missing"}
    if codes & missing_codes:
        return "skipped_not_installed", "未安装对应 provider CLI，跳过真实验收。"

    if not auth_ok:
        return "skipped_auth_missing", auth_detail or "未检测到有效认证，跳过真实验收。"

    blocking_errors = [
        item
        for item in checks
        if item.get("level") == "error" and item.get("code") not in missing_codes and item.get("code") != "agent_auth_missing"
    ]
    if blocking_errors:
        first = blocking_errors[0]
        detail = str(first.get("detail", "")).strip()
        message = str(first.get("message", "")).strip()
        reason = message or "前置检查未通过。"
        if detail:
            reason = f"{reason} {detail}"
        return "skipped_precheck_blocked", reason

    return "ready", auth_detail or "前置检查与认证探测通过。"


def target_providers(selected: str) -> List[str]:
    return list(PROVIDERS) if selected == "all" else [selected]


def _copy_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def _build_workspace_config(provider: str) -> Dict[str, Any]:
    config = load_json(SCRIPT_ROOT / ".agents" / "config" / "pipeline.json", {})
    config["agent"]["provider"] = provider
    config["input"]["cppcheck_xml"] = "cppcheck.xml"
    return config


def prepare_workspace(workspace_root: Path, provider: str) -> None:
    _copy_file(SCRIPT_ROOT / "AGENTS.md", workspace_root / "AGENTS.md")
    _copy_file(SCRIPT_ROOT / ".agents" / "config" / "agent_map.json", workspace_root / ".agents" / "config" / "agent_map.json")
    _copy_file(SCRIPT_ROOT / ".agents" / "config" / "rule_policy.json", workspace_root / ".agents" / "config" / "rule_policy.json")
    _copy_file(SCRIPT_ROOT / ".agents" / "prompts" / "fix_chunk_prompt.txt", workspace_root / ".agents" / "prompts" / "fix_chunk_prompt.txt")
    _copy_file(
        SCRIPT_ROOT / ".agents" / "skills" / "cppcheck-misra-fix" / "SKILL.md",
        workspace_root / ".agents" / "skills" / "cppcheck-misra-fix" / "SKILL.md",
    )
    save_json(workspace_root / ".agents" / "config" / "pipeline.json", _build_workspace_config(provider))
    (workspace_root / "src").mkdir(parents=True, exist_ok=True)
    (workspace_root / "src" / "a.c").write_text(
        "int f(void) {\n    int unused = 0;\n    return 0;\n}\n",
        encoding="utf-8",
    )
    (workspace_root / "cppcheck.xml").write_text(
        (
            "<results><errors>"
            "<error id=\"unusedVariable\" severity=\"style\" msg=\"Unused variable: unused\">"
            "<location file=\"src/a.c\" line=\"2\"/>"
            "</error>"
            "</errors></results>"
        ),
        encoding="utf-8",
    )


def build_pipeline_env(workspace_root: Path) -> Dict[str, str]:
    env = dict(os.environ)
    env[ROOT_OVERRIDE_ENV] = str(workspace_root)
    return env


def run_subprocess(
    cmd: Sequence[str],
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: Optional[int] = None,
) -> subprocess.CompletedProcess:
    proc = subprocess.Popen(
        list(cmd),
        cwd=str(cwd) if cwd is not None else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        # On Unix: start_new_session creates a new process group for clean termination
        # On Windows: this parameter is ignored; use CREATE_NEW_PROCESS_GROUP instead
        start_new_session=True if platform.system() != "Windows" else False,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        # Kill process group on Unix, single process on Windows
        if platform.system() == "Windows":
            proc.kill()
        else:
            try:
                os.killpg(os.getpgid(proc.pid), 9)  # SIGKILL = 9
            except OSError:
                proc.kill()
        stdout, stderr = proc.communicate()
        raise subprocess.TimeoutExpired(cmd=exc.cmd, timeout=exc.timeout, output=stdout, stderr=stderr)
    return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)


def run_cli_command(workspace_root: Path, args: Sequence[str]) -> subprocess.CompletedProcess:
    return run_subprocess(
        [sys.executable, str(PIPELINE_CLI_PATH), *args],
        cwd=workspace_root,
        env=build_pipeline_env(workspace_root),
        timeout=CLI_STAGE_TIMEOUT_SECONDS,
    )


def bootstrap_workspace(workspace_root: Path) -> subprocess.CompletedProcess:
    return run_cli_command(workspace_root, ["bootstrap", "--mode", "overwrite"])


def probe_auth_status(provider: str, checks: List[Dict[str, Any]]) -> Tuple[bool, str]:
    if provider == "codex":
        for item in checks:
            if item.get("code") in {"agent_auth_ok", "agent_auth_shared"}:
                return True, str(item.get("detail", "")).strip()
        for item in checks:
            if item.get("code") == "agent_auth_missing":
                return False, str(item.get("detail", "")).strip()
        return False, "未检测到 Codex 认证文件。"

    if provider == "claude":
        try:
            completed = run_subprocess(
                ["claude", "auth", "status"],
                timeout=AUTH_PROBE_TIMEOUT_SECONDS,
            )
        except OSError as exc:
            return False, str(exc)
        except subprocess.TimeoutExpired:
            return False, "Claude 认证状态探测超时。"
        output = completed.stdout.strip() or completed.stderr.strip()
        if completed.returncode != 0:
            return False, output or "Claude 认证状态探测失败。"
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError:
            payload = {}
        if bool(payload.get("loggedIn")):
            method = str(payload.get("authMethod", "")).strip()
            provider_name = str(payload.get("apiProvider", "")).strip()
            detail = "Claude auth status 已登录。"
            if method or provider_name:
                detail = f"{detail} authMethod={method or 'unknown'} apiProvider={provider_name or 'unknown'}"
            return True, detail
        return False, output or "Claude 未登录。"

    if provider == "opencode":
        try:
            completed = run_subprocess(
                ["opencode", "providers", "list"],
                timeout=AUTH_PROBE_TIMEOUT_SECONDS,
            )
        except OSError as exc:
            return False, str(exc)
        except subprocess.TimeoutExpired:
            return False, "OpenCode 凭据探测超时。"
        output = "\n".join(part for part in (completed.stdout.strip(), completed.stderr.strip()) if part).strip()
        text = output.lower()
        if completed.returncode != 0:
            return False, output or "OpenCode 凭据探测失败。"
        if "0 credentials" in text:
            return False, output or "OpenCode 未检测到 provider 凭据。"
        if OPENCODE_CREDENTIALS_RE.search(text):
            return True, output or "OpenCode 已检测到 provider 凭据。"
        return False, output or "OpenCode 未检测到 provider 凭据。"

    return False, "未知 provider。"


def _trim(text: str, limit: int = 800) -> str:
    data = (text or "").strip()
    if len(data) <= limit:
        return data
    return data[:limit] + "...(truncated)"


def run_run_stage_with_retry(workspace_root: Path) -> Tuple[subprocess.CompletedProcess, int]:
    attempts = 0
    while True:
        attempts += 1
        try:
            return run_cli_command(workspace_root, ["run", "--max-chunks", "1"]), attempts
        except subprocess.TimeoutExpired:
            if attempts > RUN_STAGE_TIMEOUT_RETRIES:
                raise


def _workspace_root_for_provider(provider: str) -> Path:
    """Create workspace root appropriate for each provider.

    Codex refuses to create helper binaries under /tmp, so we use ~/.cache instead.
    Other providers can use standard temp directories.
    """
    if provider == "codex":
        CODEX_WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)
        return Path(tempfile.mkdtemp(prefix="workspace-", dir=str(CODEX_WORKSPACE_BASE)))
    return Path(tempfile.mkdtemp(prefix=f"real-validate-{provider}-"))


def run_provider_validation(
    provider: str,
    keep_workdir: bool = False,
    run_id_override: str = "",
) -> Dict[str, Any]:
    workspace_root = _workspace_root_for_provider(provider)
    result: Dict[str, Any] = {
        "provider": provider,
        "status": "failed",
        "message": "",
        "workspace_root": str(workspace_root),
        "precheck_results": [],
    }

    try:
        prepare_workspace(workspace_root, provider)
        try:
            bootstrap = bootstrap_workspace(workspace_root)
        except subprocess.TimeoutExpired:
            result["status"] = "failed"
            result["message"] = "bootstrap 阶段执行超时。"
            return result
        result["bootstrap"] = {
            "returncode": bootstrap.returncode,
            "stdout": _trim(bootstrap.stdout),
            "stderr": _trim(bootstrap.stderr),
        }
        if bootstrap.returncode != 0:
            result["status"] = "skipped_precheck_blocked"
            result["message"] = "bootstrap 失败，无法执行真实验收。"
            return result

        checks = doctor.collect_checks(root=workspace_root)
        auth_ok, auth_detail = probe_auth_status(provider, checks)
        status, message = determine_provider_status(provider, checks, auth_ok=auth_ok, auth_detail=auth_detail)
        result["precheck_results"] = checks
        result["auth_probe"] = {
            "ok": auth_ok,
            "detail": auth_detail,
        }
        result["status"] = status
        result["message"] = message
        if status != "ready":
            return result

        run_id = run_id_override or next_run_id(workspace_root / ".agents" / "runs")
        try:
            split_completed = run_cli_command(workspace_root, ["split", "--run-id", run_id])
        except subprocess.TimeoutExpired:
            result["status"] = "failed"
            result["message"] = "split 阶段执行超时。"
            return result
        result["split"] = {
            "returncode": split_completed.returncode,
            "stdout": _trim(split_completed.stdout),
            "stderr": _trim(split_completed.stderr),
            "run_id": run_id,
        }
        if split_completed.returncode != 0:
            result["status"] = "failed"
            result["message"] = "split 阶段失败。"
            return result

        try:
            run_completed, run_attempts = run_run_stage_with_retry(workspace_root)
        except subprocess.TimeoutExpired:
            result["status"] = "failed"
            result["message"] = "run 阶段执行超时。"
            return result
        result["run"] = {
            "returncode": run_completed.returncode,
            "stdout": _trim(run_completed.stdout),
            "stderr": _trim(run_completed.stderr),
            "attempts": run_attempts,
        }
        progress = load_json(workspace_root / ".agents" / "runtime" / "progress.json", {})
        result["progress_status"] = progress.get("status", "")

        if run_completed.returncode != 0:
            result["status"] = "failed"
            result["message"] = "run 阶段失败。"
            return result

        chunk_result_path = workspace_root / ".agents" / "runtime" / "results" / "chunk_001_result.json"
        result["result_exists"] = chunk_result_path.exists()
        if not chunk_result_path.exists():
            result["status"] = "failed"
            result["message"] = "run 阶段未生成 chunk 结果文件。"
            return result

        try:
            verify_completed = run_cli_command(workspace_root, ["verify", "1"])
        except subprocess.TimeoutExpired:
            result["status"] = "failed"
            result["message"] = "verify 阶段执行超时。"
            return result
        result["verify"] = {
            "returncode": verify_completed.returncode,
            "stdout": _trim(verify_completed.stdout),
            "stderr": _trim(verify_completed.stderr),
        }
        chunk_result = load_json(chunk_result_path, {})
        verification = chunk_result.get("verification", {})
        result["verification"] = verification
        if verify_completed.returncode != 0 or not bool(verification.get("passed")):
            result["status"] = "failed"
            result["message"] = "verify 阶段失败。"
            return result

        result["status"] = "passed"
        result["message"] = "真实 1 issue / 1 chunk 验收通过。"
        return result
    finally:
        if not keep_workdir:
            shutil.rmtree(workspace_root, ignore_errors=True)


def build_summary(results: List[Dict[str, Any]]) -> Dict[str, int]:
    summary = {
        "passed": 0,
        "failed": 0,
        "skipped_not_installed": 0,
        "skipped_auth_missing": 0,
        "skipped_precheck_blocked": 0,
    }
    for item in results:
        status = str(item.get("status", ""))
        if status in summary:
            summary[status] += 1
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    results = [
        run_provider_validation(provider, keep_workdir=bool(args.keep_workdir), run_id_override=str(args.run_id or ""))
        for provider in target_providers(args.provider)
    ]
    summary = build_summary(results)
    report = {
        "generated_at": now_iso(),
        "requested_provider": args.provider,
        "summary": summary,
        "providers": results,
    }
    report_path = Path(str(args.report))
    try:
        save_json(report_path, report)
    except OSError as exc:
        print(f"[validate-real] 无法写入报告文件: {report_path} ({exc})", file=sys.stderr)
        return 2

    for item in results:
        print(f"[validate-real] {item['provider']}: {item['status']} - {item.get('message', '')}")
    print(f"[validate-real] report: {report_path}")

    return 1 if summary["failed"] > 0 else 0
