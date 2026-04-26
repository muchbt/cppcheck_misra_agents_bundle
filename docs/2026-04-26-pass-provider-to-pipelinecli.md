
• 如果你的意思是：

  - pipeline.json 里仍保留 agent.providers.{codex|claude|opencode} 的完整配置
  - 只把 agent.provider 这个“当前选中项”拿掉
  - 改成运行时由 pipeline_cli.py --provider xxx 传入

  那我评估是 小到中等改动，不是大改，但也不止改一处。

  改动量级

  - 最小可用方案：4-6 个文件，约 80-150 行
  - 做成稳妥方案：7-10 个文件，约 150-250 行
  - 测试改动：大概 10-20 个断言点，4-6 个测试文件

  为什么不是只改 pipeline_cli.py
  当前 provider 选择不是集中在 pipeline_cli.py，而是散在公共配置读取里：

  - .agents/tools/common.py:68
  - .agents/tools/common.py:131
  - .agents/tools/agent_runner.py:50
  - .agents/tools/doctor.py:176
  - .agents/tools/oneshot.py:261

  现在很多地方默认认为 config["agent"]["provider"] 一定存在。

  最合理的实现方式
  建议不要把 provider 参数层层手工传函数，最省改动的是：

  1. 在 pipeline_cli.py 增加全局 --provider
  2. pipeline_cli 在分发子命令前设置一个环境变量，比如 PIPELINE_AGENT_PROVIDER
  3. 在 common.py 统一改：
      - get_selected_agent_provider_name()
      - get_selected_agent_config()
      - validate_pipeline_config()

  主要会改到的文件
  高概率要改：

  - .agents/tools/pipeline_cli.py:1
  - .agents/tools/common.py:68
  - .agents/tools/doctor.py:176
  - .agents/tools/oneshot.py:261
  - tests/test_pipeline_cli.py:1
  - tests/test_common_runtime.py:1
  - tests/test_doctor.py:1
  - tests/test_agent_runner.py:1

  真正的分界线
  有两个方案，改动量差很多：

  - 方案 A：仅支持 python .agents/tools/pipeline_cli.py ... --provider claude
    这是较小改动。
  - 方案 B：同时支持直接运行 python .agents/tools/run_fix_pipeline.py、doctor.py、oneshot.py 时也能传 --provider
    这是中等改动，因为每个子命令都要补参数解析和测试。

  额外风险
  如果你把 agent.provider 完全从 pipeline.json 删除，而又不保证所有入口都走 pipeline_cli，会出现两个问题：

  - 配置校验直接报错：agent.provider must be a non-empty string
  - 独立执行某些工具时不知道选哪个 provider

  所以如果要做，我建议定成下面其中一种：

  - pipeline_cli --provider 为主，但 pipeline.json 里保留默认 agent.provider 作为回退
  - 或者明确规定：所有入口必须走 pipeline_cli，并用环境变量覆盖

  我的判断：这是一个“值得做但要收好边界”的中小改动，不是重构级别。
  如果你要，我可以下一步直接给你拆成“最小实现方案”的修改清单。


› ok


• 最小实现方案我建议这样收：

  方案

  - 保留 pipeline.json 里的 agent.providers.* 全量配置。
  - agent.provider 可以继续保留为默认值，也可以逐步弱化为 fallback。
  - 新增 pipeline_cli.py --provider {codex,claude,opencode}。
  - pipeline_cli 在分发子命令前注入环境变量，例如 PIPELINE_AGENT_PROVIDER=claude。
  - common.py 统一优先读取该环境变量；未传时再回退到 pipeline.json 的 agent.provider。

  最小改动点

  1. pipeline_cli.py
      - 加全局 --provider
      - 解析后从剩余参数里剥离
      - 调子命令前设置环境变量
  2. common.py
      - 改 get_selected_agent_provider_name()
      - 改 get_selected_agent_config()
      - 放宽 validate_pipeline_config()
      - 规则建议改成：
          - agent.providers 必须存在且是对象
          - 若 CLI/env 指定了 provider，则该 provider 必须在 agent.providers 中
          - 若未指定，则回退校验 agent.provider
  3. doctor.py
      - 通过公共 helper 取 provider，基本会自动生效
      - 只需要补测试
  4. oneshot.py
      - 如果走 pipeline_cli，基本不用改业务逻辑
      - 只确认 stage 调用链能继承环境变量

  测试范围

  - tests/test_pipeline_cli.py
      - --provider 透传/注入生效
  - tests/test_common_runtime.py 或相关 common 测试
      - env override 优先于 config
      - 未传时仍回退到 config
  - tests/test_doctor.py
      - doctor 在 env override 下选对 provider
  - tests/test_agent_runner.py
      - get_selected_agent_config() 能选中对应 provider 配置

  工作量评估

  - 代码：约 80-120 行
  - 测试：约 60-120 行
  - 风险：低到中
  - 主要风险点：配置校验和直接运行子脚本时的行为一致性

  建议边界

  - 第一版只保证：
      - python3 .agents/tools/pipeline_cli.py ... --provider claude
  - 不保证第一版支持：
      - 直接执行 run_fix_pipeline.py --provider claude
      - 直接执行 doctor.py --provider claude
  - 这样改动最小，也最稳。

  如果你要，我下一步就按这个最小方案直接改。
