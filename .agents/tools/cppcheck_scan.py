#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
cppcheck_scan.py

统一的 cppcheck 扫描工作流脚本，整合了 compile_commands.json 展开、
DB 过滤、cppcheck 扫描、XML 过滤和 HTML 报告生成。

子命令：
  scan          全流程：展开 → 过滤DB → cppcheck扫描 → XML过滤 → HTML报告（默认）
  expand        展开 compile_commands.json
  filter-db     按文件路径前缀过滤 compile_commands 条目
  cppcheck      运行 cppcheck 扫描
  filter-xml    过滤 cppcheck XML 报告
  html-report   生成 HTML 报告

全流程默认文件（基于 --project-root，默认为当前目录）：

  步骤 1 - expand
    读取: <project-root>/compile_commands.json     （自动检测）
          <project-root>/.cproject                 （自动检测）
    写出: <project-root>/compile_commands_expanded.json

  步骤 2 - filter-db（仅当指定 --scan-files 时执行）
    读取: <project-root>/compile_commands_expanded.json
    写出: <project-root>/compile_commands_expanded.json （原地覆盖，备份为 .bak）
    注: git worktree 下若本地不存在，自动从主仓库根目录读取

  步骤 3 - cppcheck
    读取: <project-root>/compile_commands_expanded.json
    写出: <project-root>/cppcheck_result/<timestamp>/cppcheck_result.xml
          <project-root>/cppcheck_result/<timestamp>/<timestamp>.log
    注: git worktree 下若本地不存在，自动从主仓库根目录读取

  步骤 4 - filter-xml（仅当指定 --filter-error-id 或 --filter-file-prefix 时执行）
    读取: <project-root>/cppcheck_result/<最新>/cppcheck_result.xml （自动查找最新）
    写出: 同输入文件（原地覆盖，备份为 .bak）

  步骤 5 - html-report
    读取: <project-root>/cppcheck_result/<最新>/cppcheck_result.xml （优先 _filtered）
    写出: <project-root>/cppcheck_result/<最新>/html_report/

示例：
  # 全流程扫描（默认子命令）
  python cppcheck_scan.py --project-root .
  python cppcheck_scan.py scan --project-root . --scan-files src/Bsw

  # 单步执行
  python cppcheck_scan.py expand --project-root .
  python cppcheck_scan.py filter-db --scan-files src/Bsw,src/Mcal
  python cppcheck_scan.py cppcheck
  python cppcheck_scan.py filter-xml --error-id unusedFunction
  python cppcheck_scan.py html-report
