# 前三期缺口收敛设计（草案）

## 背景

本草案按范围 2 收敛：以前三期计划为主，同时把当前代码中已暴露出来的红测和配置回归一并纳入，但不扩散到无关重构。

当前仓库已经完成了大部分一期、二期和文档修复工作，但现状出现了一个新的收敛点：`opencode` provider 文件已经存在，`pipeline.json` 的选中 provider 也被切换成了 `opencode`，但对应配置、诊断、测试隔离和运行时路径处理还没有一起补齐，导致当前 provider 体系处于“部分切换”的不一致状态。

## 现状结论

基于当前代码和红测，主要缺口集中在以下几类：

1. 配置层不一致
   - `agent.provider` 当前为 `opencode`，但 `agent.providers` 中没有 `opencode` 配置块。
   - `validate_pipeline_config()` 会按“已选 provider”读取 launch/capabilities，导致整体验证失败。

2. 测试隔离不足
   - 多个 `codex` / `doctor` 测试直接复用仓库默认配置，没有在测试内显式切换 provider。
   - 一旦默认 provider 改成 `opencode`，这些测试会因为选中 provider 漂移而失真。

3. 运行时路径解析不稳
   - `agent_runner.py` 的 `resolve_env_path()`、`build_launch_env()`、`resolve_cwd()` 三个函数仍绑定模块级 `ROOT`。
   - 测试通过 patch `agent_runner.ROOT` 注入临时根目录时，部分路径仍可能落回真实仓库，触发只读 staging 路径错误。
   - `spawn_error` 场景的单测当前会误用真实仓库 staging 路径，而不是临时目录。

4. `opencode` 三期未闭环
   - `providers/opencode.py` 已创建，但错误分类、环境目录隔离、配置示例、`doctor` 特定诊断、README 说明还未形成完整闭环。
   - 当前 `doctor` 对非 `codex` / `claude` provider 基本走“不适用”分支，无法支撑 phase 3 计划目标。

## 方案对比

### 方案 A：回退默认 provider 到 `codex`，仅修红测

优点：
- 改动最小，能最快恢复当前测试面。
- 对现有 `codex` 使用者风险最低。

缺点：
- 实际上绕开了 phase 3 的 `opencode` 收尾。
- 只是把不一致藏起来，没有完成配置、诊断、文档闭环。

### 方案 B：补齐 `opencode` 配置与诊断，同时修复测试隔离

优点：
- 能把前三期剩余缺口与当前回归一次性收拢。
- 保持现有 provider 抽象不变，符合“最小改动”原则。
- 修完后默认 provider 是 `opencode` 还是 `codex` 都不会再导致测试整体漂移。

缺点：
- 需要同时改配置、测试、`doctor`、README。
- 需要明确 `opencode` 的认证/网络检查边界，不能简单照搬 `codex`。

### 方案 C：顺手重构 provider 选择模型

方向：
- 重新定义“默认 provider”“选中 provider”“回退 launch”的关系。
- 把 `doctor` 和 `agent_runner` 进一步抽象成完全 provider 插件化。

优点：
- 从长期看更整洁。

缺点：
- 超出本次“补全测试、配置缺失项”的范围。
- 容易把问题从“缺口补齐”演化成“架构重做”。

## 推荐

推荐采用方案 B。

理由很直接：当前问题不是 provider 设计彻底错误，而是 `opencode` 三期只完成了“文件存在”和“部分切换”，没有把配置、诊断、测试夹具一起收口。此时最合理的动作是把不一致补齐，而不是回退逃避，或借机做额外抽象。

## 设计

### 1. 配置与选择语义

维持现有 `agent.provider + agent.providers.<name>` 模型，不新增新的抽象层。

要点：
- 在 `.agents/config/pipeline.json` 中补全 `agent.providers.opencode`。
- `opencode.launch` 至少包含：
  - `argv: ["opencode"]`
  - `prompt_via: "stdin"` 或 `"arg"`，以当前 runner/doctor 共同支持的非交互方式为准
  - `cwd: "project_root"`
  - `env: {}`
  - `requires_tty: false`
  - `output.mode: "exit_code"`
- `capabilities` 与其他 provider 对齐，先保持：
  - `non_interactive: true`
  - `workspace_write_required: true`

这一节的目标不是重新设计配置，而是让“当前选中的 provider 在配置上真实可运行、可诊断、可验证”。

### 2. 测试边界

所有 provider 相关测试都不再隐式依赖仓库默认 provider。

