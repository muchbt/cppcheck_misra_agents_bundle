from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from providers import get_provider
from common import (
    ROOT,
    archive_size_bytes,
    load_json,
    read_text,
    resolve_agent_staging_dir,
    validate_pipeline_config,
)

PROMPT_LENGTH_WARNING_THRESHOLD = 6000
UNFINISHED_STATUSES = {"ready", "running", "partial", "failed"}


def make_result(level: str, code: str, message: str, detail: str) -> Dict[str, Any]:
    return {
        "level": level,
        "code": code,
        "message": message,
        "detail": detail,
    }


def check_python_version() -> Dict[str, Any]:
    if sys.version_info < (3, 8):
        return make_result(
            "error",
            "python_version_unsupported",
            "Python 版本过低，doctor 需要 3.8 及以上。",
            f"当前版本: {sys.version.split()[0]}",
        )
    return make_result(
        "ok",
        "python_version",
        "Python 版本满足要求。",
        f"当前版本: {sys.version.split()[0]}",
    )


def check_cppcheck_xml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return make_result(
            "error",
            "cppcheck_xml_missing",
            "未找到 cppcheck.xml。",
            f"路径: {path}",
        )

    try:
        tree = ET.parse(path)
    except (ET.ParseError, OSError) as exc:
        return make_result(
            "error",
            "cppcheck_xml_invalid",
            "cppcheck.xml 不是有效的 XML。",
            f"路径: {path}; 详情: {exc}",
        )

    error_count = len(tree.findall(".//error"))
    if error_count == 0:
        return make_result(
            "warning",
            "cppcheck_xml_empty",
            "cppcheck.xml 是有效 XML，但没有发现 error 节点。",
            f"路径: {path}",
        )

    return make_result(
        "ok",
        "cppcheck_xml_ok",
        "cppcheck.xml 可用。",
        f"路径: {path}; error 节点数量: {error_count}",
    )


def check_pipeline_config(config: Any) -> Dict[str, Any]:
    errors, warnings = validate_pipeline_config(config)
    if errors:
        return make_result(
            "error",
            "pipeline_config_invalid",
            "pipeline.json 配置有误。",
            "; ".join(errors),
        )
    if warnings:
        return make_result(
            "warning",
            "pipeline_config_warning",
            "pipeline.json 配置存在警告。",
            "; ".join(warnings),
        )
    return make_result(
        "ok",
        "pipeline_config_ok",
        "pipeline.json 配置通过检查。",
        "配置项完整。",
    )


def _command_tokens(command: str) -> List[str]:
    return shlex.split(command)


