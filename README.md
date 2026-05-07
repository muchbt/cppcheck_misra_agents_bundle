# cppcheck + MISRA agent pipeline

一个纯 Python 3、跨 Windows/Linux 的工程内自包含方案，用于：

- 解析 `cppcheck.xml`
- 识别普通 cppcheck 与 MISRA 结果
- 按文件聚类并切 chunk
- 调用本地 agent CLI
- 记录 issue 状态、修改点、chunk 结果、统一运行日志
- 支持按 `年月日-序号` 的 `run_id` 归档
- 支持 `run` 统一入口和默认续跑
- 通过 `.agents/` 统一管理，并自动生成兼容层

## 系统要求

- **Python 3.8+**（入口自动检查版本）
- **跨平台支持**：Windows / Linux

## 支持的 Agent Provider

| Provider | CLI 命令 | 认证方式 | 特点 |
|----------|----------|----------|------|
| **codex** | `codex exec` | `~/.codex/auth.json` | 需要 CODEX_HOME 工作区目录 |
| **claude** | `claude -p` | `claude auth login` 或 `ANTHROPIC_API_KEY` | 无需额外工作区配置 |
| **opencode** | `opencode` | OpenCode CLI 全局配置 | 自动隔离 XDG_DATA_HOME/XDG_STATE_HOME |
| **kimi** | `kimi --print` | `KIMI_API_KEY` 或 `~/.kimi/credentials/` | 自动隔离 KIMI_SHARE_DIR |

切换 provider 只需修改 `.agents/config/pipeline.json` 中的 `agent.provider` 字段，或通过 CLI 参数覆盖：

```bash
misra-pipeline run --provider kimi
```

## CLI 命令

唯一入口：`misra-pipeline`（开发模式下：`python3 cli/misra-pipeline-cli.py`）

| 命令 | 功能 |
|------|------|
| `run` | 执行 split → agent → merge，支持自动续跑 |
| `oneshot` | 已废弃，使用 `run` 代替 |
| `split` | 解析 cppcheck.xml，按策略切分 chunk |
| `merge` | 合并结果，生成中文报告和归档 |
| `status` | 显示当前运行进度 |
| `doctor` | 运行环境诊断检查 |
| `bootstrap` | 生成 agent 兼容层（AGENTS.md、SKILL.md） |
| `verify` | 验证单个 chunk 结果 |
| `validate` | provider 验证测试 |
| `policy` | 策略模板管理（list/init/test/add） |

## 目录结构

- `.agents/config/*.json`：配置
- `.agents/config/templates/*.json`：策略模板
- `.agents/prompts/*.txt`：prompt 模板
- `.agents/skills/*`：主 skill 源
- `.agents/tools/*.py`：工具脚本（仅通过 misra-pipeline CLI 调用）
- `.agents/runtime/*`：当前运行态、chunk、结果、日志
- `.agents/reports/*`：当前运行的中文报告
- `.agents/runs/<run_id>/*`：历史归档

## 策略模板

### 模板列表

| 模板文件 | 适用场景 | 特点 |
|----------|----------|------|
| `misra_c2012_conservative.json` | 保守 MISRA C:2012 | 所有 MISRA 规则标记为 `needs_manual_review` |
| `misra_c2012_relaxed.json` | 放宽 MISRA C:2012 | 低风险 `auto_fix`，中风险 `careful_fix`，高风险 `needs_manual_review` |
| `cppcheck_common.json` | 通用 cppcheck | 常见 cppcheck error/warning 策略 |
| `autosar_baseline.json` | AUTOSAR 基线 | RTE/MCAL/BSW 组件强制人工复核 |

### 使用模板

```bash
# 查看可用模板
misra-pipeline policy list

# 从单个模板初始化策略文件
misra-pipeline policy init misra_c2012_relaxed

# 从多个模板初始化（合并，后面的覆盖前面的冲突规则）
misra-pipeline policy init --template misra_c2012_relaxed --template cppcheck_common

# 测试规则匹配
misra-pipeline policy test misra-c2012-2.2

# 添加自定义规则
misra-pipeline policy add misra-c2012-8.1 --action auto_fix --risk-level low
```

