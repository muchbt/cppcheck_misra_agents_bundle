---
name: cppcheck-scan-integration-design
description: 将 cppcheck_scan.py 集成到 MISRA 流水线 CLI，支持 scan 前置步骤和阈值式 review 循环
type: project
---

# cppcheck_scan 集成设计

## 概述

将独立脚本 `cppcheck_scan.py` 集成到 MISRA 流水线 CLI，分两期实现：

- **一期**：集成 cppcheck_scan.py 的 6 个子命令到 CLI，支持 scan 前置步骤，扫描完成后交互式更新配置
- **二期**：实现阈值式 review 循环，支持 `scan → fix → review → fix` 直到目标 issue 消除

## 一期设计

### 目标

- 提供 `misra-pipeline scan` 命令组，完整集成 cppcheck_scan.py 功能
- 扫描完成后自动检测并交互式提示用户更新 `pipeline.json` 配置
- 不修改现有 `split → run → merge` 流程，仅提供前置衔接点

### 文件变更

| 变更类型 | 文件 | 说明 |
|---------|------|------|
| 移动 | `cppcheck_scan.py` → `.agents/tools/cppcheck_scan.py` | 与现有工具模块统一位置 |
| 修改 | `cli/misra-pipeline-cli.py` | 添加 scan 命令组及嵌套子命令 |
| 修改 | `.agents/tools/cppcheck_scan.py` | 适配模块化调用，支持 main(argv) 入口 |
| 新增 | `.agents/tools/config_update.py` (可选) | 配置更新辅助函数，或放入 common.py |

### CLI 命令结构

```
misra-pipeline scan [args...]              # 默认全流程（对应 scan 子命令）
misra-pipeline scan expand [args...]       # 单步：展开 compile_commands.json
misra-pipeline scan filter-db [args...]    # 单步：过滤 compile_commands 条目
misra-pipeline scan cppcheck [args...]     # 单步：运行 cppcheck 扫描
misra-pipeline scan filter-xml [args...]   # 单步：过滤 cppcheck XML 报告
misra-pipeline scan html-report [args...]  # 单步：生成 HTML 报告
```

### 参数透传机制

CLI 层不定义 cppcheck_scan.py 的具体参数，使用 `parse_known_args` 实现：

```python
def parse_args(argv):
    parser = argparse.ArgumentParser(prog="misra-pipeline")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # scan 命令组
    scan_parser = subparsers.add_parser("scan", help="cppcheck 扫描工作流")
    scan_subparsers = scan_parser.add_subparsers(dest="scan_action")

    # 默认子命令（无 action 时执行全流程）
    # 不添加 parser，通过 dest 判断

    # 单步子命令：expand, filter-db, cppcheck, filter-xml, html-report
    for action in ["expand", "filter-db", "cppcheck", "filter-xml", "html-report"]:
        scan_subparsers.add_parser(action)

    parsed, forwarded = parser.parse_known_args(argv)
    return parsed, forwarded

def cmd_scan(args, forwarded):
    action = args.scan_action or "scan"
    return cppcheck_scan.main([action, *forwarded])
```

### 扫描完成后的配置更新交互

**触发条件**：
- scan 子命令执行成功（exit code 0）
- 生成的 XML 路径与当前 `input.cppcheck_xml` 配置不同

**交互流程**：
1. 检测生成的 XML 路径（从 cppcheck_scan 输出或 `find_latest_xml`）
2. 加载 `pipeline.json`，读取 `input.cppcheck_xml`
3. 比较路径（相对路径转绝对路径后比较）
4. 若不同，打印提示并询问：
   ```
   [scan] 扫描完成，生成 XML: cppcheck_result/20260515-103045/cppcheck_result.xml
   [scan] 当前配置: input.cppcheck_xml = cppcheck.xml
   [scan] 是否更新配置指向最新结果？[Y/n]
   ```
5. 用户输入 `Y` 或回车 → 更新 `pipeline.json`，打印确认
6. 用户输入 `n` → 跳过更新，提示手动修改路径

**配置更新实现**：
```python
def update_pipeline_cppcheck_xml(new_xml_path: str, config_path: Path) -> bool:
    """更新 pipeline.json 中的 input.cppcheck_xml 字段。"""
    config = load_json(config_path)
    old_value = config.get("input", {}).get("cppcheck_xml", "")
    if old_value == new_xml_path:
        return False
    config.setdefault("input", {})["cppcheck_xml"] = new_xml_path
    save_json(config_path, config)
    return True
```

**注意**：保存的路径应使用相对路径（相对于项目根目录），便于配置文件在不同环境复用。

### 与现有流水线的衔接