def _resolve_launch_dir(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def _ensure_writable_dir(path: Path) -> str:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".doctor-write-check"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return str(exc)
    return ""


def _get_agent_provider_name(config: Any) -> str:
    agent = config.get("agent", {}) if isinstance(config, dict) else {}
    provider_name = agent.get("provider", "") if isinstance(agent, dict) else ""
    return str(provider_name).strip()


def _get_agent_launch(config: Any) -> Dict[str, Any]:
    agent = config.get("agent", {}) if isinstance(config, dict) else {}
    launch = agent.get("launch", {}) if isinstance(agent, dict) else {}
    return launch if isinstance(launch, dict) else {}


def check_agent_launch(config: Any, root: Path = ROOT) -> Dict[str, Any]:
    agent = config.get("agent", {}) if isinstance(config, dict) else {}
    provider_name = agent.get("provider", "") if isinstance(agent, dict) else ""
    launch = agent.get("launch", {}) if isinstance(agent, dict) else {}
    capabilities = agent.get("capabilities", {}) if isinstance(agent, dict) else {}

    if not isinstance(provider_name, str) or not provider_name.strip():
        return make_result(
            "error",
            "agent_provider_missing",
            "未配置 agent.provider。",
            "无法判断当前应使用哪个 provider。",
        )

    provider = get_provider(provider_name)
    if provider is None:
        return make_result(
            "error",
            "agent_provider_unsupported",
            "当前 agent.provider 不受支持。",
            f"provider: {provider_name}",
        )

    argv = launch.get("argv", []) if isinstance(launch, dict) else []
    if not isinstance(argv, list) or not argv or not all(isinstance(item, str) and item.strip() for item in argv):
        return make_result(
            "error",
            "agent_launch_invalid_argv",
            "agent.launch.argv 无效。",
            "launch.argv 必须是非空字符串数组。",
        )

    executable = argv[0]
    if shutil.which(executable) is None:
        return make_result(
            "error",
            "agent_launch_executable_missing",
            "未找到 agent.launch.argv 指向的可执行程序。",
            f"命令: {' '.join(argv)}",
        )

    prompt_via = launch.get("prompt_via")
    supported_prompt_via = getattr(provider, "SUPPORTED_PROMPT_VIA", {"stdin"})
    if prompt_via not in supported_prompt_via:
        return make_result(
            "error",
            "agent_launch_prompt_via_unsupported",
            "当前 provider 不支持该 prompt 传递方式。",
            f"provider: {provider_name}; prompt_via: {prompt_via}; supported: {', '.join(sorted(supported_prompt_via))}",
        )

    requires_tty = bool(launch.get("requires_tty"))
    non_interactive = bool(capabilities.get("non_interactive"))
    if requires_tty or not non_interactive:
        return make_result(
            "error",
            "agent_launch_interactive_not_supported",
            "当前 agent 配置仍依赖交互式执行。",
            "流水线只支持非交互模式。",
        )

    cwd_mode = launch.get("cwd")
    if cwd_mode not in {"project_root", "runtime_dir", "custom"}:
        return make_result(
            "error",
            "agent_launch_cwd_invalid",
            "agent.launch.cwd 无效。",
            f"cwd: {cwd_mode}",
        )

    prefix = getattr(provider, "NON_INTERACTIVE_COMMAND_PREFIX", [])
    if prefix:
        if argv[: len(prefix)] != prefix:
            return make_result(
                "error",
                "agent_launch_interactive_not_supported",
                f"当前 {provider_name} 配置仍是交互式或不受支持的启动方式。",
                f"期望前缀: {' '.join(prefix)}; 当前命令: {' '.join(argv)}",
            )

    env = launch.get("env", {}) if isinstance(launch, dict) else {}
    if isinstance(env, dict):
        for key, value in env.items():
            if not isinstance(key, str) or not key.strip() or not isinstance(value, str) or not value.strip():
                return make_result(
                    "error",
                    "agent_launch_env_invalid",
                    "agent.launch.env 无效。",
                    "env 键和值都必须是非空字符串。",
                )
            resolved = _resolve_launch_dir(root, value)
            error = _ensure_writable_dir(resolved)
            if error:
                return make_result(
                    "error",
                    "agent_launch_env_unwritable",
                    "agent 运行目录不可写。",
                    f"{key} -> {resolved}; 详情: {error}",
                )

    return make_result(
        "ok",
        "agent_launch_ok",
        "agent 启动配置适合非交互执行。",
        f"provider: {provider_name}; 命令: {' '.join(argv)}; prompt_via: {prompt_via}",
    )


def check_agent_staging_dir(config: Any, root: Path = ROOT) -> Dict[str, Any]:
    try:
        staging_dir = resolve_agent_staging_dir(config, root=root)
    except ValueError as exc:
        return make_result(
            "error",
            "agent_staging_dir_invalid",
            "agent.staging_dir 无效。",
            str(exc),
        )

    error = _ensure_writable_dir(staging_dir)
    if error:
        return make_result(
            "error",
            "agent_staging_dir_unwritable",
            "agent staging 目录不可写。",
            f"路径: {staging_dir}; 详情: {error}",
        )

    return make_result(
        "ok",
        "agent_staging_dir_ok",
        "agent staging 目录可写。",
        f"路径: {staging_dir}; agent 只写 staging，权威 runtime 由主流程导入维护。",
    )


def check_agent_auth(config: Any, root: Path = ROOT) -> Dict[str, Any]:
    provider_name = _get_agent_provider_name(config)
    if provider_name == "claude":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return make_result(
                "ok",
                "agent_auth_ok",
                "检测到 Claude Code 的环境认证。",
                "已检测到 ANTHROPIC_API_KEY。",
            )
        return make_result(
            "warning",
            "agent_auth_manual_check",
            "Claude Code 认证状态需要人工确认。",
            "请确认本机已通过 `claude auth login` 完成登录，或在运行环境中提供 ANTHROPIC_API_KEY。",
        )
    if provider_name != "codex":
        return make_result(
            "ok",
            "agent_auth_not_applicable",
            "当前 provider 无需额外认证检查。",
            f"provider: {provider_name or '未设置'}",
        )

    launch = _get_agent_launch(config)
    env = launch.get("env", {}) if isinstance(launch, dict) else {}
    codex_home_value = env.get("CODEX_HOME", "") if isinstance(env, dict) else ""
    codex_home = _resolve_launch_dir(root, codex_home_value) if isinstance(codex_home_value, str) and codex_home_value.strip() else None

    shared_auth = Path.home() / ".codex" / "auth.json"
    workspace_auth = codex_home / "auth.json" if codex_home is not None else None

    if workspace_auth is not None and workspace_auth.exists():
        return make_result(
            "ok",
            "agent_auth_ok",
            "agent 认证文件已就绪。",
            f"路径: {workspace_auth}",
        )
    if shared_auth.exists():
        detail = f"共享认证文件: {shared_auth}"
        if workspace_auth is not None:
            detail += f"; 运行时将同步到: {workspace_auth}"
        return make_result(
            "ok",
            "agent_auth_shared",
            "检测到可复用的共享认证文件。",
            detail,
        )
    return make_result(
        "error",
        "agent_auth_missing",
        "未找到可用的 agent 认证文件。",
        f"期望路径: {workspace_auth if workspace_auth is not None else '未配置 CODEX_HOME/auth.json'}; 共享路径: {shared_auth}",
    )


def check_agent_network(config: Any) -> Dict[str, Any]:
    provider_name = _get_agent_provider_name(config)
    if provider_name == "claude":
        return make_result(
            "ok",
            "agent_network_ok",
            "未发现 Claude Code 的显式网络阻断环境变量。",
            "真实运行仍依赖本机对 Claude 服务的外网访问能力。",
        )
    if provider_name != "codex":
        return make_result(
            "ok",
            "agent_network_not_applicable",
            "当前 provider 无需额外网络检查。",
            f"provider: {provider_name or '未设置'}",
        )

    launch = _get_agent_launch(config)
    argv = launch.get("argv", []) if isinstance(launch, dict) else []
    if "--oss" in argv:
        return make_result(
            "ok",
            "agent_network_local_provider",
            "当前 codex 配置使用本地 provider。",
            f"命令: {' '.join(argv)}",
        )

    if os.environ.get("CODEX_SANDBOX_NETWORK_DISABLED") == "1":
        return make_result(
            "warning",
            "agent_network_env_sanitized",
            "检测到继承的禁网环境变量，运行时会自动剥离。",
            "检测到 CODEX_SANDBOX_NETWORK_DISABLED=1；agent_runner 启动 codex exec 时会移除该变量。若宿主环境本身仍禁网，运行时仍可能失败。",
        )
    return make_result(
        "ok",
        "agent_network_ok",
        "未发现显式的 agent 网络阻断环境变量。",
        f"命令: {' '.join(argv)}",
    )


def check_custom_verification_command(config: Any) -> Dict[str, Any]:
    verification = config.get("verification", {}) if isinstance(config, dict) else {}
    command = verification.get("custom_command", "") if isinstance(verification, dict) else ""
    if not isinstance(command, str) or not command.strip():
        return make_result(
            "ok",
            "custom_verification_command_absent",
            "未配置自定义验证命令。",
            "跳过该项检查。",
        )

    try:
        parts = _command_tokens(command.strip())
    except ValueError as exc:
        return make_result(
            "error",
            "custom_verification_command_invalid_syntax",
            "自定义验证命令语法无效。",
            f"命令: {command}; 详情: {exc}",
        )
    if len(parts) > 1:
        return make_result(
            "warning",
            "custom_verification_command_compound",
            "自定义验证命令包含多个 token。",
            "当前版本只完整检查简单可执行文件名；复合命令请结合实际 shell 语义人工确认。",
        )
    executable = parts[0] if parts else ""
    if shutil.which(executable) is None:
        return make_result(
            "warning",
            "custom_verification_command_missing",
            "未找到自定义验证命令。",
            f"命令: {command}",
        )
    return make_result(
        "ok",
        "custom_verification_command_ok",
        "自定义验证命令可执行。",
        f"命令: {command}",
    )


def check_runtime_strategy(config: Any, progress: Any) -> Dict[str, Any]:
    config_mode = ""
    progress_mode = ""
    if isinstance(config, dict):
        fix_strategy = config.get("fix_strategy", {})
        if isinstance(fix_strategy, dict):
            config_mode = str(fix_strategy.get("mode", "")).strip()
    if isinstance(progress, dict):
        progress_mode = str(progress.get("fix_strategy", "")).strip()

    if config_mode and progress_mode and config_mode != progress_mode:
        return make_result(
            "warning",
            "runtime_strategy_mismatch",
            "运行时策略与配置策略不一致。",
            f"pipeline.json 为 {config_mode}，progress.json 为 {progress_mode}。",
        )
    return make_result(
        "ok",
        "runtime_strategy_ok",
        "运行时策略一致。",
        f"pipeline.json: {config_mode or '未设置'}; progress.json: {progress_mode or '未设置'}",
    )


def check_existing_unfinished_run(progress: Any) -> Dict[str, Any]:
    status = str(progress.get("status", "")).strip() if isinstance(progress, dict) else ""
    if status in UNFINISHED_STATUSES:
        return make_result(
            "warning",
            "unfinished_run",
            "检测到未完成的运行状态，oneshot 默认会继续恢复执行。",
            f"当前状态: {status}; oneshot 会优先继续上一次未完成的运行。",
        )
    return make_result(
        "ok",
        "unfinished_run_absent",
        "没有检测到未完成的运行。",
        f"当前状态: {status or '未设置'}",
    )


def check_archive_size(runs_dir: Path) -> Dict[str, Any]:
    if not runs_dir.exists():
        return make_result(
            "ok",
            "archive_empty",
            "未发现归档目录。",
            f"路径: {runs_dir}",
        )

    entries = list(runs_dir.iterdir())
    size = archive_size_bytes(runs_dir)
    if entries or size > 0:
        return make_result(
            "warning",
            "archive_nonempty",
            "归档目录已有内容，可能会影响诊断或恢复判断。",
            f"条目数: {len(entries)}; 总大小: {size} 字节; 路径: {runs_dir}",
        )
    return make_result(
        "ok",
        "archive_empty",
        "归档目录为空。",
        f"路径: {runs_dir}",
    )


def check_prompt_length(path: Path) -> Dict[str, Any]:
    text = read_text(path, "")
    if len(text) > PROMPT_LENGTH_WARNING_THRESHOLD:
        return make_result(
            "warning",
            "prompt_too_long",
            "fix_chunk_prompt.txt 提示词内容较长。",
            f"长度: {len(text)} 字符; 路径: {path}",
        )
    return make_result(
        "ok",
        "prompt_length_ok",
        "fix_chunk_prompt.txt 长度正常。",
        f"长度: {len(text)} 字符; 路径: {path}",
    )


def resolve_cppcheck_xml_path(root: Path, config: Any) -> Path:
    configured = "cppcheck.xml"
    if isinstance(config, dict):
        input_cfg = config.get("input", {})
        if isinstance(input_cfg, dict):
            value = input_cfg.get("cppcheck_xml")
            if isinstance(value, str) and value.strip():
                configured = value.strip()
    path = Path(configured)
    return path if path.is_absolute() else root / path


def collect_checks(root: Path = ROOT) -> List[Dict[str, Any]]:
    config_path = root / ".agents" / "config" / "pipeline.json"
    progress_path = root / ".agents" / "runtime" / "progress.json"
    prompt_path = root / ".agents" / "prompts" / "fix_chunk_prompt.txt"
    runs_dir = root / ".agents" / "runs"

    config_error = None
    try:
        config = load_json(config_path, {})
    except (OSError, json.JSONDecodeError) as exc:
        config = {}
        config_error = make_result(
            "error",
            "pipeline_config_invalid",
            "pipeline.json 不是有效的 JSON。",
            f"路径: {config_path}; 详情: {exc}",
        )
    progress_error = None
    try:
        progress = load_json(progress_path, {})
    except (OSError, json.JSONDecodeError) as exc:
        progress = {}
        progress_error = make_result(
            "error",
            "progress_json_invalid",
            "progress.json 不是有效的 JSON。",
            f"路径: {progress_path}; 详情: {exc}",
        )

    results = [
        check_python_version(),
        check_cppcheck_xml(resolve_cppcheck_xml_path(root, config)),
    ]

    if config_error is not None:
        results.insert(2, config_error)
    else:
        results.insert(2, check_pipeline_config(config))
        results.extend(
            [
                check_agent_launch(config, root),
                check_agent_staging_dir(config, root),
                check_agent_auth(config, root),
                check_agent_network(config),
                check_custom_verification_command(config),
            ]
        )

    if progress_error is not None:
        results.insert(4, progress_error)
    else:
        results.extend(
            [
                check_runtime_strategy(config, progress),
                check_existing_unfinished_run(progress),
            ]
        )

    results.extend(
        [
            check_archive_size(runs_dir),
            check_prompt_length(prompt_path),
        ]
    )

    return results


def print_checks(results: List[Dict[str, Any]]) -> None:
    labels = {
        "ok": "正常",
        "warning": "警告",
        "error": "错误",
    }
    for result in results:
        level = str(result.get("level", ""))
        label = labels.get(level, "信息")
        code = result.get("code", "")
        message = result.get("message", "")
        detail = result.get("detail", "")
        print(f"{label} [{code}] {message}")
        if detail:
            print(f"  详情: {detail}")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="诊断 cppcheck/MISRA pipeline 运行环境。")
    parser.parse_args(sys.argv[1:] if argv is None else argv)
    results = collect_checks()
    print_checks(results)
    return 1 if any(result.get("level") == "error" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