### 多模板合并规则

`--template` 可多次指定，合并时遵循以下规则：

| 情况 | 处理方式 |
|------|----------|
| **规则冲突** | 后面的模板覆盖前面的（按 `--template` 顺序，后胜） |
| **规则不冲突** | 全部保留（取并集） |
| **pattern 冲突** | 按 `match_contains` 去重，后面的不覆盖已有的 |
| **default** | 采用第一个有 default 的模板 |

**合并后果示例：**

假设模板 A 定义 `misra-c2012-2.2 → auto_fix`，模板 B 定义 `misra-c2012-2.2 → needs_manual_review`：

```bash
misra-pipeline policy init --template misra_c2012_relaxed --template misra_c2012_conservative
```

结果：`misra-c2012-2.2` 动作取决于顺序：
- `--template A --template B` → `needs_manual_review`（B 覆盖 A）
- `--template B --template A` → `auto_fix`（A 覆盖 B）

**常用合并组合：**

| 组合 | 效果 |
|------|------|
| `misra_c2012_relaxed + cppcheck_common` | MISRA 规则 + 通用 cppcheck 规则合并 |
| `misra_c2012_conservative + cppcheck_common` | 保守 MISRA + 通用 cppcheck（cppcheck 规则在保守基础上增加） |
| `autosar_baseline + cppcheck_common` | AUTOSAR 架构保护 + 通用 cppcheck 规则 |

### 模板详解

#### misra_c2012_conservative.json

最保守策略，覆盖 MISRA C:2012 全部 143 条规则（Directive 1-4 + Rule 1-22）。

- **默认动作**：所有规则 `needs_manual_review`
- **风险等级**：全部 `high`
- **特殊模式**：`volatile` / `interrupt` / `register` / `rte_` / `mcal` / `bsw` 关键字强制人工复核

适用场景：安全关键系统、首次接入、对自动修复持保守态度的项目。

#### misra_c2012_relaxed.json

放宽策略，根据规则实际风险分级：

| 动作 | 含义 | 典型规则 |
|------|------|----------|
| `auto_fix` | 高置信度自动修复 | 2.2/2.3（死代码）、2.7（未用参数）、7.2（常量后缀）、8.11（const）、15.6/15.7（块结构）、20.7（宏参数括号） |
| `careful_fix` | 需验证后修复 | 5.1-5.5（标识符）、8.3-8.10（类型定义）、10.1/10.3（类型转换）、16.1/16.3（switch） |
| `needs_manual_review` | 必须人工复核 | 9.1（未初始化）、11.1/11.2（函数指针转换）、17.1/17.2（指针使用）、21.3/21.4（内存分配）、全部 Directive |

适用场景：有一定 MISRA 经验、希望减少人工复核负担、但仍保留高风险路径保护。

#### cppcheck_common.json

通用 cppcheck 策略：

| 动作 | 典型错误类型 |
|------|--------------|
| `auto_fix` | unusedVariable、constVariable |
| `careful_fix` | unreadVariable、uninitStructMember、memoryLeak、resourceLeak |
| `needs_manual_review` | uninitvar、nullPointer、bufferAccessOutOfBounds、arrayIndexOutOfBounds、doubleFree |

特殊模式：`volatile` / `interrupt` / `register` / `malloc` / `strcpy` / `sprintf` 关键字强制人工复核。

#### autosar_baseline.json

AUTOSAR 架构专用策略，覆盖 RTE/MCAL/BSW 关键路径：

- **默认动作**：全部 `needs_manual_review`
- **特殊模式**（强制人工复核）：
  - `rte_` / `Rte_` / `RTE_`：AUTOSAR RTE 路径
  - `mcal` / `MCAL`：微控制器抽象层
  - `bsw` / `BSW`：基础软件层
  - `canif` / `CanIf` / `com` / `dem` / `det` / `ecu` / `schm` / `os`：AUTOSAR 模块
  - `volatile` / `interrupt` / `ISR` / `register` / `config`：硬件相关

