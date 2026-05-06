文档整体与之前讨论的 6 个简化方向高度一致。以下是逐项确认和发现的几个需要补充的点：

## 与预想一致的部分 ✅

| 方向 | 设计文档覆盖 | 状态 |
|------|-------------|------|
| `run` 吸收 `oneshot` | 第1节，含参数表、`--stage` 映射、续跑逻辑 | ✅ 完整 |
| 常用参数提升为一级选项 | 第1节参数表，12 个一级参数 | ✅ 完整 |
| `policy init` 交互式 | 第3节，TTY/非TTY/显式三种路径 | ✅ 完整 |
| `status` 顶级命令 | 第2节 | ✅ 完整 |
| 帮助分层 | 第4节，Primary 6 + Advanced 8 | ✅ 完整 |
| 修复旧引用 | 第5节，4 处行号 | ✅ 完整 |
| oneshot 保留但 deprecated | 第6节 | ✅ 完整 |
| 测试策略 | 9 个场景 | ✅ 完整 |

## 需要补充的点

### P1: `--verbose` 缺失

刚才确认 [run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 支持 `--verbose`，但第1节参数表（第57-72行）未包含。建议加入：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--verbose` | flag | False | 打印每个 chunk 完整 stdout/stderr |

### P2: 无效参数组合未约束

`--stage split --max-chunks 10` 或 `--stage merge --retry-failed 2` 时，多余参数会被静默忽略。建议在设计中注明：
- **方案A**：打印 warning（`--max-chunks ignored when --stage=split`）
- **方案B**：不校验，保持简单（建议选此，可在后续迭代加）

### P2: `misra-pipeline oneshot` 移除后的友好提示

第6节说 `oneshot` 从 `PIPELINE_COMMANDS` 移除，此时用户运行 `misra-pipeline oneshot` 会得到 argparse 的 "invalid choice" 错误。建议加一个 deprecated alias 或友好提示：

```
'oneshot' has been merged into 'run'. Use 'misra-pipeline run' instead.
```

### P3: `run --status` 与 `status` 参数互斥校验

`run --status --provider claude --max-chunks 10` 等组合无意义。建议注明 `--status` 时忽略其他所有参数（与 oneshot.py 当前行为一致，见 `@/\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py:263-265`）。

---

## 结论

**设计方案与预想一致**，方向、范围、实现策略均正确。补充上述 3 个 P1/P2 点后即可进入计划编写阶段。