做法：
- `tests/test_agent_runner.py`
  - `codex` 用例显式设置 `config["agent"]["provider"] = "codex"`。
  - `claude` 用例显式设置 `config["agent"]["provider"] = "claude"`。
  - `opencode` 用例补到“真实选中 provider”的粒度，而不是只测 import。
- `tests/test_doctor.py`
  - `codex`、`claude`、`opencode` 诊断各自构造最小配置。
  - 不再让“仓库当前默认 provider 是谁”决定断言结果。

这样可以把“默认配置变更”与“测试意图”解耦，避免后续继续出现整片误报。

### 3. `agent_runner` 路径与 staging 处理

`agent_runner` 继续维持通用执行层，但所有相对路径解析都必须以“当前调用上下文的 root”一致收口。

要点：
- `build_launch_env()` 解析 env 中的相对路径时，不应偷偷回落到模块初始化时的 `ROOT`。
- `resolve_cwd()` 解析 `project_root` / `runtime_dir` / `custom` 时，也应和当前 root 注入一致。
- staging 目录准备逻辑要保证：
  - 单测 patch 了临时 root 时，只操作临时目录。
  - spawn error 用例不会先碰真实仓库里的 staging。

本节只修“路径一致性”和“可测性”，不改 runner 的主职责。

### 4. `doctor` 的 `opencode` 诊断范围

`doctor` 对 `opencode` 至少补齐以下检查：

- 启动入口检查
  - `argv[0]` 是否存在。
  - 启动前缀是否符合 `opencode` 的非交互约束。

- 数据/状态目录策略说明
  - 运行时会注入 `XDG_DATA_HOME=.opencode/data`
  - 运行时会注入 `XDG_STATE_HOME=.opencode/state`
  - `doctor` 需要对这两个工作区目录做可写性检查。

- 认证检查
  - 不伪造“已认证”。
  - 给出“依赖 OpenCode CLI 全局认证状态，当前仅能做有限提示”的结果级别和文案。

- 网络检查
  - 对 `zen/v1/messages`、`ConnectionRefused`、timeout 一类错误给出 `network_error` 分类和文档说明。

这里的关键原则是：对 `opencode` 只做当前代码能可靠判断的检查，不凭空宣称认证已通过。

### 5. 文档收口

README 和 phase 3 计划文档按实现后的真实行为更新。

重点补充：
- `opencode` 的结构化配置示例。
- `XDG_DATA_HOME` / `XDG_STATE_HOME` 工作区隔离策略。
- 认证依赖 OpenCode CLI 全局状态，doctor 只能给有限提示。
- 常见网络失败的归类口径。

## 测试与验证设计

本轮只做针对性验证，不做无差别全量。

建议验证集：

1. `python3 -m unittest tests.test_agent_runner -v`
2. `python3 -m unittest tests.test_doctor -v`
3. 如 README 有改动，只做相关断言和人工复核，不追加无关测试

如 `opencode` provider 的真实 CLI 行为需要验收，可单独作为后续一步，不与本轮单元补缺绑定。

## 范围外

本轮不做以下事项：

- 不重构 provider 总体架构。
- 不引入“执行器 provider / 模型 provider”双层模型。
- 不补与前三期计划无关的新功能。
- 不顺手清理 `.agents/runtime/` 之外的历史杂项文件。

## 暂停前实施计划草案

1. 修正 `.agents/config/pipeline.json`
   - 补齐 `agent.providers.opencode`
   - 明确默认 provider 保持现状或回退到 `codex` 的最终选择标准

2. 修正配置读取与测试夹具
   - 确保 `validate_pipeline_config()` 在选中 provider 下通过
   - 让 provider/doctor 测试显式指定自己的 provider

3. 修正 `agent_runner` 根目录一致性
   - 统一 env、cwd、staging 的相对路径解析
   - 消除单测误触真实仓库 staging 的问题

4. 补齐 `opencode` provider 与 `doctor` 诊断
   - 完善错误分类
   - 增加数据目录、状态目录、认证、网络提示的测试与实现

5. 收口 README 与 phase 3 文档
   - 只按真实实现更新说明

6. 跑定向验证
   - `tests.test_agent_runner`
   - `tests.test_doctor`

## 待确认

待你回来后，优先确认两点：

1. 默认 provider 最终是否继续保留为 `opencode`
2. 本轮是否接受把 phase 3 文档一起同步为“当前真实状态”

在你确认前，先停在设计阶段，不进入实施计划细化和代码改动。