"""

import argparse
import base64
import datetime
import gzip
import json
import os
import shlex
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


SOURCE_EXTENSIONS = {
    ".c", ".cc", ".cpp", ".cxx", ".c++",
    ".h", ".hh", ".hpp", ".hxx",
    ".s", ".S"
}

DEFAULT_EXCLUDE_DIRS = {
    ".git", ".svn", ".hg", ".idea", ".vscode", "__pycache__",
    "node_modules", ".venv", "venv"
}

DEFAULT_MISRA_RULE_TEXTS_B64 = (
    "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"
    "vGF04x78+r/ATttF5ZVUwAA"
)

DEFAULT_MISRA_SUPPRESS_RULES = (
    "1.2,2.3,2.4,2.5,2.6,2.7,2.8,4.2,5.9,8.7,8.9,8.13,8.16,8.17,"
    "10.5,11.4,11.5,12.1,12.3,12.4,13.3,13.4,15.1,15.4,15.5,17.5,"
    "17.8,17.12,18.4,18.5,19.2,20.1,20.5,20.10,21.12,23.1,23.3,23.7"
)


class ProjectDetectionError(RuntimeError):
    pass


# =========================================================================
# 通用工具函数
# =========================================================================


def normpath(path: str) -> str:
    return os.path.normpath(os.path.abspath(path))


def strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "'" and s[-1] == "'")):
        return s[1:-1]
    return s


def is_windows() -> bool:
    return os.name == "nt"


def is_windows_abs_path(path: str) -> bool:
    import re
    return bool(re.match(r'^[A-Za-z]:[/\\]', path.strip()))


_WINDOWS_DRIVE_PATTERN = None


def get_windows_drive_pattern(path: str) -> Optional[str]:
    import re
    global _WINDOWS_DRIVE_PATTERN
    if _WINDOWS_DRIVE_PATTERN is None:
        _WINDOWS_DRIVE_PATTERN = re.compile(r'^([A-Za-z]:[/\\][^/\\]*[/\\][^/\\]*[/\\][^/\\]*)')
    match = _WINDOWS_DRIVE_PATTERN.match(path.strip())
    if match:
        return match.group(1)
    return None


def convert_windows_path_to_local(windows_path: str, windows_root: str, local_root: str) -> str:
    if not windows_path or not is_windows_abs_path(windows_path):
        return windows_path
    windows_path_norm = windows_path.replace('\\', '/')
    windows_root_norm = windows_root.replace('\\', '/')
    if windows_path_norm.lower().startswith(windows_root_norm.lower()):
        relative_part = windows_path_norm[len(windows_root_norm):]
        relative_part = relative_part.lstrip('/')
        return os.path.join(local_root, relative_part)
    return windows_path


def split_args_text(text: str) -> List[str]:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lexer = shlex.shlex(text, posix=not is_windows())
    lexer.whitespace_split = True
    lexer.commenters = ""
    return [tok.strip() for tok in lexer if tok.strip()]


def unique_keep_order(items: Iterable[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def safe_relpath(path: str, start: str) -> str:
    try:
        return os.path.relpath(path, start)
    except Exception:
        return path


def find_files_by_name(project_root: str, filename: str) -> List[str]:
    matches: List[str] = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDE_DIRS]
        if filename in files:
            matches.append(normpath(os.path.join(root, filename)))
    return matches


def load_json_file(path: str):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return json.load(f)


def looks_like_source_file(path_value: str) -> bool:
    p = strip_quotes(path_value)
    return Path(p).suffix in SOURCE_EXTENSIONS


def parse_comma_list(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def backup_file(path: str) -> str:
    """备份文件为 .bak，返回备份路径。"""
    backup_path = path + ".bak"
    shutil.copy2(path, backup_path)
    return backup_path


def find_latest_xml(project_root: str, prefer_filtered: bool = False) -> Optional[str]:
    """在 cppcheck_result/ 下查找最新的 XML 文件。
    prefer_filtered=True 时优先查找 *_filtered.xml。
    """
    result_base = normpath(os.path.join(project_root, "cppcheck_result"))
    if not os.path.isdir(result_base):
        return None

    subdirs = sorted(
        [d for d in os.listdir(result_base)
         if os.path.isdir(os.path.join(result_base, d))],
        reverse=True
    )

    for subdir_name in subdirs:
        subdir_path = os.path.join(result_base, subdir_name)

        if prefer_filtered:
            for f in os.listdir(subdir_path):
                if f.endswith("_filtered.xml") and os.path.isfile(os.path.join(subdir_path, f)):
                    return normpath(os.path.join(subdir_path, f))

        standard = os.path.join(subdir_path, "cppcheck_result.xml")
        if os.path.isfile(standard):
            return normpath(standard)

    return None


def find_latest_report_dir(project_root: str) -> Optional[str]:
    """在 cppcheck_result/ 下查找最新的报告目录。"""
    result_base = normpath(os.path.join(project_root, "cppcheck_result"))
    if not os.path.isdir(result_base):
        return None

    subdirs = sorted(
        [d for d in os.listdir(result_base)
         if os.path.isdir(os.path.join(result_base, d))],
        reverse=True
    )

    if subdirs:
        return normpath(os.path.join(result_base, subdirs[0]))
    return None


def default_html_report_dir(input_xml_path: str) -> str:
    """根据输入 XML 路径推导默认 HTML 报告目录。"""
    xml_dir = os.path.dirname(input_xml_path)
    return normpath(os.path.join(xml_dir, "html_report"))


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def get_git_worktree_main_root(path: str) -> Optional[str]:
    """检测当前目录是否在 git worktree 中。
    如果是链接工作树（linked worktree），返回主工作树的根目录；
    否则返回 None。
    """
    git_dir = os.path.join(path, ".git")
    if not os.path.isfile(git_dir):
        return None

    try:
        with open(git_dir, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read().strip()
    except OSError:
        return None

    if not content.startswith("gitdir: "):
        return None

    gitdir_path = content[len("gitdir: "):].strip()

    commondir = os.path.join(gitdir_path, "commondir")
    if not os.path.isfile(commondir):
        return None

    try:
        with open(commondir, "r", encoding="utf-8", errors="ignore") as f:
            common_rel = f.read().strip()
    except OSError:
        return None

    common_abs = normpath(os.path.join(os.path.dirname(commondir), common_rel))
    main_git_dir = normpath(common_abs)

    main_root = os.path.dirname(main_git_dir)
    if os.path.isdir(main_root):
        return main_root

    return None


def resolve_db_path(project_root: str, explicit_path: Optional[str],
                    filename: str = "compile_commands_expanded.json") -> Optional[str]:
    """解析 DB 文件路径。
    优先使用显式路径；若未指定，依次尝试 project_root 和 git worktree 主仓库根目录。
    返回找到的文件路径，或默认路径（找不到时报错用）。
    """
    if explicit_path is not None:
        return normpath(explicit_path)

    primary = normpath(os.path.join(project_root, filename))
    if os.path.isfile(primary):
        return primary

    worktree_root = get_git_worktree_main_root(project_root)
    if worktree_root is not None:
        secondary = normpath(os.path.join(worktree_root, filename))
        if os.path.isfile(secondary):
            print(f"[INFO] 当前目录为 git worktree，使用主仓库 DB: {secondary}")
            return secondary

    return primary


# =========================================================================
#  工程检测
# =========================================================================


def count_valid_compile_entries(db_path: str) -> int:
    try:
        data = load_json_file(db_path)
    except Exception:
        return -1
    if not isinstance(data, list):
        return -1
    valid = 0
    for item in data:
        if not isinstance(item, dict):
            continue
        file_value = item.get("file", "")
        if isinstance(file_value, str) and file_value and looks_like_source_file(file_value):
            valid += 1
    return valid


def detect_windows_root_from_db(db: List[Dict]) -> Optional[Tuple[str, str]]:
    for entry in db:
        directory = entry.get("directory", "")
        if directory and is_windows_abs_path(directory):
            build_dirs = {'Debug', 'Release', 'Debug_FLASH', 'Release_FLASH',
                          'debug', 'release', 'build', 'out'}
            parts = directory.replace('\\', '/').split('/')
            result_parts = []
            detected_build_dir = ""
            for part in parts:
                if part.lower() in {d.lower() for d in build_dirs} and not detected_build_dir:
                    detected_build_dir = part
                else:
                    result_parts.append(part)

            if len(result_parts) >= 2:
                windows_root = result_parts[0] + '\\' + '\\'.join(result_parts[1:])
                return (windows_root, detected_build_dir)
            elif len(result_parts) >= 1:
                windows_root = result_parts[0]
                return (windows_root, detected_build_dir)
            return (directory, "")
    return None


def choose_best_compile_db(project_root: str, candidates: Sequence[str]) -> str:
    if not candidates:
        raise ProjectDetectionError(
            f"未找到 compile_commands.json，请确认当前目录是工程根目录：{project_root}"
        )
    root_candidate = normpath(os.path.join(project_root, "compile_commands.json"))
    if root_candidate in {normpath(c) for c in candidates}:
        return root_candidate

    scored: List[Tuple[int, int, str]] = []
    for path in candidates:
        valid_count = count_valid_compile_entries(path)
        rel_depth = safe_relpath(path, project_root).count(os.sep)
        scored.append((valid_count, -rel_depth, normpath(path)))

    scored.sort(reverse=True)
    best_score = scored[0][0]
    if best_score < 0:
        raise ProjectDetectionError("找到 compile_commands.json，但文件内容无效，无法解析")
    return scored[0][2]


def choose_best_cproject(project_root: str, candidates: Sequence[str]) -> str:
    if not candidates:
        raise ProjectDetectionError(
            f"未找到 .cproject，请确认当前目录是 Eclipse/S32DS 工程根目录：{project_root}"
        )
    root_candidate = normpath(os.path.join(project_root, ".cproject"))
    if root_candidate in {normpath(c) for c in candidates}:
        return root_candidate

    candidates_sorted = sorted(
        (normpath(c) for c in candidates),
        key=lambda p: (safe_relpath(p, project_root).count(os.sep), len(p), p.lower())
    )
    return candidates_sorted[0]


def auto_detect_project_files(project_root: str) -> Tuple[str, str]:
    compile_candidates = find_files_by_name(project_root, "compile_commands.json")
    cproject_candidates = find_files_by_name(project_root, ".cproject")
    compile_db_path = choose_best_compile_db(project_root, compile_candidates)
    cproject_path = choose_best_cproject(project_root, cproject_candidates)
    return compile_db_path, cproject_path


# =========================================================================
#  展开 compile_commands
# =========================================================================


def read_text_file(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        return f.read()


def read_response_file(path: str, visited: Optional[Set[str]] = None) -> List[str]:
    if visited is None:
        visited = set()

    path = normpath(path)
    if path in visited:
        print(f"[WARN] 检测到循环引用 response file: {path}", file=sys.stderr)
        return []
    visited.add(path)

    if not os.path.isfile(path):
        print(f"[WARN] response file 不存在: {path}", file=sys.stderr)
        return []

    try:
        content = read_text_file(path)
    except OSError as e:
        print(f"[WARN] 读取 response file 失败: {path}: {e}", file=sys.stderr)
        return []

    tokens = split_args_text(content)
    result: List[str] = []
    base_dir = os.path.dirname(path)

    for tok in tokens:
        if tok.startswith("@"):
            nested = strip_quotes(tok[1:])
            nested_path = nested if os.path.isabs(nested) else os.path.join(base_dir, nested)
            result.extend(read_response_file(nested_path, visited))
        else:
            result.append(tok)
    return result


def normalize_path_for_platform(path: str, windows_root: Optional[str], local_root: str) -> str:
    if not path or "${" in path:
        return path
    if is_windows_abs_path(path) and not is_windows():
        if windows_root:
            converted = convert_windows_path_to_local(path, windows_root, local_root)
            if converted != path:
                return converted
        return path.replace('\\', '/')
    return path


def resolve_arg_path(base_dir: str, path_value: str,
                     windows_root: Optional[str] = None, local_root: Optional[str] = None) -> str:
    p = strip_quotes(path_value)
    if not p:
        return p
    if "${ProjDirPath}" in p:
        p = p.replace("${ProjDirPath}", local_root)
        return normpath(p)
    if "${" in p:
        return p
    if is_windows_abs_path(p) and not is_windows() and windows_root and local_root:
        converted = convert_windows_path_to_local(p, windows_root, local_root)
        if converted != p:
            return normpath(converted)
        return normpath(p.replace('\\', '/'))
    if os.path.isabs(p):
        return normpath(p)
    return normpath(os.path.join(base_dir, p))


def extract_existing_I_D(arguments: List[str], base_dir: str) -> Tuple[Set[str], Set[str]]:
    include_set: Set[str] = set()
    define_set: Set[str] = set()

    i = 0
    while i < len(arguments):
        arg = arguments[i]

        if arg == "-I":
            if i + 1 < len(arguments):
                include_set.add(resolve_arg_path(base_dir, arguments[i + 1]))
                i += 2
                continue
        elif arg.startswith("-I") and len(arg) > 2:
            include_set.add(resolve_arg_path(base_dir, arg[2:]))
            i += 1
            continue
        elif arg == "-D":
            if i + 1 < len(arguments):
                define_set.add(strip_quotes(arguments[i + 1]))
                i += 2
                continue
        elif arg.startswith("-D") and len(arg) > 2:
            define_set.add(strip_quotes(arg[2:]))
            i += 1
            continue

        i += 1

    return include_set, define_set


def merge_missing_I_D(arguments: List[str], base_dir: str,
                      includes: List[str], defines: List[str],
                      local_root: Optional[str] = None) -> List[str]:
    existing_includes, existing_defines = extract_existing_I_D(arguments, base_dir)

    merged: List[str] = []
    if arguments:
        merged.append(arguments[0])
        compiler_rest = arguments[1:]
    else:
        compiler_rest = []

    injected: List[str] = []

    for inc in includes:
        full_inc = resolve_arg_path(base_dir, inc, None, local_root)
        if full_inc not in existing_includes:
            injected.extend(["-I", full_inc])
            existing_includes.add(full_inc)

    for d in defines:
        d_norm = strip_quotes(d)
        if d_norm and d_norm not in existing_defines:
            injected.extend(["-D", d_norm])
            existing_defines.add(d_norm)

    merged.extend(injected)
    merged.extend(compiler_rest)
    return merged


def expand_arguments(arguments: List[str], base_dir: str,
                     windows_root: Optional[str] = None, local_root: Optional[str] = None) -> List[str]:
    expanded: List[str] = []

    for arg in arguments:
        if arg.startswith("@"):
            rsp = strip_quotes(arg[1:])
            if is_windows_abs_path(rsp) and not is_windows() and windows_root and local_root:
                rsp_path = convert_windows_path_to_local(rsp, windows_root, local_root)
            elif os.path.isabs(rsp):
                rsp_path = rsp
            else:
                rsp_path = os.path.join(base_dir, rsp)
            for tok in read_response_file(rsp_path):
                if "${ProjDirPath}" in tok and local_root:
                    tok = tok.replace("${ProjDirPath}", local_root)
                expanded.append(tok)
        else:
            if "${ProjDirPath}" in arg and local_root:
                arg = arg.replace("${ProjDirPath}", local_root)
            expanded.append(arg)

    return expanded


def find_config_node(root: ET.Element, config_name: Optional[str]) -> Optional[ET.Element]:
    all_configs = root.findall(".//configuration")
    if not all_configs:
        return None

    if not config_name:
        return all_configs[0]

    target_lower = config_name.strip().lower()

    for cfg in all_configs:
        name = (cfg.get("name") or "").strip().lower()
        if name == target_lower:
            return cfg

    for cfg in all_configs:
        name = (cfg.get("name") or "").strip().lower()
        if target_lower in name:
            return cfg

    return None


def parse_option_value(option: ET.Element) -> List[str]:
    values: List[str] = []
    direct_value = option.get("value")
    if direct_value:
        values.append(direct_value)

    for child in option:
        child_value = child.get("value")
        if child_value:
            values.append(child_value)

    return values


def looks_like_include_option(option: ET.Element) -> bool:
    s = " ".join([
        option.get("id", ""),
        option.get("name", ""),
        option.get("superClass", ""),
        option.get("valueType", "")
    ]).lower()
    keywords = [
        "include",
        "includepath",
        "include path",
        "include.paths",
        "gnu.c.compiler.option.include.paths",
        "gnu.cpp.compiler.option.include.paths",
    ]
    return any(k in s for k in keywords)


def looks_like_define_option(option: ET.Element) -> bool:
    s = " ".join([
        option.get("id", ""),
        option.get("name", ""),
        option.get("superClass", ""),
        option.get("valueType", "")
    ]).lower()
    keywords = [
        "define",
        "symbol",
        "definedsymbols",
        "preprocessor",
        "gnu.c.compiler.option.preprocessor.def.symbols",
        "gnu.cpp.compiler.option.preprocessor.def.symbols",
    ]
    return any(k in s for k in keywords)


def parse_cproject(cproject_path: str, config_name: Optional[str]) -> Tuple[List[str], List[str]]:
    if not os.path.isfile(cproject_path):
        raise FileNotFoundError(f".cproject 不存在: {cproject_path}")

    tree = ET.parse(cproject_path)
    root = tree.getroot()

    cfg = find_config_node(root, config_name)
    if cfg is None:
        if config_name:
            raise RuntimeError(f"未在 .cproject 中找到 configuration: {config_name}")
        raise RuntimeError("未在 .cproject 中找到 configuration")

    includes: List[str] = []
    defines: List[str] = []

    for option in cfg.findall(".//option"):
        values = parse_option_value(option)
        if looks_like_include_option(option):
            includes.extend(values)
        elif looks_like_define_option(option):
            defines.extend(values)

    return unique_keep_order(includes), unique_keep_order(defines)


def normalize_cproject_include(base_dir: str, item: str) -> str:
    item = strip_quotes(item).strip()
    if not item:
        return item
    if "${" in item:
        return item
    if os.path.isabs(item):
        return normpath(item)
    return normpath(os.path.join(base_dir, item))


def filter_resolvable_includes(base_dir: str, includes: List[str]) -> List[str]:
    out: List[str] = []
    for inc in includes:
        normalized = normalize_cproject_include(base_dir, inc)
        if normalized:
            out.append(normalized)
    return unique_keep_order(out)


def build_expanded_entry(entry: Dict,
                        cproject_includes: Optional[List[str]] = None,
                        cproject_defines: Optional[List[str]] = None,
                        windows_root: Optional[str] = None,
                        windows_build_dir: Optional[str] = None,
                        local_root: Optional[str] = None) -> Dict:
    directory = entry.get("directory", "")
    file_path = entry.get("file", "")
    arguments = entry.get("arguments")

    if not arguments:
        command = entry.get("command")
        if command:
            arguments = split_args_text(command)
        else:
            raise RuntimeError(f"条目缺少 arguments/command: {file_path}")

    actual_base_dir = directory if directory else os.getcwd()
    if is_windows_abs_path(actual_base_dir) and not is_windows() and windows_root and local_root:
        actual_base_dir = convert_windows_path_to_local(actual_base_dir, windows_root, local_root)
    base_dir = normpath(actual_base_dir)

    expanded_args = expand_arguments(arguments, base_dir, windows_root, local_root)

    if cproject_includes or cproject_defines:
        expanded_args = merge_missing_I_D(
            expanded_args,
            base_dir,
            cproject_includes or [],
            cproject_defines or [],
            local_root
        )

    new_entry = dict(entry)
    new_entry["arguments"] = expanded_args
    if is_windows_abs_path(directory) and not is_windows() and windows_root and local_root:
        new_entry["directory"] = base_dir
        if file_path:
            if is_windows_abs_path(file_path):
                new_entry["file"] = convert_windows_path_to_local(file_path, windows_root, local_root)
            elif not os.path.isabs(file_path):
                abs_file_path = os.path.normpath(os.path.join(base_dir, file_path))
                new_entry["file"] = abs_file_path
    if "command" in new_entry:
        del new_entry["command"]
    return new_entry


# =========================================================================
#  cppcheck 扫描相关函数
# =========================================================================


def check_command_exists(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def generate_report_dir(project_root: str) -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    report_dir = normpath(os.path.join(project_root, "cppcheck_result", timestamp))
    os.makedirs(report_dir, exist_ok=True)
    return report_dir


def run_command_with_live_log(cmd: List[str], log_path: str, verbose: bool = False) -> int:
    cmd_line = " ".join(cmd)
    if verbose:
        print(f"[INFO] 执行命令: {cmd_line}")

    with open(log_path, "a", encoding="utf-8", newline="\n") as lf:
        lf.write(f"[CMD] {cmd_line}\n")
        lf.write(f"[TIME] Start: {datetime.datetime.now().isoformat()}\n")
        lf.flush()

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
        except FileNotFoundError as e:
            msg = f"[ERROR] 命令未找到: {e}\n"
            lf.write(msg)
            print(msg, end="", file=sys.stderr)
            return 127
        except OSError as e:
            msg = f"[ERROR] 启动命令失败: {e}\n"
            lf.write(msg)
            print(msg, end="", file=sys.stderr)
            return 126

        for line in process.stdout:
            print(line, end="")
            lf.write(line)
            lf.flush()

        process.wait()
        lf.write(f"[TIME] End: {datetime.datetime.now().isoformat()}\n")
        lf.write(f"[EXIT] Code: {process.returncode}\n")
        return process.returncode


def find_misra_py() -> Optional[str]:
    candidates = [
        "/usr/share/cppcheck/addons/misra.py",
        "/usr/local/share/cppcheck/addons/misra.py",
    ]
    try:
        import cppcheck
        pkg_dir = os.path.dirname(cppcheck.__file__)
        candidates.insert(0, os.path.join(pkg_dir, "Cppcheck", "addons", "misra.py"))
        candidates.insert(1, os.path.join(pkg_dir, "addons", "misra.py"))
    except Exception:
        pass
    for p in candidates:
        if p and os.path.isfile(p):
            return normpath(p)
    return None


def _decode_embedded_rule_texts() -> bytes:
    compressed = base64.b64decode(DEFAULT_MISRA_RULE_TEXTS_B64)
    return gzip.decompress(compressed)


def setup_misra_addon(misra_config_path: Optional[str],
                      temp_dir: str,
                      verbose: bool = False) -> str:
    target_json = normpath(os.path.join(temp_dir, "misra.json"))

    if misra_config_path:
        src = normpath(misra_config_path)
        if not os.path.isfile(src):
            raise FileNotFoundError(f"指定的 misra 配置文件不存在: {src}")
        shutil.copy2(src, target_json)
        if verbose:
            print(f"[INFO] 已复制用户指定的 misra 配置到临时目录: {target_json}")
        return target_json

    misra_py = find_misra_py()
    if not misra_py:
        raise FileNotFoundError(
            "无法自动定位 misra.py，请确认 cppcheck addons 已安装，"
            "或通过 --cppcheck-misra-config 手动指定 misra.json"
        )

    rule_texts_path = normpath(os.path.join(temp_dir, "misra_rules.txt"))
    with open(rule_texts_path, "wb") as f:
        f.write(_decode_embedded_rule_texts())

    config = {
        "script": misra_py,
        "args": [
            f"--rule-texts={rule_texts_path}",
            f"--suppress-rules={DEFAULT_MISRA_SUPPRESS_RULES}",
        ],
    }
    with open(target_json, "w", encoding="utf-8", newline="\n") as f:
        json.dump(config, f, indent=2)
        f.write("\n")

    if verbose:
        print(f"[INFO] 已生成临时 misra 配置: {target_json}")
        print(f"[INFO] 使用 misra.py: {misra_py}")
    return target_json


def run_cppcheck(expanded_db_path: str, report_dir: str, project_root: str,
                 cppcheck_enable: str = "warning,style",
cppcheck_misra: bool = True,
                 cppcheck_misra_config: Optional[str] = None,
                 cppcheck_jobs: int = 0,
                 cppcheck_extra_args: str = "",
                 cppcheck_inline_suppr: bool = True,
                 verbose: bool = False) -> Tuple[int, str, str]:
    """调用 cppcheck 进行扫描。返回 (returncode, xml_path, log_path)。"""
    if cppcheck_jobs <= 0:
        cppcheck_jobs = max(1, os.cpu_count() or 4)

    build_dir = normpath(os.path.join(report_dir, ".cppcheck-build-dir"))
    os.makedirs(build_dir, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    xml_path = normpath(os.path.join(report_dir, "cppcheck_result.xml"))
    log_path = normpath(os.path.join(report_dir, f"{timestamp}.log"))

    cmd: List[str] = ["cppcheck"]
    cmd.append(f"--enable={cppcheck_enable}")
    cmd.append("--check-level=exhaustive")
    cmd.append(f"--project={expanded_db_path}")
    cmd.append(f"--cppcheck-build-dir={build_dir}")
    cmd.append("--xml")
    cmd.append("--xml-version=2")
    cmd.append(f"--output-file={xml_path}")
    cmd.append(f"-j{cppcheck_jobs}")

    if cppcheck_inline_suppr:
        cmd.append("--inline-suppr")

    if cppcheck_misra:
        addon_json = setup_misra_addon(cppcheck_misra_config, report_dir, verbose)
        cmd.append(f"--addon={addon_json}")

    if cppcheck_extra_args:
        extra = shlex.split(cppcheck_extra_args, posix=not is_windows())
        cmd.extend(extra)

    ret = run_command_with_live_log(cmd, log_path, verbose)
    return ret, xml_path, log_path


def run_cppcheck_htmlreport(xml_path: str, html_dir: str, source_dir: str,
                            log_path: str, verbose: bool = False) -> int:
    if not check_command_exists("cppcheck-htmlreport"):
        msg = "[WARN] 未找到 cppcheck-htmlreport，跳过 HTML 报告生成\n"
        print(msg, end="", file=sys.stderr)
        with open(log_path, "a", encoding="utf-8", newline="\n") as lf:
            lf.write(msg)
        return 0

    title = Path(source_dir).name
    try:
        git_cwd = source_dir if os.path.isdir(source_dir) else "."
        remote_res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=git_cwd, capture_output=True, text=True, timeout=5
        )
        branch_res = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_cwd, capture_output=True, text=True, timeout=5
        )
        commit_res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=git_cwd, capture_output=True, text=True, timeout=5
        )
        if remote_res.returncode == 0 and branch_res.returncode == 0 and commit_res.returncode == 0:
            remote_url = remote_res.stdout.strip()
            repo_name = Path(remote_url).stem if not remote_url.endswith(".git") else Path(remote_url).stem
            branch = branch_res.stdout.strip()
            commit = commit_res.stdout.strip()
            title = f"{repo_name}+{branch}+{commit}"
    except Exception:
        pass

    os.makedirs(html_dir, exist_ok=True)
    cmd: List[str] = [
        "cppcheck-htmlreport",
        f"--file={xml_path}",
        f"--report-dir={html_dir}",
        f"--source-dir={source_dir}",
        "--source-encoding=iso8859-1",
        f"--title={title}",
    ]

    return run_command_with_live_log(cmd, log_path, verbose)


# =========================================================================
#  Filter-DB：按文件路径前缀过滤 compile_commands 条目
# =========================================================================


def filter_db_entries(db: List[Dict], prefixes: List[str],
                      project_root: str, invert: bool = False) -> Tuple[List[Dict], int]:
    """过滤 compile_commands 条目。
    返回 (保留的条目列表, 移除的条目数)。
    invert=False（默认，包含模式）：只保留匹配前缀的条目
    invert=True（排除模式）：排除匹配前缀的条目
    """
    abs_prefixes: Set[str] = set()
    for p in prefixes:
        abs_prefixes.add(normpath(os.path.join(project_root, p)))

    kept: List[Dict] = []
    removed = 0

    for entry in db:
        file_path = entry.get("file", "")
        if not file_path:
            removed += 1
            continue

        if os.path.isabs(file_path):
            abs_file = normpath(file_path)
        else:
            abs_file = normpath(os.path.join(project_root, file_path))

        matches = any(abs_file.startswith(prefix) for prefix in abs_prefixes)

        if invert:
            if not matches:
                kept.append(entry)
            else:
                removed += 1
        else:
            if matches:
                kept.append(entry)
            else:
                removed += 1

    return kept, removed


# =========================================================================
#  Filter-XML：按 error id / 文件路径前缀过滤 cppcheck XML 报告
# =========================================================================


def matches_error_id(error_elem: ET.Element, error_ids: Set[str]) -> bool:
    eid = error_elem.get("id", "")
    return eid in error_ids


def matches_file_prefix(error_elem: ET.Element, prefix_set: Set[str], project_root: str) -> bool:
    for loc in error_elem.findall("location"):
        file_path = loc.get("file", "")
        if not file_path:
            continue
        if os.path.isabs(file_path):
            abs_file = normpath(file_path)
        else:
            abs_file = normpath(os.path.join(project_root, file_path))

        for prefix in prefix_set:
            if abs_file.startswith(prefix):
                return True
    return False


def should_keep_error(error_elem: ET.Element,
                      error_ids: Optional[Set[str]],
                      file_prefixes: Optional[Set[str]],
                      project_root: str,
                      invert_match: bool) -> bool:
    matched = False

    if error_ids is not None:
        matched = matched or matches_error_id(error_elem, error_ids)

    if file_prefixes is not None:
        matched = matched or matches_file_prefix(error_elem, file_prefixes, project_root)

    if invert_match:
        return matched
    return not matched


# =========================================================================
#  核心逻辑函数 (do_xxx)
# =========================================================================


def do_expand(project_root: str,
             compile_db_path: Optional[str] = None,
             cproject_path: Optional[str] = None,
             output_path: Optional[str] = None,
             config: Optional[str] = None,
             verbose: bool = False) -> Tuple[int, Optional[str]]:
    """展开 compile_commands.json。返回 (exit_code, output_path)。"""
    if compile_db_path is None or cproject_path is None:
        try:
            auto_compile_db, auto_cproject = auto_detect_project_files(project_root)
        except ProjectDetectionError as e:
            print(f"[ERROR] {e}", file=sys.stderr)
            return 2, None
        if compile_db_path is None:
            compile_db_path = auto_compile_db
        if cproject_path is None:
            cproject_path = auto_cproject

    compile_db_path = normpath(compile_db_path)
    cproject_path = normpath(cproject_path)

    if output_path is None:
        output_path = normpath(os.path.join(project_root, "compile_commands_expanded.json"))
    else:
        output_path = normpath(output_path)

    if not os.path.isfile(compile_db_path):
        print(f"[ERROR] compile_commands.json 不存在: {compile_db_path}", file=sys.stderr)
        return 2, None
    if not os.path.isfile(cproject_path):
        print(f"[ERROR] .cproject 不存在: {cproject_path}", file=sys.stderr)
        return 2, None

    try:
        db = load_json_file(compile_db_path)
    except Exception as e:
        print(f"[ERROR] 读取 compile_commands.json 失败: {e}", file=sys.stderr)
        return 2, None

    if not isinstance(db, list):
        print("[ERROR] compile_commands.json 格式错误：顶层应为数组", file=sys.stderr)
        return 2, None

    windows_root = None
    windows_build_dir = None
    if not is_windows():
        detected = detect_windows_root_from_db(db)
        if detected:
            windows_root, windows_build_dir = detected
            if verbose:
                print(f"[INFO] 检测到 Windows 工程根目录: {windows_root}")
                if windows_build_dir:
                    print(f"[INFO] 检测到构建目录: {windows_build_dir}")
                print(f"[INFO] 本地工程根目录: {project_root}")

    cproject_base_dir = os.path.dirname(cproject_path)
    try:
        raw_includes, raw_defines = parse_cproject(cproject_path, config)
        cproject_includes = filter_resolvable_includes(cproject_base_dir, raw_includes)
        cproject_defines = unique_keep_order(strip_quotes(d) for d in raw_defines if strip_quotes(d))
    except Exception as e:
        print(f"[ERROR] 解析 .cproject 失败: {e}", file=sys.stderr)
        return 2, None

    if verbose:
        print(f"[INFO] 工程根目录: {project_root}")
        print(f"[INFO] compile_commands.json: {compile_db_path}")
        print(f"[INFO] .cproject: {cproject_path}")
        print(f"[INFO] 输出文件: {output_path}")
        print(f"[INFO] 从 .cproject 提取 include 数量: {len(cproject_includes)}")
        print(f"[INFO] 从 .cproject 提取 define 数量: {len(cproject_defines)}")

    expanded_db: List[Dict] = []
    failed = 0

    for idx, entry in enumerate(db, 1):
        try:
            expanded_db.append(
                build_expanded_entry(
                    entry,
                    cproject_includes=cproject_includes,
                    cproject_defines=cproject_defines,
                    windows_root=windows_root,
                    windows_build_dir=windows_build_dir,
                    local_root=project_root,
                )
            )
            if verbose and idx % 50 == 0:
                print(f"[INFO] 已处理 {idx}/{len(db)}")
        except Exception as e:
            failed += 1
            file_path = entry.get("file", "<unknown>") if isinstance(entry, dict) else "<unknown>"
            print(f"[WARN] 处理失败: {file_path}: {e}", file=sys.stderr)
            expanded_db.append(entry)

    ensure_parent_dir(output_path)
    try:
        with open(output_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(expanded_db, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        print(f"[ERROR] 写出失败: {e}", file=sys.stderr)
        return 2, None

    print(f"[OK] 展开完成: {output_path}")
    print(f"[INFO] 条目总数: {len(db)}")
    print(f"[INFO] 失败条目: {failed}")
    return 0, output_path


def do_filter_db(input_db_path: str, output_db_path: str,
                 scan_files: List[str], scan_files_invert: bool,
                 project_root: str) -> Tuple[int, int, int]:
    """过滤 compile_commands DB。返回 (exit_code, kept_count, removed_count)。"""
    if not os.path.isfile(input_db_path):
        print(f"[ERROR] 输入文件不存在: {input_db_path}", file=sys.stderr)
        return 2, 0, 0

    try:
        db = load_json_file(input_db_path)
    except Exception as e:
        print(f"[ERROR] 读取输入文件失败: {e}", file=sys.stderr)
        return 2, 0, 0

    if not isinstance(db, list):
        print("[ERROR] 输入文件格式错误：顶层应为数组", file=sys.stderr)
        return 2, 0, 0

    kept_db, removed = filter_db_entries(db, scan_files, project_root, scan_files_invert)

    if output_db_path == input_db_path:
        backup_file(input_db_path)
        print(f"[INFO] 已备份: {input_db_path}.bak")

    ensure_parent_dir(output_db_path)
    try:
        with open(output_db_path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(kept_db, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except Exception as e:
        print(f"[ERROR] 写出失败: {e}", file=sys.stderr)
        return 2, 0, 0

    print(f"[OK] DB 过滤完成: {output_db_path}")
    print(f"[INFO] 保留条目数: {len(kept_db)}")
    print(f"[INFO] 移除条目数: {removed}")
    return 0, len(kept_db), removed


def do_cppcheck(project_db_path: str, report_dir: Optional[str],
                project_root: str,
                cppcheck_enable: str = "warning,style",
                cppcheck_misra: bool = False,
                cppcheck_misra_config: Optional[str] = None,
                cppcheck_jobs: int = 0,
                cppcheck_extra_args: str = "",
                cppcheck_inline_suppr: bool = True,
                verbose: bool = False) -> Tuple[int, str, str]:
    """运行 cppcheck 扫描。返回 (exit_code, xml_path, log_path)。"""
    if not os.path.isfile(project_db_path):
        print(f"[ERROR] 输入文件不存在: {project_db_path}", file=sys.stderr)
        return 2, "", ""

    if not check_command_exists("cppcheck"):
        print("[ERROR] 未找到 cppcheck 命令，请安装 cppcheck 后重试", file=sys.stderr)
        return 2, "", ""

    if report_dir is None:
        report_dir = generate_report_dir(project_root)
    else:
        report_dir = normpath(report_dir)
    os.makedirs(report_dir, exist_ok=True)

    print(f"[INFO] 扫描报告目录: {report_dir}")

    ret, xml_path, log_path = run_cppcheck(
        project_db_path, report_dir, project_root,
        cppcheck_enable=cppcheck_enable,
        cppcheck_misra=cppcheck_misra,
        cppcheck_misra_config=cppcheck_misra_config,
        cppcheck_jobs=cppcheck_jobs,
        cppcheck_extra_args=cppcheck_extra_args,
        cppcheck_inline_suppr=cppcheck_inline_suppr,
        verbose=verbose,
    )

    if ret != 0:
        print(f"[ERROR] cppcheck 执行失败，返回码: {ret}", file=sys.stderr)

    return ret, xml_path, log_path


def do_filter_xml(input_xml_path: str, output_xml_path: str,
                 error_ids: Optional[List[str]],
                 file_prefixes: Optional[List[str]],
                 project_root: str,
                 invert_match: bool) -> Tuple[int, int, int]:
    """过滤 cppcheck XML 报告。返回 (exit_code, kept_count, removed_count)。"""
    if not os.path.isfile(input_xml_path):
        print(f"[ERROR] 输入 XML 不存在: {input_xml_path}", file=sys.stderr)
        return 2, 0, 0

    abs_prefixes: Optional[Set[str]] = None
    if file_prefixes:
        abs_prefixes = set()
        for p in file_prefixes:
            abs_prefixes.add(normpath(os.path.join(project_root, p)))

    id_set: Optional[Set[str]] = set(error_ids) if error_ids else None

    try:
        tree = ET.parse(input_xml_path)
    except ET.ParseError as e:
        print(f"[ERROR] 解析 XML 失败: {e}", file=sys.stderr)
        return 2, 0, 0

    root = tree.getroot()
    if root.tag != "results":
        print(f"[WARN] 非标准 cppcheck XML 根节点: {root.tag}，仍尝试处理")

    errors_elem = root.find("errors")
    if errors_elem is None:
        print("[WARN] 未找到 <errors> 节点，XML 中可能不含任何错误")
        errors_elem = ET.SubElement(root, "errors")

    kept = 0
    removed = 0
    to_remove: List[ET.Element] = []

    for error in errors_elem.findall("error"):
        if should_keep_error(error, id_set, abs_prefixes, project_root, invert_match):
            kept += 1
        else:
            to_remove.append(error)
            removed += 1

    for error in to_remove:
        errors_elem.remove(error)

    if output_xml_path == input_xml_path:
        backup_file(input_xml_path)
        print(f"[INFO] 已备份: {input_xml_path}.bak")

    ensure_parent_dir(output_xml_path)
    try:
        tree.write(output_xml_path, encoding="utf-8", xml_declaration=True)
        with open(output_xml_path, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n")
    except OSError as e:
        print(f"[ERROR] 写出 XML 失败: {e}", file=sys.stderr)
        return 2, 0, 0

    print(f"[OK] XML 过滤完成: {output_xml_path}")
    print(f"[INFO] 保留 error 数量: {kept}")
    print(f"[INFO] 移除 error 数量: {removed}")
    return 0, kept, removed


def do_html_report(input_xml_path: str, report_dir: str,
                   project_root: str,
                   verbose: bool = False) -> int:
    """生成 HTML 报告。返回 exit_code。"""
    if not os.path.isfile(input_xml_path):
        print(f"[ERROR] 输入 XML 不存在: {input_xml_path}", file=sys.stderr)
        return 2

    html_dir = normpath(os.path.join(report_dir, "html_report"))
    log_path = normpath(os.path.join(report_dir, "html_report.log"))

    ret = run_cppcheck_htmlreport(input_xml_path, html_dir, project_root, log_path, verbose)
    if ret != 0:
        print(f"[ERROR] HTML 报告生成异常，返回码: {ret}", file=sys.stderr)
        return ret

    print(f"[OK] HTML 报告生成完成: {html_dir}")
    return 0


# =========================================================================
#  子命令入口
# =========================================================================


def cmd_expand(args: argparse.Namespace) -> int:
    project_root = normpath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"[ERROR] 工程根目录不存在: {project_root}", file=sys.stderr)
        return 2

    ret, _ = do_expand(
        project_root=project_root,
        compile_db_path=args.compile_db,
        cproject_path=args.cproject,
        output_path=args.output,
        config=args.config,
        verbose=args.verbose,
    )
    return ret


def cmd_filter_db(args: argparse.Namespace) -> int:
    project_root = normpath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"[ERROR] 工程根目录不存在: {project_root}", file=sys.stderr)
        return 2

    input_db = resolve_db_path(project_root, args.input_db)

    output_db = args.output_db
    if output_db is None:
        output_db = input_db
    else:
        output_db = normpath(output_db)

    scan_files = parse_comma_list(args.scan_files)
    if not scan_files:
        print("[ERROR] 必须指定 --scan-files 过滤条件", file=sys.stderr)
        return 2

    scan_files_invert = args.scan_files_invert

    ret, _, _ = do_filter_db(
        input_db_path=input_db,
        output_db_path=output_db,
        scan_files=scan_files,
        scan_files_invert=scan_files_invert,
        project_root=project_root,
    )
    return ret


def cmd_cppcheck(args: argparse.Namespace) -> int:
    project_root = normpath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"[ERROR] 工程根目录不存在: {project_root}", file=sys.stderr)
        return 2

    project_db = resolve_db_path(project_root, args.project_db)

    report_dir = args.report_dir
    if report_dir is not None:
        report_dir = normpath(report_dir)

    ret, xml_path, log_path = do_cppcheck(
        project_db_path=project_db,
        report_dir=report_dir,
        project_root=project_root,
        cppcheck_enable=args.cppcheck_enable,
        cppcheck_misra=args.cppcheck_misra,
        cppcheck_misra_config=args.cppcheck_misra_config,
        cppcheck_jobs=args.cppcheck_jobs,
        cppcheck_extra_args=args.cppcheck_extra_args,
        cppcheck_inline_suppr=args.cppcheck_inline_suppr,
        verbose=args.verbose,
    )

    if ret != 0:
        return ret

    print("[INFO] cppcheck 扫描完成")

    if os.path.isfile(xml_path):
        html_dir = report_dir if report_dir else normpath(os.path.join(project_root, "cppcheck_result"))
        ret_html = do_html_report(xml_path, html_dir, project_root, args.verbose)
        if ret_html != 0:
            return ret_html

    print(f"[INFO] XML 报告: {xml_path}")
    print(f"[INFO] 扫描日志: {log_path}")
    return 0


def cmd_filter_xml(args: argparse.Namespace) -> int:
    project_root = normpath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"[ERROR] 工程根目录不存在: {project_root}", file=sys.stderr)
        return 2

    input_xml = args.input_xml
    if input_xml is None:
        input_xml = find_latest_xml(project_root, prefer_filtered=False)
        if input_xml is None:
            print("[ERROR] 未找到 cppcheck XML 报告，请先运行 cppcheck 扫描", file=sys.stderr)
            return 2
        print(f"[INFO] 自动选择 XML 报告: {input_xml}")
    else:
        input_xml = normpath(input_xml)

    output_xml = args.output_xml
    if output_xml is None:
        output_xml = input_xml
    else:
        output_xml = normpath(output_xml)

    error_ids = parse_comma_list(args.error_id) or None
    file_prefixes = parse_comma_list(args.file_prefix) or None

    if error_ids is None and file_prefixes is None:
        print("[ERROR] 必须指定 --error-id 或 --file-prefix 至少一个过滤条件", file=sys.stderr)
        return 2

    ret, _, _ = do_filter_xml(
        input_xml_path=input_xml,
        output_xml_path=output_xml,
        error_ids=error_ids,
        file_prefixes=file_prefixes,
        project_root=project_root,
        invert_match=args.invert_match,
    )
    return ret


def cmd_html_report(args: argparse.Namespace) -> int:
    project_root = normpath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"[ERROR] 工程根目录不存在: {project_root}", file=sys.stderr)
        return 2

    input_xml = args.input_xml
    if input_xml is None:
        input_xml = find_latest_xml(project_root, prefer_filtered=True)
        if input_xml is None:
            input_xml = find_latest_xml(project_root, prefer_filtered=False)
        if input_xml is None:
            print("[ERROR] 未找到 cppcheck XML 报告，请先运行 cppcheck 扫描", file=sys.stderr)
            return 2
        print(f"[INFO] 自动选择 XML 报告: {input_xml}")
    else:
        input_xml = normpath(input_xml)

    report_dir = args.report_dir
    if report_dir is None:
        xml_dir = os.path.dirname(input_xml)
        if xml_dir and os.path.isdir(xml_dir):
            report_dir = xml_dir
        else:
            report_dir = normpath(os.path.join(project_root, "cppcheck_result"))
    else:
        report_dir = normpath(report_dir)

    return do_html_report(input_xml, report_dir, project_root, args.verbose)


def cmd_scan(args: argparse.Namespace) -> int:
    project_root = normpath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"[ERROR] 工程根目录不存在: {project_root}", file=sys.stderr)
        return 2

    # Step 1: expand
    print("=" * 60)
    print("[STEP 1/5] 展开 compile_commands.json")
    print("=" * 60)
    expanded_db_path = normpath(os.path.join(project_root, "compile_commands_expanded.json"))
    ret, expanded_db_path = do_expand(
        project_root=project_root,
        compile_db_path=args.compile_db,
        cproject_path=args.cproject,
        output_path=args.output,
        config=args.config,
        verbose=args.verbose,
    )
    if ret != 0:
        return ret

    # Step 2: filter-db (if --scan-files specified)
    scan_files = parse_comma_list(args.scan_files)
    if scan_files:
        print()
        print("=" * 60)
        print("[STEP 2/5] 过滤 compile_commands DB")
        print("=" * 60)
        ret, _, _ = do_filter_db(
            input_db_path=expanded_db_path,
            output_db_path=expanded_db_path,
            scan_files=scan_files,
            scan_files_invert=args.scan_files_invert,
            project_root=project_root,
        )
        if ret != 0:
            return ret
    else:
        print("[STEP 2/5] 跳过 DB 过滤（未指定 --scan-files）")

    # Step 3: cppcheck
    print()
    print("=" * 60)
    print("[STEP 3/5] 运行 cppcheck 扫描")
    print("=" * 60)
    report_dir = args.report_dir
    if report_dir is not None:
        report_dir = normpath(report_dir)

    extra_args = args.cppcheck_extra_args
    if scan_files:
        if "--suppress=unusedFunction" not in extra_args:
            extra_args = (extra_args + " --suppress=unusedFunction").strip()
            print("[INFO] 已过滤 DB 条目，自动追加 --suppress=unusedFunction 以减少误报")

    ret, xml_path, log_path = do_cppcheck(
        project_db_path=expanded_db_path,
        report_dir=report_dir,
        project_root=project_root,
        cppcheck_enable=args.cppcheck_enable,
        cppcheck_misra=args.cppcheck_misra,
        cppcheck_misra_config=args.cppcheck_misra_config,
        cppcheck_jobs=args.cppcheck_jobs,
        cppcheck_extra_args=extra_args,
        cppcheck_inline_suppr=args.cppcheck_inline_suppr,
        verbose=args.verbose,
    )
    if ret != 0:
        return ret

    # Step 4: filter-xml (if --filter-error-id or --filter-file-prefix specified)
    error_ids = parse_comma_list(args.filter_error_id) or None
    file_prefixes = parse_comma_list(args.filter_file_prefix) or None

    if error_ids is not None or file_prefixes is not None:
        print()
        print("=" * 60)
        print("[STEP 4/5] 过滤 XML 报告")
        print("=" * 60)

        abs_prefixes_for_xml: Optional[List[str]] = None
        if file_prefixes is not None:
            abs_prefixes_for_xml = file_prefixes

        ret, _, _ = do_filter_xml(
            input_xml_path=xml_path,
            output_xml_path=xml_path,
            error_ids=error_ids,
            file_prefixes=abs_prefixes_for_xml,
            project_root=project_root,
            invert_match=args.filter_invert_match,
        )
        if ret != 0:
            return ret
    else:
        print("[STEP 4/5] 跳过 XML 过滤（未指定 --filter-error-id 或 --filter-file-prefix）")

    # Step 5: html-report
    print()
    print("=" * 60)
    print("[STEP 5/5] 生成 HTML 报告")
    print("=" * 60)
    actual_report_dir = report_dir if report_dir else find_latest_report_dir(project_root)
    if actual_report_dir is None:
        actual_report_dir = generate_report_dir(project_root)

    ret = do_html_report(xml_path, actual_report_dir, project_root, args.verbose)
    if ret != 0:
        return ret

    print()
    print("=" * 60)
    print("[OK] 全流程扫描完成")
    print("=" * 60)
    print(f"[INFO] XML 报告: {xml_path}")
    print(f"[INFO] HTML 报告: {normpath(os.path.join(actual_report_dir, 'html_report'))}")
    print(f"[INFO] 扫描日志: {log_path}")
    return 0


# =========================================================================
#  参数解析
# =========================================================================


def add_common_project_arg(parser: argparse.ArgumentParser):
    parser.add_argument("--project-root", default=".", help="工程根目录，默认当前目录")


def add_common_verbose_arg(parser: argparse.ArgumentParser):
    parser.add_argument("--verbose", action="store_true", help="打印更多日志")


def add_cppcheck_args(parser: argparse.ArgumentParser):
    parser.add_argument("--cppcheck-enable", default="warning,style",
                        help="cppcheck --enable 参数，默认 warning,style")
    parser.add_argument("--cppcheck-misra", dest="cppcheck_misra",
                        action="store_true", default=True,
                        help="启用 misra 扫描（默认启用）")
    parser.add_argument("--no-cppcheck-misra", dest="cppcheck_misra",
                        action="store_false",
                        help="禁用 misra 扫描")
    parser.add_argument("--cppcheck-misra-config",
                        help="指定 misra addon 的 JSON 配置文件路径")
    parser.add_argument("--cppcheck-jobs", type=int, default=0,
                        help="cppcheck 并行扫描线程数，默认 CPU 核心数")
    parser.add_argument("--cppcheck-extra-args", default="",
                        help="cppcheck 额外自定义参数")
    parser.add_argument("--no-cppcheck-inline-suppr", dest="cppcheck_inline_suppr",
                        action="store_false", default=True,
                        help="禁用 cppcheck inline suppress 功能")


SUBCOMMAND_NAMES = {"expand", "filter-db", "cppcheck", "filter-xml", "html-report", "scan"}


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    if argv is None:
        argv = sys.argv[1:]

    # If --help or -h is at root level, don't prepend "scan" - let argparse show all subcommands
    if argv and argv[0] in ("-h", "--help"):
        pass
    elif not argv or argv[0] not in SUBCOMMAND_NAMES:
        argv = ["scan"] + list(argv)

    parser = argparse.ArgumentParser(
        description="统一的 cppcheck 扫描工作流脚本"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # --- expand ---
    sp_expand = subparsers.add_parser("expand", help="展开 compile_commands.json")
    add_common_project_arg(sp_expand)
    sp_expand.add_argument("--compile-db", help="指定 compile_commands.json 路径（自动检测）")
    sp_expand.add_argument("--cproject", help="指定 .cproject 路径（自动检测）")
    sp_expand.add_argument("--output", help="输出文件路径")
    sp_expand.add_argument("--config", help=".cproject 中的 configuration 名称")
    add_common_verbose_arg(sp_expand)

    # --- filter-db ---
    sp_filter_db = subparsers.add_parser("filter-db", help="按文件路径前缀过滤 compile_commands 条目")
    add_common_project_arg(sp_filter_db)
    sp_filter_db.add_argument("--input-db", help="输入 DB 文件路径（默认 compile_commands_expanded.json）")
    sp_filter_db.add_argument("--output-db", help="输出 DB 文件路径（默认覆盖输入）")
    sp_filter_db.add_argument("--scan-files", default="",
                              help="逗号分隔的文件路径前缀，如 src/Bsw,src/Mcal")
    sp_filter_db.add_argument("--scan-files-invert", action="store_true",
                              help="排除模式：排除匹配前缀的条目，保留其余")

    # --- cppcheck ---
    sp_cppcheck = subparsers.add_parser("cppcheck", help="运行 cppcheck 扫描")
    add_common_project_arg(sp_cppcheck)
    sp_cppcheck.add_argument("--project-db", help="输入 DB 文件路径（默认 compile_commands_expanded.json）")
    sp_cppcheck.add_argument("--report-dir", help="扫描报告输出目录")
    add_cppcheck_args(sp_cppcheck)
    add_common_verbose_arg(sp_cppcheck)

    # --- filter-xml ---
    sp_filter_xml = subparsers.add_parser("filter-xml", help="过滤 cppcheck XML 报告")
    add_common_project_arg(sp_filter_xml)
    sp_filter_xml.add_argument("--input-xml", help="输入 XML 路径（自动查找最新）")
    sp_filter_xml.add_argument("--output-xml", help="输出 XML 路径（默认覆盖输入）")
    sp_filter_xml.add_argument("--error-id", default="",
                               help="逗号分隔的 error id 列表，如 uninitvar,constVariable")
    sp_filter_xml.add_argument("--file-prefix", default="",
                               help="逗号分隔的文件路径前缀列表，如 src/Bsw,src/Mcal")
    sp_filter_xml.add_argument("--invert-match", action="store_true",
                               help="保留模式：匹配的 error 保留在输出中")

    # --- html-report ---
    sp_html = subparsers.add_parser("html-report", help="生成 HTML 报告")
    add_common_project_arg(sp_html)
    sp_html.add_argument("--input-xml", help="输入 XML 路径（自动查找最新，优先 _filtered）")
    sp_html.add_argument("--report-dir", help="HTML 报告输出目录")
    add_common_verbose_arg(sp_html)

    # --- scan (default) ---
    sp_scan = subparsers.add_parser("scan", help="全流程：展开 → 过滤DB → cppcheck → XML过滤 → HTML报告")
    add_common_project_arg(sp_scan)
    sp_scan.add_argument("--compile-db", help="指定 compile_commands.json 路径（自动检测）")
    sp_scan.add_argument("--cproject", help="指定 .cproject 路径（自动检测）")
    sp_scan.add_argument("--output", help="展开输出文件路径")
    sp_scan.add_argument("--config", help=".cproject 中的 configuration 名称")
    sp_scan.add_argument("--scan-files", default="",
                          help="逗号分隔的文件路径前缀（触发 filter-db 步骤）")
    sp_scan.add_argument("--scan-files-invert", action="store_true",
                          help="排除模式：排除匹配的条目")
    sp_scan.add_argument("--filter-error-id", default="",
                         help="逗号分隔的 error id（触发 filter-xml 步骤）")
    sp_scan.add_argument("--filter-file-prefix", default="",
                         help="逗号分隔的文件路径前缀（触发 filter-xml 步骤）")
    sp_scan.add_argument("--filter-invert-match", action="store_true",
                         help="XML 过滤保留模式")
    sp_scan.add_argument("--report-dir", help="扫描报告输出目录")
    add_cppcheck_args(sp_scan)
    add_common_verbose_arg(sp_scan)

    return parser.parse_args(argv)


# =========================================================================
#  主入口
# =========================================================================


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point. Supports both CLI invocation and module import.

    Args:
        argv: Command line arguments. If None, uses sys.argv[1:].

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    args = parse_args(argv)

    commands = {
        "expand": cmd_expand,
        "filter-db": cmd_filter_db,
        "cppcheck": cmd_cppcheck,
        "filter-xml": cmd_filter_xml,
        "html-report": cmd_html_report,
        "scan": cmd_scan,
    }

    handler = commands.get(args.command)
    if handler is None:
        print(f"[ERROR] 未知子命令: {args.command}", file=sys.stderr)
        return 2

    return handler(args)


if __name__ == "__main__":
    sys.exit(main())