一期不修改现有流程，用户手动衔接：

```
# 步骤 1: 执行扫描
misra-pipeline scan --project-root . --scan-files src/Bsw

# 步骤 2: 确认更新配置（交互式提示）
# 或手动配置: misra-pipeline config set cppcheck_xml cppcheck_result/xxx/cppcheck_result.xml

# 步骤 3: 进入修复流程
misra-pipeline run
```

### cppcheck_scan.py 模块化适配

**现有入口**：
```python
def main() -> int:
    args = parse_args()
    # ... handler(args)
```

**适配后**：
```python
def main(argv: Optional[List[str]] = None) -> int:
    """模块入口，返回 exit code。扫描路径通过 find_latest_xml() 检测。"""
    args = parse_args(argv)
    # ... handler(args)
    return exit_code
```

需要调整：
- `parse_args` 支持 argv 参数传入（保持向后兼容：argv=None 时使用 sys.argv）
- `main` 支持 argv 参数传入并返回 exit code
- CLI 通过 `find_latest_xml(project_root)` 检测生成的 XML 路径（已存在于 cppcheck_scan.py）

**Why**: 现有设计是独立脚本模式，适配后支持模块化调用，便于 CLI 集成和后续二期扩展。不修改返回值结构避免破坏向后兼容性。
**How to apply**: 修改 parse_args 和 main 函数签名，CLI 层通过现有 find_latest_xml 函数获取 XML 路径。

## 二期设计（预留）

### 目标

实现阈值式 review 循环：
- 支持按 error id、目录名、文件名指定目标
- 循环执行 `scan → fix → review` 直到目标达成或达到最大轮次

### 命令结构（预留）

```
misra-pipeline review [args...]           # 验证当前修复效果，对比前后 XML
misra-pipeline fix-loop [args...]         # scan → fix → review 循环
```

### review 命令参数（预留）

```
--target-error-id <id>        # 目标 error id，如 misra-c2012-4.1
--target-dir <dir>            # 目标目录，如 src/Bsw
--target-file <file>          # 目标文件，如 src/Bsw/bsw_main.c
--max-rounds <n>              # 最大循环轮次，默认 5
--threshold <n>               # 目标 issue 数阈值，默认 0（全部消除）
```

### fix-loop 流程（预留）

```
1. scan → 生成 baseline XML
2. split → run → merge → fix
3. review → 对比 baseline 与 fix 后 XML
4. 若目标 issue 数 > threshold 且 rounds < max_rounds：
   - 更新 baseline = fix 后 XML
   - 回到步骤 2
5. 否则结束，输出最终报告
```

### 数据结构预留

```json
{
  "review_result": {
    "baseline_xml": "cppcheck_result/baseline/cppcheck_result.xml",
    "current_xml": "cppcheck_result/round1/cppcheck_result.xml",
    "target_filter": {
      "error_ids": ["misra-c2012-4.1"],
      "dirs": ["src/Bsw"],
      "files": []
    },
    "baseline_count": 15,
    "current_count": 3,
    "eliminated": 12,
    "new_issues": 0,
    "remaining": 3,
    "round": 1,
    "max_rounds": 5,
    "threshold": 0,
    "status": "continue"
  }
}
```

## 测试要点

### 一期测试

1. **命令透传**：
   - `misra-pipeline scan --project-root .` → 正确执行全流程
   - `misra-pipeline scan cppcheck --cppcheck-enable warning` → 参数正确转发

2. **配置更新交互**：
   - scan 成功后正确检测 XML 路径
   - 配置相同时不触发交互
   - 配置不同时正确提示并等待用户输入
   - Y → 配置更新成功
   - n → 配置不变

3. **向后兼容**：
   - cppcheck_scan.py 作为独立脚本仍可运行：`python cppcheck_scan.py scan`

### 二期测试（预留）

1. **review 命令**：
   - 正确过滤目标 issue
   - 对比前后 XML 统计差异

2. **fix-loop 循环**：
   - 达到阈值时停止
   - 达到最大轮次时停止
   - 循环中正确更新 baseline

## 实现优先级

| 优先级 | 任务 | 依赖 |
|-------|------|------|
| P0 | 移动 cppcheck_scan.py 到 .agents/tools/ | 无 |
| P0 | 适配 cppcheck_scan.py 支持 main(argv) | 无 |
| P0 | CLI 添加 scan 命令组 | P0 任务完成 |
| P0 | 实现参数透传机制 | P0 任务完成 |
| P1 | 实现配置更新交互 | P0 任务完成 |
| P2 | review 命令（二期） | P0/P1 完成 |
| P2 | fix-loop 命令（二期） | P2 review 完成 |