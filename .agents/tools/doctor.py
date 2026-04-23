from __future__ import annotations

import argparse
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

from common import (
    ROOT,
    archive_size_bytes,
    load_json,
    read_text,
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


def _command_executable(command: str) -> str:
    parts = command.split()
    return parts[0] if parts else ""


def check_agent_command(config: Any) -> Dict[str, Any]:
    agent = config.get("agent", {}) if isinstance(config, dict) else {}
    command = agent.get("command", "") if isinstance(agent, dict) else ""
    executable = _command_executable(command)
    if not executable:
        return make_result(
            "error",
            "agent_command_missing",
            "agent.command 为空。",
            "无法判断 agent 命令是否可执行。",
        )
    if shutil.which(executable) is None:
        return make_result(
            "error",
            "agent_command_missing",
            "未找到 agent.command 指向的可执行程序。",
            f"命令: {command}",
        )
    return make_result(
        "ok",
        "agent_command_ok",
        "agent.command 可执行。",
        f"命令: {command}",
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

    executable = _command_executable(command.strip())
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


def collect_checks(root: Path = ROOT) -> List[Dict[str, Any]]:
    config_path = root / ".agents" / "config" / "pipeline.json"
    cppcheck_xml_path = root / "cppcheck.xml"
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
        check_cppcheck_xml(cppcheck_xml_path),
        check_agent_command(config),
        check_custom_verification_command(config),
    ]

    if config_error is not None:
        results.insert(2, config_error)
    else:
        results.insert(2, check_pipeline_config(config))

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
