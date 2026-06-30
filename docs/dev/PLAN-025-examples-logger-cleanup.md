# PLAN-025 examples-logger-cleanup

## 背景

当前 examples 中为了让输出更安静，定义并传入了 `QuietLogger`。这会让入门示例多出一个非核心概念，和 minbt “方便快捷、重心是策略和 broker 下单”的目标不一致。

## 目标

1. 移除 examples 中的 `QuietLogger` 定义和导入。
2. 移除示例 `run_strategy(quiet=True)` 这类非核心参数。
3. 示例只保留数据构造、`Exchange.set_bars()`、策略回调和 `broker` 交易主路径。
4. 更新 README 当前示例说明。

## 实施

1. 清理 `examples/01_demo_mini.py` 至 `examples/08_scenario_pairs_mean_reversion.py`。
2. 清理 `examples/example_utils.py` 中的 logger 实体。
3. 更新 README 中 `example_utils.py` 的描述。
4. 运行示例测试、编译检查和全量测试。
