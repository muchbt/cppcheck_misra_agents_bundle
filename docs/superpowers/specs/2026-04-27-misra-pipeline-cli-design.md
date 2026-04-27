# MISRA Pipeline CLI 分发方案设计

**日期**: 2026-04-27
**状态**: Draft

## 1. 目标

为内部团队提供便捷的 MISRA Pipeline 分发方案：
- 一键安装 CLI 工具到用户机器
- 在任意项目中执行 `misra-pipeline init` 初始化 `.agents/` 目录
- 支持升级、版本查看、环境检查
- 跨平台支持（Windows/Linux）

## 2. 架构

```
分发流程:

Git 仓库
    │
    ├── install.sh          ── Linux 安装入口
    ├── install.bat         ── Windows 安装入口
    └── cli/                ── Python CLI 实现
        ├── misra-pipeline-cli.py
        └── VERSION
    │
    ↓ 用户下载并执行
    │
~/.misra-pipeline/          ── 用户机器安装目录
    ├── bin/
    │   ├── misra-pipeline       (symlink/wrapper 脚本)
    │   └── cli/
    │       ├── misra-pipeline-cli.py
    │       └── VERSION
    └── installs/
        └── <project-hash>/      (可选：多项目版本追踪)
```

## 3. 安装流程

### 3.1 Linux (install.sh)

```bash
#!/bin/bash
# 用法: curl -sSL https://repo/install.sh | sh
# 或:   ./install.sh [--version vX.Y.Z]

set -e

REPO_URL="https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
INSTALL_DIR="$HOME/.misra-pipeline"
BIN_DIR="$INSTALL_DIR/bin"
CLI_DIR="$BIN_DIR/cli"
VERSION="${1:-main}"  # 默认 main 分支，可指定 tag

# 1. 创建目录结构
mkdir -p "$CLI_DIR"

# 2. 从 Git 仓库下载 CLI 文件
git archive --remote="$REPO_URL" "$VERSION" cli/ | tar -x -C "$BIN_DIR"

# 3. 创建 wrapper 脚本 (添加到 PATH)
cat > "$BIN_DIR/misra-pipeline" << 'WRAPPER'
#!/bin/bash
python3 "$HOME/.misra-pipeline/bin/cli/misra-pipeline-cli.py" "$@"
WRAPPER
chmod +x "$BIN_DIR/misra-pipeline"

# 4. 添加到 PATH (写入 shell profile)
if ! grep -q 'misra-pipeline/bin' "$HOME/.bashrc" 2>/dev/null; then
    echo 'export PATH="$HOME/.misra-pipeline/bin:$PATH"' >> "$HOME/.bashrc"
fi

# 5. 记录安装版本
echo "Installed version: $VERSION"
echo "Run: misra-pipeline init"
```

### 3.2 Windows (install.bat)

```batch
@echo off
REM 用法: install.bat [--version vX.Y.Z]

set REPO_URL=https://github.com/muchbt/cppcheck_misra_agents_bundle_v2
set INSTALL_DIR=%USERPROFILE%\.misra-pipeline
set BIN_DIR=%INSTALL_DIR%\bin
set CLI_DIR=%BIN_DIR%\cli

REM 1. 创建目录结构
mkdir "%CLI_DIR%" 2>nul

REM 2. 从 Git 仓库下载 (使用 PowerShell)
powershell -Command "Invoke-WebRequest -Uri '%REPO_URL%/archive/refs/heads/main.zip' -OutFile '%INSTALL_DIR%\temp.zip'"
powershell -Command "Expand-Archive -Path '%INSTALL_DIR%\temp.zip' -DestinationPath '%INSTALL_DIR%\temp' -Force"
xcopy "%INSTALL_DIR%\temp\*\cli\*" "%CLI_DIR%\" /E /Y

REM 3. 创建 wrapper 批处理文件
echo @echo off > "%BIN_DIR%\misra-pipeline.bat"
echo python "%CLI_DIR%\misra-pipeline-cli.py" %%* >> "%BIN_DIR%\misra-pipeline.bat"

REM 4. 添加到 PATH (用户环境变量)
powershell -Command "[Environment]::SetEnvironmentVariable('PATH', '%BIN_DIR%;' + [Environment]::GetEnvironmentVariable('PATH', 'User'), 'User')"

REM 5. 清理临时文件
del "%INSTALL_DIR%\temp.zip"
rmdir /S /Q "%INSTALL_DIR%\temp"

echo Installed version: main
echo Run: misra-pipeline init
```

## 4. CLI 命令设计

### 4.1 misra-pipeline-cli.py

单一 Python 脚本实现所有子命令：

