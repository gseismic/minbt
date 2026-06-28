# PLAN-008 真实场景示例与不足分析结果

## 实施概览

本次按 `PLAN-008-realistic-scenarios.md` 新增三类更贴近真实研究流程的示例，并用这些场景反推 minbt 在“方便快捷回测”目标下的不足。

后续 `PLAN-012-implement-design.md` 已把这些示例迁移到 `set_bars/on_bars` 主路径，并实现目标仓位接口、函数式退出规则和最小市场模型。本结果文档保留场景分析，同时标注哪些不足已被后续计划解决。

## 新增示例

### 1. 单标的趋势突破

文件：`examples/scenario_single_breakout.py`

场景特点：

- 单标的 OHLC 行情。
- 使用 `on_bars(dt, bars)`。
- 突破入场。
- ATR 类波动过滤。
- 策略内止损。
- 按目标名义金额调仓。

运行结果：

```bash
python examples/scenario_single_breakout.py
# final_equity=111029.01
# final_cash=67269.05
# final_position=721.667983
# trade_count=3
# stop_count=1
```

### 2. 多标的横截面轮动

文件：`examples/scenario_multi_rotation.py`

场景特点：

- 多标的同一时间截面行情。
- 使用 `on_bars(dt, bars)`。
- 动量排序。
- 持有 top N。
- 等权目标仓位。
- 定期再平衡。

运行结果：

```bash
python examples/scenario_multi_rotation.py
# final_equity=118303.38
# final_cash=44979.05
# final_positions={'BTCUSDT': 465.2836155267977, 'SOLUSDT': 452.1917846086323}
# last_selection=['SOLUSDT', 'BTCUSDT']
# rebalance_count=10
```

### 3. 双标的配对均值回归

文件：`examples/scenario_pairs_mean_reversion.py`

场景特点：

- 两个相关标的。
- 使用 `on_bars(dt, bars)`。
- log 价差。
- z-score 入场和退出。
- 双腿 long/short。
- 目标名义金额对冲。

运行结果：

```bash
python examples/scenario_pairs_mean_reversion.py
# final_equity=100438.32
# final_cash=65722.28
# final_positions={'BTCUSDT': -308.13452757612396, 'ETHUSDT': 314.4128914969113}
# state=long_pair
# entry_count=5
# exit_count=4
# last_z=-0.7897
```

## 共用工具

文件：`examples/example_utils.py`

新增能力：

- `QuietLogger`：让示例默认只输出结果。
- `target_position_value()`：按目标名义金额调仓，内部调用 `broker.order_target_value(...)`。
- `flatten_position()`：清空指定 symbol 仓位，内部调用 `broker.close_position(...)`。

这些工具目前放在 examples 下，目的是让真实示例保持短小，同时优先展示 broker 主路径。

## 场景暴露的问题与当前状态

### 1. 已解决：缺少目标仓位/目标权重下单 API

三个真实场景都需要“把某个 symbol 调到目标名义金额或目标权重”：

- 单标的突破需要 `target_fraction`。
- 多标的轮动需要等权 top N。
- 配对交易需要两个 leg 按名义金额对冲。

`PLAN-012` 已实现：

- `broker.order_target_size(symbol, target_size, price=None, ...)`
- `broker.order_target_value(symbol, target_value, price=None, ...)`
- `broker.order_target_percent(symbol, percent, price=None, ...)`

仍未实现：

- `broker.rebalance_targets({symbol: target_percent}, ...)`

### 2. 高优先级：缺少交易记录和绩效统计

真实场景只打印 `final_equity` 不够。用户实际需要：

- 每笔成交记录。
- 每次调仓记录。
- 时间序列权益。
- 收益率、最大回撤、波动率、Sharpe、胜率、换手率。

当前 `Strategy.get_hist_equity()` 只有权益数值，没有时间戳；broker 也没有标准 trade ledger。用户很难快速判断策略好坏。

建议后续新增：

- `Broker.get_trades()`
- `Strategy.get_equity_curve()`，包含 `dt`。
- `minbt.stats`，输出常用绩效指标。

