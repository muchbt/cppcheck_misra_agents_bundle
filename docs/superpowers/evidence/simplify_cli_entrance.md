Let me first understand the current parameter complexity of the key workflow commands.









Now I have a full picture of the current architecture. Let me analyze the current user journey vs the ideal.

# CLI 简化方向分析

## 当前用户流程（至少 5 步）

```
1. misra-pipeline init                                          # 初始化 .agents/
2. (用户运行 cppcheck 生成 cppcheck.xml)                        # 外部步骤
3. misra-pipeline policy -- init --template misra_c2012_relaxed  # 配置策略
4. misra-pipeline oneshot -- --provider claude                   # split→run→merge
   (或分步: split → run → merge 三条命令)
5. misra-pipeline doctor                                         # 出了问题再诊断
```

**痛点**：
- 用户需要知道 `split`/`run`/`merge` 的内部流程概念
- `oneshot` 才是大多数用户真正需要的命令，但名字不直觉
- `policy init` 是必须步骤但容易忘记，忘了后 split 阶段报错
- `--` 分隔符反直觉
- 14 个命令对新用户认知负担过重
- 常用参数（`--provider`、`--strategy`）需要通过 REMAINDER 转发

## 目标用户流程（3 步）

```
1. misra-pipeline init
2. misra-pipeline policy init           # 可交互选择 template
3. misra-pipeline run --provider claude  # 自动完成 split→run→merge
```

---

## 简化方向

### 方向 1: `run` 吸收 `oneshot`，成为默认全流程命令

**现状**：`run` 仅执行 agent pipeline，`oneshot` 才是 split→run→merge。
**改动**：让 `misra-pipeline run` **默认执行全流程**（等同当前 `oneshot`），通过 `--stage` 控制单阶段执行：

```bash
misra-pipeline run                          # 全流程 (split→run→merge)，自动续跑
misra-pipeline run --fresh                  # 强制重新开始
misra-pipeline run --stage split            # 仅 split
misra-pipeline run --stage agent            # 仅 agent 执行（原 run）
misra-pipeline run --stage merge            # 仅 merge
misra-pipeline run --dry-run                # 预览 split 结果
```

**收益**：消除 `oneshot` 概念，`split`/`merge` 降为 `--stage` 选项，命令数从 14 减到约 8。

### 方向 2: 常用参数提升为 `run` 的一级选项

**现状**：`--strategy`、`--max-chunks` 等参数需要 `--` 透传到子模块。
**改动**：在 `misra-pipeline run` 的 argparse 中直接定义最常用的参数：

```bash
misra-pipeline run \
  --provider claude \           # 一级选项（已有）
  --strategy conservative \     # 一级选项（新增）
  --max-chunks 10 \             # 一级选项（新增）
  --retry 2 \                   # 一级选项（新增）
  --dry-run                     # 一级选项（新增）
```

**收益**：消除 `--` 分隔符的需要，用户不再需要知道 REMAINDER 透传机制。低频参数（`--rule-id`、`--misra-only` 等）仍可通过 `--` 透传。

### 方向 3: `policy init` 支持交互式默认值

**现状**：`policy init --template misra_c2012_relaxed` 必须显式指定 template。
**改动**：

```bash
misra-pipeline policy init                  # 交互式选择 template（列表+编号）
misra-pipeline policy init --template misra_c2012_relaxed  # 非交互式（CI/脚本）
```

同时 `run` 在发现 `rule_policy.json` 缺失时，提示一键生成：
```
Error: rule_policy.json not found.
Quick fix: misra-pipeline policy init
Or auto-create with default template: misra-pipeline run --auto-policy
```

### 方向 4: `status` 提升为顶级命令

**现状**：查询进度需要 `misra-pipeline oneshot -- --status`。
**改动**：

```bash
misra-pipeline status                       # 查询当前运行进度
```

等同 `oneshot --status` 但语义更清晰。

### 方向 5: 命令分层 — 主命令 vs 高级命令

将 `--help` 输出分为两层：

```
Primary commands:
  init         Initialize .agents/ directory
  run          Run the MISRA fix pipeline (split→agent→merge)
  status       Show pipeline run progress
  policy       Manage rule policy configuration
  doctor       Diagnose pipeline environment
  env-check    Check CLI installation

Advanced commands:
  split        Split cppcheck XML into chunks (use 'run --stage split')
  merge        Merge results into reports (use 'run --stage merge')
  verify       Verify one chunk result
  bootstrap    Generate agent compatibility files
  validate     Run provider validation test
  config       Manage CLI configuration
```

**收益**：新用户只看到 6 个核心命令，高级用户仍可直接使用单阶段命令。

### 方向 6: [oneshot.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/oneshot.py:0:0-0:0) 中的硬编码提示语更新

`@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:322` 和 349、375、389 行仍引用旧命令：

```python
print("[oneshot] 预检查未通过。请先执行 `python3 .agents/tools/pipeline_cli.py doctor`。")
```

应更新为 `misra-pipeline doctor`。（这是现有 bug，不论是否简化都应修复。）

---

## 简化后的完整命令结构

| 命令 | 功能 | 用户接触频率 |
|------|------|-------------|
| `init` | 初始化项目 | 一次 |
| `policy init` | 配置策略 | 一次 |
| `run` | 全流程/单阶段执行 | 高频 |
| `status` | 查询进度 | 高频 |
| `doctor` | 诊断环境 | 排错时 |
| `env-check` | CLI 环境检查 | 低频 |
| `config` | CLI 配置 | 低频 |
| `validate` | Provider 验收 | 低频 |

**实施优先级建议**：
1. **方向 1 + 2**（P0）：`run` 吸收 oneshot + 提升常用参数，这是最大的体验改善
2. **方向 4 + 5**（P1）：`status` 顶级命令 + 帮助分层
3. **方向 3**（P2）：policy init 交互式
4. **方向 6**（P0-bugfix）：修复 oneshot.py 中的旧命令引用