```python
# cli/misra-pipeline-cli.py

import argparse
import subprocess
import sys
from pathlib import Path

REPO_URL = "https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
INSTALL_DIR = Path.home() / ".misra-pipeline"
CLI_DIR = INSTALL_DIR / "bin" / "cli"
VERSION_FILE = CLI_DIR / "VERSION"

def cmd_init(args):
    """在当前项目初始化 .agents/ 目录"""
    target_dir = Path.cwd() / ".agents"
    version = args.version or get_current_version()

    # 1. 检查目标目录是否存在
    if target_dir.exists():
        print(f"Error: {target_dir} already exists.")
        print("Please backup and remove it, or use --force to overwrite.")
        if not args.force:
            sys.exit(1)

    # 2. 从 Git 仓库下载 .agents/ 内容
    print(f"Initializing .agents/ from version: {version}")
    download_agents(target_dir, version)

    # 3. 创建版本文件
    write_version_file(target_dir / ".agents-version", version)

    print(f"Initialized: {target_dir}")
    print(f"Version: {version}")
    print("Next: configure .agents/config/pipeline.json")

def cmd_upgrade(args):
    """升级已安装项目到最新版本"""
    target_dir = Path.cwd() / ".agents"
    version_file = target_dir / ".agents-version"

    # 1. 检查是否已安装
    if not target_dir.exists():
        print("Error: .agents/ not found. Run 'misra-pipeline init' first.")
        sys.exit(1)

    # 2. 检查本地修改
    if has_local_modifications(target_dir):
        print("Error: Local modifications detected in .agents/")
        print("Please backup and resolve conflicts manually.")
        sys.exit(1)

    # 3. 获取最新版本
    current = read_version_file(version_file)
    latest = args.version or get_latest_version()

    if current == latest:
        print(f"Already at latest version: {current}")
        return

    print(f"Upgrading from {current} to {latest}")

    # 4. 执行升级 (覆盖 tools/templates，保留 config)
    upgrade_agents(target_dir, latest)

    # 5. 更新版本文件
    write_version_file(version_file, latest)
    print(f"Upgraded to: {latest}")

def cmd_version(args):
    """显示版本信息"""
    cli_version = read_version_file(VERSION_FILE) if VERSION_FILE.exists() else "unknown"
    print(f"CLI version: {cli_version}")

    target_dir = Path.cwd() / ".agents"
    version_file = target_dir / ".agents-version"
    if version_file.exists():
        project_version = read_version_file(version_file)
        print(f"Project version: {project_version}")

def cmd_doctor(args):
    """检查安装状态和依赖环境"""
    checks = [
        ("Python version", check_python_version()),
        ("CLI installed", check_cli_installed()),
        ("Git available", check_git_available()),
        ("Project initialized", check_project_initialized()),
    ]
    for name, result in checks:
        status = "OK" if result else "FAIL"
        print(f"  {name}: {status}")
```

### 4.2 子命令参数

| 命令 | 参数 | 说明 |
|------|------|------|
| `init` | `--version vX.Y.Z` | 指定安装版本，默认最新 |
| `init` | `--force` | 强制覆盖已存在的 `.agents/` |
| `upgrade` | `--version vX.Y.Z` | 升级到指定版本，默认最新 |
| `version` | 无 | 显示 CLI 和项目版本 |
| `doctor` | 无 | 检查环境 |

## 5. 版本文件格式

`.agents-version` 文件内容（混合记录）：

```json
{
  "tag": "v1.2.3",
  "commit": "abc123def456",
  "installed_at": "2026-04-27T10:30:00Z",
  "repo_url": "https://github.com/muchbt/cppcheck_misra_agents_bundle_v2"
}
```

## 6. 升级冲突检测

检测本地修改的逻辑：

```python
def has_local_modifications(target_dir: Path) -> bool:
    """检查是否有用户自定义修改"""
    # 保留文件列表（不检测这些文件的修改）
    preserved = {
        "config/pipeline.json",
        "config/rule_policy.json",
        "runtime/",
        "reports/",
        "runs/",
        "staging/",
    }

    # 检查 tools/ 和 templates/ 是否有修改
    # 通过 git diff 或文件 hash 比较
    version_file = target_dir / ".agents-version"
    if not version_file.exists():
        return True  # 无版本信息，视为已修改

    version_info = read_version_file(version_file)
    original_commit = version_info.get("commit")

    # 比较 tools/*.py 和 templates/*.json 的 hash
    for subdir in ["tools", "config/templates"]:
        for file in (target_dir / subdir).glob("*"):
            if file.is_file() and not is_original_file(file, original_commit):
                return True

    return False
```

## 7. 文件处理策略

| 文件类型 | init | upgrade | 说明 |
|----------|------|---------|------|
| `tools/*.py` | 复制 | 覆盖 | 工具脚本，始终更新 |
| `config/templates/*.json` | 复制 | 覆盖 | 策略模板，始终更新 |
| `config/pipeline.json` | 复制默认 | 保留 | 用户配置，不覆盖 |
| `config/rule_policy.json` | 不复制 | 保留 | 用户策略，不覆盖 |
| `prompts/*.txt` | 复制 | 覆盖 | Prompt 模板 |
| `skills/*` | 复制 | 覆盖 | Skill 定义 |
| `compat/*` | 复制 | 覆盖 | 兼容层模板 |
| `runtime/` | 创建空目录 | 保留 | 运行态数据 |
| `reports/` | 创建空目录 | 保留 | 报告数据 |
| `runs/` | 创建空目录 | 保留 | 归档数据 |
| `staging/` | 创建空目录 | 保留 | 临时数据 |

## 8. 错误处理

| 错误场景 | 处理方式 |
|----------|----------|
| Git 不可用 | doctor 检测，init/upgrade 报错退出 |
| 网络不可达 | 报错提示，建议检查网络或使用离线包 |
| Python 版本过低 | doctor 检测，CLI 入口版本守卫报错 |
| 目标目录已存在 | 提示使用 --force 或手动备份 |
| 本地有修改 | upgrade 报错，提示手动处理 |

## 9. 目录结构（仓库新增）

```
仓库根目录/
├── install.sh           # Linux 安装脚本
├── install.bat          # Windows 安装脚本
├── cli/                 # CLI 实现
│   ├── misra-pipeline-cli.py
│   └── VERSION          # 当前 CLI 版本
└── .agents/             # 原有内容（init 时复制到目标项目）
```

## 10. 测试计划

- install.sh 在 Linux/WSL 环境测试
- install.bat 在 Windows CMD/PowerShell 测试
- `misra-pipeline init` 测试正常安装和 --force
- `misra-pipeline upgrade` 测试版本升级和冲突检测
- `misra-pipeline version` 测试版本显示
- `misra-pipeline doctor` 测试环境检查
- 跨 Python 版本测试（3.8, 3.10）