### 3. 高优先级：缺少批量/原子调仓能力

配对交易暴露了双腿调仓问题：当前两个 leg 是两次独立市价单。如果第一腿成功、第二腿因为资金或其他原因失败，会留下不完整对冲。

多标的轮动也有类似问题：一组 rebalance 订单没有统一成功/失败语义。

建议后续新增：

- `broker.submit_batch_orders([...])`
- 预检查所有订单保证金和现金。
- 支持 all-or-nothing 或 best-effort 两种模式。

### 4. 部分解决：止损/止盈能力

单标的突破示例仍在策略里手写 ATR 类止损逻辑，这是为了展示策略内复杂条件。

`PLAN-012` 已实现函数式退出规则：

- `broker.add_exit_rule(...)`
- `stop_loss_pct(...)`
- `take_profit_pct(...)`

仍未实现：

- 挂单式止损。
- 追踪止损订单。
- 基于 bar 内 high/low 路径的止损触发模拟。

如果后续要进一步提升快捷性，可以增加纯函数 helper：

- ATR 止损条件 helper。
- 最高价回撤退出 helper。
- 多规则组合 helper。

### 5. 中优先级：多标的数据完整性只校验唯一性，不校验截面完整性

多标的轮动和配对交易都默认每个 `dt` 下所有 symbol 都存在。当前 Exchange 会拒绝重复 `(dt, symbol)`，但不会检查缺失 symbol。

如果某天 ETH 缺失，`bars["ETHUSDT"]` 会直接 KeyError。用户需要自己处理缺失、停牌、异步 bar。

建议后续提供可选参数：

- `required_symbols=[...]`
- `missing_policy="raise" | "skip" | "ffill"`

### 6. 中优先级：撮合模型过于理想化

三个示例都按当前 `close` 直接成交。这适合快速原型，但真实回测通常至少需要：

- 滑点。
- next bar open 成交。
- 手续费分层。
- 最小下单数量和数量精度。
- 部分成交或拒单。

建议后续先增加简单可配置撮合参数：

- `execution_price="close" | "next_open"`
- `slippage_bps`
- `min_qty`
- `qty_step`

### 7. 中优先级：保证金合约模型和现货模型未区分

当前资金模型是保证金合约账户模型。对加密货币合约回测合适，但多资产轮动用户可能会以为这是现货买入。

建议后续明确或实现：

- `account_type="margin"` 默认保持现状。
- `account_type="spot"` 独立现金和资产市值模型。
- README 中继续突出当前是保证金模型。

### 8. 低优先级：示例仍需静默 logger 样板

虽然 `Broker(logger=quiet_logger)` 和 `Exchange(logger=quiet_logger)` 已可用，但用户仍需要自己定义 `QuietLogger`。

建议后续提供：

- `minbt.NullLogger`
- `Exchange(silent=True)`
- 或 `logger.disable() / logger.enable()` 的受控接口。

## 对 minbt 目标的判断

minbt 当前已经适合做“能跑起来的轻量策略原型”，尤其是：

- 单标的 bars 策略。
- 多标的同截面策略。
- 多空和保证金类策略。
- 少量代码完成市场价回测。

`PLAN-012` 已补齐目标仓位和函数式退出规则。接下来如果目标是“方便快捷地做真实研究”，最应该补的是：

1. 交易记录和绩效统计。
2. 批量调仓预检查。
3. 数据完整性策略。
4. 简单滑点和成交价格配置。
5. 现货账户模型或更明确的账户类型边界。

这些能力能直接减少用户写策略时的样板代码，并降低结果误判风险。

## 验证结果

```bash
python examples/scenario_single_breakout.py
# passed

python examples/scenario_multi_rotation.py
# passed

python examples/scenario_pairs_mean_reversion.py
# passed

pytest -q tests/test_examples.py
# 6 passed

pytest -q
# 77 passed

python -m compileall -q examples tests minbt
# passed

git diff --check
# passed
```