适用场景：AUTOSAR 项目、需要保护架构层接口的项目。

### 策略动作说明

| 动作 | 含义 | 风险等级 |
|------|------|----------|
| `auto_fix` | agent 可自动修复，无需人工确认 | low |
| `careful_fix` | agent 可修复，但需验证结果 | medium |
| `needs_manual_review` | 必须人工复核，agent 不自动修复 | high |
| `skip` | 跳过该问题 | - |

## 修复模式（fix_patterns）

`fix_patterns.json` 为每条规则提供规范化修复指导，在 chunk 切分时按风险等级动态注入，约束 agent 修复行为。

### 数据来源

| 文件 | 作用 |
|------|------|
| `.agents/config/fix_patterns.json` | 规则 → 修复模式映射（183 条，覆盖全部 cppcheck + MISRA C:2012 规则） |
| `.agents/config/rule_policy.json` | 规则 → 动作/风险等级映射（单一来源，fix_patterns 不含 `risk_level`） |

### 工作原理

```
split_cppcheck_xml.py
  │
  ├── 加载 rule_policy.json → classify_issue() → 确定 risk_level
  ├── 加载 fix_patterns.json → lookup_fix_pattern(rule_id, risk_level)
  │
  └── chunk 切分时：按 rule_id 去重 → unique_fix_patterns 写入 chunk JSON
```

`lookup_fix_pattern()` 根据规则的 `risk_level` 过滤字段：

| risk_level | 注入字段 |
|------------|----------|
| `low` | `fix`, `example` |
| `medium` | `fix`, `example`, `caution` |
| `high` | `fix`, `example`, `pitfalls`, `context_notes` |

### chunk JSON 结构变化

每个 chunk JSON 新增 `unique_fix_patterns` 字段：

```json
{
  "chunk_index": 1,
  "unique_fix_patterns": {
    "nullPointer": {
      "fix": "Add NULL guard before the first dereference.",
      "example": "if (ptr == NULL) { return ERR_NULL; } /* fix: nullPointer — added NULL guard */",
      "pitfalls": "Adding a NULL guard changes control flow. ...",
      "context_notes": "In safety-critical code, prefer returning an explicit error code ..."
    }
  },
  "issues": [...]
}
```

### prompt 指导

chunk prompt 模板（`.agents/prompts/fix_chunk_prompt.txt`）新增：

> For each issue whose rule_id appears in unique_fix_patterns, you MUST use the exact fix approach described there. Do NOT invent alternative fix methods when a pattern is provided.

### 容错

- `fix_patterns.json` 缺失时，`load_json()` 返回 `{}`，所有 `lookup_fix_pattern()` 返回 `None`，chunk JSON 中 `unique_fix_patterns` 为空字典 — 不影响正常流程
- 规则未在 `fix_patterns.json` 中出现时，该规则不会有修复模式条目

## 推荐用法

首次接入、环境异常、命令失败时，先运行：

```bash
misra-pipeline doctor
```

日常使用推荐直接运行：

```bash
misra-pipeline run
```

`run` 会自动完成：

1. 预检查（doctor）
2. `split`（解析 XML、切 chunk）
3. `run`（执行 agent 修复）
4. `merge`（生成报告、归档）

如果检测到已有未完成运行，`run` 会默认续跑。

## fresh 与续跑

默认情况下，只要 `.agents/runtime/progress.json` 的状态是 `ready`、`running`、`partial` 或 `failed`，`run` 就会续跑。

强制从头开始：

```bash
misra-pipeline run --fresh
```

指定策略或 run_id：

```bash
misra-pipeline run --fresh --strategy all_auto --run-id 20260423-001
```

## 分步命令

需要拆开执行时：

