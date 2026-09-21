# PLAN-044：增加可手算的盈亏曲线示例

## 目标

为 `examples` 增加简单直接的盈亏 sanity check，使用户可以同时看到：

- 多头和空头方向是否计算正确；
- 手续费是否计入最终结果；
- 持仓过程中的净盈亏曲线和零基线；
- 理论手算值与 minbt 实际结果是否一致。

## 实施范围

1. 新增 `examples/00_pnl_sanity_check.py`，构造三组短路径行情，分别回测多头、空头和手续费场景。
2. 用 `权益 - 初始资金` 生成净盈亏曲线，输出理论值和实际值，并在不一致时显式失败。
3. 在 `tests/test_examples.py` 中增加脚本运行覆盖和理论盈亏断言。
4. 新增 `tests/test_pnl.py`，从 Broker 公共接口覆盖多空往返交易和手续费。
5. 更新 `README.md` 与 `skills/minbt-usage/SKILL.md` 的示例索引和结果查询说明。
6. 完成代码 review、相关测试、全量测试和编译检查，生成结果文档。

## 验收标准

- `python examples/00_pnl_sanity_check.py` 无异常，并保存 `examples/screenshots/00_pnl_sanity_check.png`。
- 三个场景的最终实际净盈亏分别接近 `20`、`10`、`-0.15005`。
- 图中包含零盈亏基线，曲线能反映正负盈亏。
- 新测试能在示例结果偏离理论值时失败。
- 不改变核心 Broker/Portfolio/Position API 和既有行为。
- `pytest -q`、`python -m compileall -q minbt examples tests`、`git diff --check` 通过。
