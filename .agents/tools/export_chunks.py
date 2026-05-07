from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from common import (
    CONFIG_DIR,
    LOGS_DIR,
    ROOT,
    RUNTIME_DIR,
    load_json,
    now_iso,
    resolve_agent_staging_dir,
    save_json,
)


def resolve_host_id(args: argparse.Namespace) -> str:
    """三级优先级解析 host identifier：--host-id > PIPELINE_HOST_ID > socket.gethostname()"""
    return (
        getattr(args, "host_id", None)
        or os.environ.get("PIPELINE_HOST_ID", "").strip()
        or socket.gethostname()
    )


def try_generate_patch(root: Path = ROOT) -> Tuple[Optional[str], str]:
    """尝试生成 git diff patch。失败则降级返回 None 和提示信息。"""
    try:
        r = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(root),
            timeout=30,
        )
        if r.returncode != 0:
            return None, "git diff 失败，跳过 source patch"
        if not r.stdout.strip():
            return None, "无源码修改"
        return r.stdout, f"已生成 source patch ({len(r.stdout)} bytes)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, "git 不可用或超时，跳过 source patch（请自行同步源码修改）"