```bash
misra-pipeline split --strategy conservative
misra-pipeline run --strategy conservative
misra-pipeline merge
```

Windows 下：

```bat
misra-pipeline doctor
misra-pipeline run
```

## 修复策略（fix_strategy）

默认策略是 `conservative`：

- 只自动修复高置信度、局部可判定的问题
- 高风险 MISRA / volatile / interrupt / register / RTE / MCAL 等问题标记为 `needs_manual_review`

使用 `all_auto` 让 agent 尝试修复更多问题：

```bash
misra-pipeline run --fresh --strategy all_auto
```

`all_auto` 会把高风险问题也分发给 agent，但结果必须保留 `risk_level`、`risk_reason` 和 `review_required_after_fix=true`。

此维度的详细说明及与规则策略的联动关系，参见下节「策略模板与修复策略的联动」。

## 策略模板与修复策略的联动

本方案有两层策略控制：

| 维度 | 配置位置 | 选项 | 作用 |
|------|----------|------|------|
| **规则策略（rule_policy）** | `.agents/config/rule_policy.json` | 模板初始化：`misra_c2012_conservative` / `misra_c2012_relaxed` / `cppcheck_common` / `autosar_baseline` | 定义每条规则在**任意模式**下的默认动作 |
| **修复策略（fix_strategy）** | `pipeline.json` → CLI `--strategy` | `conservative`（默认）或 `all_auto` | 控制 `needs_manual_review` 规则是否被降级 |

### 联动工作原理

```
rule_policy.json（规则动作）      +      fix_strategy（运行模式）
──────────────────────────────────────┼─────────────────────────────
auto_fix                            →     直接修复
careful_fix                          →     修复但需验证结果
needs_manual_review  + conservative →     跳过，标记人工复核
needs_manual_review  + all_auto     →     降级为 careful_fix，但仍标记 requires_review_after_fix
```

### 完整工作流示例

假设使用 `misra_c2012_relaxed.json` 模板 + `all_auto` 策略：

```bash
# 1. 从模板初始化规则策略
misra-pipeline policy init misra_c2012_relaxed

# 2. 使用 all_auto 模式运行
misra-pipeline run --fresh --strategy all_auto
```

执行时：
- 规则 `misra-c2012-2.2`（action: `auto_fix`）→ agent 直接修复
- 规则 `misra-c2012-10.1`（action: `careful_fix`）→ agent 修复但需验证
- 规则 `misra-c2012-9.1`（action: `needs_manual_review`）→ 在 `all_auto` 下降级为 `careful_fix`，但 `requires_review_after_fix=true` 标记

### 一键切换模板 + 策略

组合使用模板初始化和运行策略：

```bash
# 保守模式：保守模板 + conservative（最严格）
misra-pipeline policy init misra_c2012_conservative
misra-pipeline run --fresh --strategy conservative

# 放宽模式：宽松模板 + all_auto（最大修复范围）
misra-pipeline policy init misra_c2012_relaxed
misra-pipeline run --fresh --strategy all_auto

# AUTOSAR 模式：AUTOSAR 模板 + conservative（保护架构层）
misra-pipeline policy init autosar_baseline
misra-pipeline run --fresh --strategy conservative
```

### 配置来源说明

- `pipeline.json` 中的 `fix_strategy.mode` 决定默认运行模式
- CLI 的 `--strategy` 参数覆盖 `pipeline.json` 的默认模式
- `rule_policy.json` 由用户通过 `policy init` 管理，默认为空（需要手动初始化）

## 运行日志

当前运行的日志位于：

- `.agents/runtime/pipeline.log`：适合人工快速阅读
- `.agents/runtime/run_log.jsonl`：适合脚本消费

## 中文报告

每次 `merge` 会生成：

- `.agents/reports/final_summary.md`：运行总结（简体中文）
- `.agents/reports/final_summary.json`：JSON 格式总结
- `.agents/reports/review_checklist.md`：人工复核清单
- `.agents/reports/run_manifest.json`：运行元数据

