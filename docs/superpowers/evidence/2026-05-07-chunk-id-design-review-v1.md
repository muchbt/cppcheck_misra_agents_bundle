




# 审核结果：⚠️ 仅有规格文档，代码尚未落地

## 已确认

- **规格文档**：`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\docs\superpowers\specs\2026-05-07-chunk-id-design.md` 已写入，内容覆盖目标、设计、行为示例、兼容性与测试策略，**与上文方案一致**。

## 未实现的代码改动

三个文件均**没有 `--chunk-id` 相关代码**：

- `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py` — [parse_args](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/cli/misra-pipeline-cli.py:137:0-275:17) 仍是 7 个参数（`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py:107-151`），无 `--chunk-id`；无 `parse_chunk_id_specs`；[next_chunk](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:190:0-203:15) 签名未扩展（`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py:191`）；[main()](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:225:0-441:42) 未集成。
- `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\oneshot.py` — `build_run_args` 未追加转发逻辑（grep 仅命中无关的 `chunk_idx`）。
- `@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\cli\misra-pipeline-cli.py` — `run_parser` 无 `--chunk-id` 定义。

## 顺带发现（非 chunk-id 相关）

[run_fix_pipeline.py](cci:7://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:0:0-0:0) 的失败处理已被改成"失败后 `continue` 继续下一个 chunk"，原本是 `return 1` 退出（`@\\wsl.localhost\Ubuntu-22.04\home\ubuntu\code\cppcheck_misra_agents_bundle_v2\.agents\tools\run_fix_pipeline.py:407-438`）。这是行为变更，但不在本次 spec 范围内——若是有意改动建议另起 spec/PR；若是无意改动需注意它会让 `--max-chunks` 和退出码语义都发生变化。

## 建议下一步

请确认是否：

# Spec 审核结论

## ✅ 通过项

- **目标与背景**清晰，回答了"为什么需要"。
- **改动范围**精确锁定 3 个文件，均为追加式，符合"最小修改"。
- **参数语法**完整覆盖单值/范围/重复/反序四种形态，且明确 `action="append"` 默认 `[]`。
- **`parse_chunk_id_specs` 契约**输入输出和错误处理（无效格式、越界、去重、排序）描述完整。
- **[next_chunk](cci:1://file://wsl.localhost/Ubuntu-22.04/home/ubuntu/code/cppcheck_misra_agents_bundle_v2/.agents/tools/run_fix_pipeline.py:190:0-203:15) 改动**保持向后兼容（`requested_ids=None` 走原路径）。
- **行为示例**表覆盖正常、错误、边界、回归 7 种情况。
- **兼容性章节**显式声明 progress.json schema 不变。
- **测试策略**分单元/集成/回归/CLI 四层，粒度合适。

## ⚠️ 建议补强

1. **`status` 状态语义**：spec §4 第 5 条说"有 `requested_ids` 时 `status` 保持 `running`"，但若用户只指定 chunk 5、跑完后既不是 `done` 也不是 `failed`，会让 `merge` 阶段或后续 `--resume` 判断歧义。建议明确：跑完所有 `requested_ids` 后 `status` 设为 `partial`（与现有 `--max-chunks` 截断时的语义复用），避免新增状态值。

2. **`--chunk-id` 与 `--max-chunks` 的优先级**未提：例如 `--chunk-id 1-10 --max-chunks 3` 应处理前 3 个还是报错？建议补一条："`--max-chunks` 在 `--chunk-id` 候选集合上独立生效，先到先停"。

3. **与 `--include-failed` 的交互**：当用户显式 `--chunk-id 5` 而 chunk 5 在 `failed_chunks` 里，是否需要 `--include-failed` 才能跑？spec §3 写"其余过滤逻辑不变"——意味着默认会被跳过且**没有任何输出**，用户体验差。建议：**显式指定的 chunk-id 命中 failed 时**，输出一条提示 `chunk N 之前失败，使用 --include-failed 重跑`，避免静默跳过。

4. **`oneshot` 全流模式的语义**：行为表第 5 行"先 split 再仅跑 chunk 5 再 merge"——但 split 后产生的 `total_chunks` 用户事先不知道，写 `--chunk-id 5` 可能越界。spec 没说在 `oneshot` 模式下越界是中止还是继续到 merge。建议明确：`oneshot` 模式下若 `requested_ids` 解析后为空，**不进入 merge**（避免合并空结果），直接以非零码或警告退出。

5. **事件日志**：`--chunk-id` 这类用户筛选条件建议在 `run_started` 事件 `data.filters` 里也带上，便于 `runs/<run_id>/events.jsonl` 回溯。spec §4 第 6 条已写入 `last_run_filters`，但**未提及事件**——补一句即可。

6. **测试策略缺一项**：建议增加"指定的 chunk-id 已 completed"的回归——验证不会重复执行已完成 chunk（除非加一个未来的 `--force` 参数）。

## 小修订建议（可选）

- §2 函数签名 `tuple` 写成 `Tuple[List[int], List[str]]` 更利于静态检查。
- 行为表"未传 `--chunk-id`"放第一行作为基线对照更直观。

## 总结

Spec 整体设计**正确、最小、向后兼容**，可以作为实现依据。落地前建议把上述 1–4 条歧义点写进 spec 的"边界行为"小节，避免实现期再回头补丁。第 5–6 条是 nice-to-have。
