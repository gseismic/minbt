# PLAN-025 examples-logger-cleanup 结果

## 已完成

1. 移除所有 examples 中的 `QuietLogger` 定义、导入和使用。
2. 移除所有示例的 `run_strategy(quiet=True)` 参数，示例入口只保留回测主路径。
3. `Exchange()` 和 `Broker(...)` 在示例中不再显式传入 logger。
4. `examples/example_utils.py` 只保留高级示例需要的目标名义金额调仓和平仓辅助函数。
5. `examples/04_scenario_exit_rules.py` 和 `examples/05_scenario_limit_order.py` 补回最小项目根路径引导，避免直接运行时误导入本机旧版 `minbt`。
6. README 删除“静默 logger”描述，避免把 logger 作为示例关注点。

## 设计判断

`QuietLogger` 只是压制示例运行日志的辅助实体，不属于 minbt 的核心用户接口。示例应优先展示：

1. 准备数据。
2. `Exchange.set_bars(...)` 接入行情。
3. 在 `Strategy.on_bars(dt, bars)` 中读取同一时间截面数据。
4. 调用 `self.broker` 交易。

因此移除 logger 实体符合“最简回测系统”的目标。

## 验证

```text
pytest -q tests/test_examples.py
8 passed

python -m compileall -q examples
通过

pytest -q
123 passed

python -m compileall -q minbt tests examples
通过

git diff --check
通过
```

## 结论

示例中的 logger 概念已清理。当前 examples 仍按编号从最小示例、单标的、多标的到退出条件、限价单和高级真实场景逐步展开。