## 归档

每次 `merge` 后，当前运行会复制到 `.agents/runs/<run_id>/`，包含：

- `runtime/`：运行态 JSON、chunk、结果
- `reports/`：中文总结、复核清单、manifest
- `logs/`：pipeline.log 与 run_log.jsonl

## bootstrap_agents.py

同步兼容层：

```bash
misra-pipeline bootstrap --mode merge
```

模式说明：

- `--mode merge`：默认；标记块替换/追加 AGENTS.md，覆盖 SKILL.md
- `--mode overwrite`：重建兼容层
- `--dry-run`：预览变更，不写盘

## 兼容层说明

`.agents/` 是主目录。兼容层包括：

- 项目根目录 `AGENTS.md`
- `.codex/skills/cppcheck-misra-fix/SKILL.md`
- `.claude/skills/cppcheck-misra-fix/SKILL.md`

## 注意

- 本方案默认只自动修复高置信度、局部可判定的问题
- 高风险路径默认标记为 `needs_manual_review`
- 涉及环境异常、命令缺失、输入文件问题时，先运行 `doctor`
- Python 低于 3.8 时，入口会直接报错退出

## CLI 安装与使用

### Linux 安装

```bash
curl -sSL https://raw.githubusercontent.com/muchbt/cppcheck_misra_agents_bundle/refs/heads/main/install.sh | bash
```

指定版本：

```bash
curl -sSL https://raw.githubusercontent.com/muchbt/cppcheck_misra_agents_bundle/refs/heads/main/install.sh | bash -s -- --version v1.2.3
```

指定自定义仓库：

```bash
curl -sSL https://raw.githubusercontent.com/muchbt/cppcheck_misra_agents_bundle/refs/heads/main/install.sh | bash -s -- --repo-url https://gitlab.company.com/tools/misra-pipeline
```

### Windows 安装

下载 `install.bat` 并运行：

```batch
install.bat
```

指定版本：

```batch
install.bat --version v1.2.3
```

指定自定义仓库：

```batch
install.bat --repo-url https://gitlab.company.com/tools/misra-pipeline
```

### 使用环境变量安装

如果不想通过命令行参数，也可以通过环境变量指定：

```bash
# Linux/macOS
export MISRA_PIPELINE_REPO_URL=https://gitlab.company.com/tools/misra-pipeline
export MISRA_PIPELINE_DOWNLOAD_URL=https://my-server.com/agents-v1.2.3.tar.gz
curl -sSL https://raw.githubusercontent.com/muchbt/cppcheck_misra_agents_bundle/refs/heads/main/install.sh | bash

# Windows
set MISRA_PIPELINE_REPO_URL=https://gitlab.company.com/tools/misra-pipeline
set MISRA_PIPELINE_DOWNLOAD_URL=https://my-server.com/agents-v1.2.3.tar.gz
install.bat
```

### CLI 命令

| 命令 | 说明 |
|------|------|
| `misra-pipeline init` | 在当前项目初始化 `.agents/` 目录 |
| `misra-pipeline init --force` | 强制覆盖已存在的 `.agents/` |
| `misra-pipeline init --version vX.Y.Z` | 安装指定版本 |
| `misra-pipeline init --source release` | 从 Release 下载（默认） |
| `misra-pipeline init --source git_archive` | 使用 git archive 下载 |
| `misra-pipeline init --source direct --url <url>` | 从指定 URL 下载 |
| `misra-pipeline init --source local --url <path>` | 从本地路径复制 |
| `misra-pipeline upgrade` | 升级到最新版本 |
| `misra-pipeline upgrade --version vX.Y.Z` | 升级到指定版本 |
| `misra-pipeline version` | 显示 CLI 和项目版本 |
| `misra-pipeline doctor` | 检查安装状态和依赖环境 |
| `misra-pipeline config show` | 显示当前下载源配置 |
| `misra-pipeline config set mode <mode>` | 设置默认下载模式 |
| `misra-pipeline config set repo_url <url>` | 设置仓库 URL |
| `misra-pipeline config set url_template <tpl>` | 设置 URL 模板 |
| `misra-pipeline config reset --yes` | 重置为默认配置 |

