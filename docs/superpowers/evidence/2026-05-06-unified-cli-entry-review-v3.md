# 三次审核报告：统一 CLI 入口方案与计划 (v2 修订后)

## 一、上轮问题修复验证

| # | 上轮问题 | 修复状态 | 验证点 |
|---|---------|----------|--------|
| P1 | `test_dispatch_provider_sets_env` 缺 tools_dir mock | ✅ | 计划第495-500行，创建临时目录 + mock Path.cwd |
| P2 | `test_dispatch_missing_tools_dir` 链式 MagicMock | ✅ | 计划第477-480行，改用 `tempfile.TemporaryDirectory` |
| P2 | `seen_second.get("provider")` 应改严格断言 | ✅ | 计划第583行改为 `seen_second["provider"]` |
| P2 | 缺少 `import tempfile` / `MagicMock` | ✅ | 设计§10.6 + 计划第530-539行明确列出 |
| P3 | policy `--help` 体验降级 | ✅ | 设计§5.2 + 计划第253-263行添加 epilog 示例 |

**所有上轮问题均已修复。**

---

## 二、本轮发现

### 🟢 仅剩低优先级问题

#### 1. 设计 §5.1 代码片段缺少 `provider` 参数 (P3)

设计文档 §5.1 的 `_dispatch_pipeline_command` 签名（第111行）：
```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\specs\2026-05-06-unified-cli-entry-design.md:111
def _dispatch_pipeline_command(command: str, args: list[str]) -> int:
```

而 §6 单独讨论了 provider 逻辑，计划中的实际实现包含 `provider` 参数（第173行）：
```@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\plans\2026-05-06-unified-cli-entry-plan.md:173
def _dispatch_pipeline_command(command: str, args: list[str], provider: Optional[str] = None) -> int:
```

§5.1 的代码片段与 §6 描述的 provider 逻辑未合并展示。不影响实施（以计划为准），但如果有人仅读设计文档会觉得 provider 集成方式不明确。

**建议**：可选择在 §5.1 代码中加入 provider 参数，或在 §5.1 开头注明 "此处省略 --provider 处理，详见 §6"。

#### 2. `MagicMock` import 未实际使用 (P3)

计划第536行要求 `from unittest.mock import MagicMock, patch`，但所有新测试均使用 `tempfile.TemporaryDirectory` + `patch`，不再使用 `MagicMock`。导入无害但冗余。

#### 3. 设计 §5.1 的 `inserted` 局部变量 (P3)

设计第118行定义了 `inserted = tools_dir_str not in sys.path`，但仅用于控制 `sys.path.insert`，未用于后续清理。计划中的实现（第184-185行）直接用 `if` 条件，更简洁。两处风格不一致但不影响功能。

---

## 三、总结

| 优先级 | 数量 | 说明 |
|--------|------|------|
| P0 | 0 | — |
| P1 | 0 | — |
| P2 | 0 | — |
| P3 | 3 | 文档展示细节，不影响实施 |

**结论**：方案和计划已就绪，无阻塞性问题。所有 P0/P1/P2 问题在前两轮审核中已修复，剩余 3 个 P3 均为文档展示层面的瑕疵，可选修复。**批准实施。**