### 配置自定义分发源

CLI 支持从多种来源下载 `.agents/` 内容，不仅限于 GitHub Release。配置存储在 `~/.misra-pipeline/config.json`。

**默认配置：**

```json
{
  "repo_url": "https://github.com/muchbt/cppcheck_misra_agents_bundle",
  "download": {
    "mode": "release",
    "url_template": "{repo_url}/releases/download/{version}/agents-{version}.tar.gz",
    "fallback_mode": "git_archive"
  }
}
```

**支持的下载模式：**

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `release` | 从 Release 下载预打包 tar.gz | **默认**，GitHub/GitLab Release |
| `git_archive` | 使用 `git archive` 从仓库提取 | 开发测试、无 Release 时回退 |
| `direct` | 直接下载指定 URL | 任意 HTTP 服务器 |
| `local` | 从本地目录或 tar.gz 复制 | 内网离线环境 |

**企业内部 GitLab 示例：**

```bash
# 安装时指定
./install.sh --repo-url https://gitlab.company.com/tools/misra-pipeline

# 或在安装后修改配置
misra-pipeline config set repo_url https://gitlab.company.com/tools/misra-pipeline
misra-pipeline config set url_template "https://gitlab.company.com/tools/misra-pipeline/-/releases/download/{version}/agents-{version}.tar.gz"
```

**离线/本地文件示例：**

```bash
misra-pipeline init --source local --url /mnt/usb/agents-v1.0.0.tar.gz
```

**任意 HTTP 服务器示例：**

```bash
misra-pipeline init --source direct --url https://artifacts.company.com/misra/agents-latest.tar.gz
```

### 版本管理

初始化后，项目 `.agents/` 目录下会生成 `.agents-version` 文件，记录安装版本和 commit hash。

升级时：
- `tools/` 和 `config/templates/` 被覆盖更新
- `config/pipeline.json` 和 `config/rule_policy.json` 被保留
- 如检测到本地修改（与安装版本不一致），升级会报错提示手动处理

### 系统要求

- Python 3.8+
- Git（用于 `git_archive` 回退模式，Release 下载无需）
- Linux 或 Windows

## Release 打包

项目根目录提供 `Makefile` 用于自动打包 Release 归档。

### 查看可用目标

```bash
make help
```

### 打包 Release

```bash
# 1. 确保版本号正确（修改 cli/VERSION）
cat cli/VERSION

# 2. 运行测试并打包
make release
```

`make release` 会：
1. 运行全部测试
2. 读取 `cli/VERSION` 作为版本号
3. 打包为 `dist/agents-v{VERSION}.tar.gz`

打包内容包括：
- `cli/` — CLI 入口和版本文件
- `.agents/config/` — 配置和策略模板
- `.agents/compat/` — 兼容层
- `.agents/prompts/` — Prompt 模板
- `.agents/skills/` — Skill 文件
- `.agents/tools/` — 工具脚本
- `README.md`, `AGENTS.md` — 文档
- `install.sh`, `install.bat` — 安装脚本

排除内容：
- `__pycache__`, `.pytest_cache`
- `.agents/runs/`, `.agents/staging/`, `.agents/runtime/`, `.agents/reports/`

### 创建并推送 Tag

```bash
# 创建 git tag（基于 cli/VERSION）
make tag

# 或手动操作
git tag v0.1.0
git push origin v0.1.0
```

### 发布到 GitHub/GitLab

1. 在 GitHub/GitLab 上创建 Release
2. 上传 `dist/agents-v{VERSION}.tar.gz` 到 Release Assets
3. 用户即可通过 `misra-pipeline init` 自动下载该版本

### 清理打包产物

```bash
make clean
```
