# PLAN-020 实现最简回测接口契约

## 背景

当前设计已经收敛到“Exchange 接入数据，Strategy 在同一时间截面回调中调用 Broker 交易”的最简模型，但代码仍保留开发期旧接口：

- `Exchange.set_data/on_data/on_bar` 仍存在。
- `Broker` 订单接口返回 `bool`，不是统一的 `Order`。
- 止盈止损仍挂在 `symbol` 上，不贴近真实交易中“订单成交后设置/修改退出条件”的模型。
- 限价单接口尚未实现。
- 示例和测试仍覆盖旧接口，不能证明新接口好用。

## 目标

实现 `docs/design/minbt-20260630-system-design.md` 中的核心接口契约，并补齐真实可运行示例。

## 范围

1. 重构 `Exchange`
   - 只保留 `set_bars/set_books/set_trades/set_news` 数据入口。
   - 删除用户级 `set_data`。
   - 统一回调为 `on_bars/on_books/on_trades/on_news(dt, data)`。
   - 同一 `dt` 先聚合所有数据源，先更新价格和触发待成交/退出条件，再回调策略。

2. 重构 `Strategy`
   - 删除 `on_data/on_bar` 旧回调。
   - 简化 Broker 协议，不暴露 `portfolio_id`。
   - 保留少量真实交易快捷方法 `market_buy/market_sell/market_order`。

3. 重构 `Broker`
   - 构造函数只接受 `initial_cash/fee_rate/market` 等必要参数，不再接受 `portfolio_cash/portfolio_id/initial_positions`。
   - 所有订单类接口返回 `Order`。
   - 实现 `submit_market_order/submit_limit_order/cancel_order/order_target_size/order_target_value/order_target_percent/close_position/close_portfolio`。
   - 实现订单级退出条件 `set_exit/clear_exit/get_exit/add_exit`。
   - 支持固定止损价、固定止盈价、追踪止损百分比、追踪止损金额、自定义函数退出条件。
   - 保留 `add_portfolio(name, cash)` 分仓接口，删除 `add_sub_portfolio` 用户入口。

4. 市场模型
   - 保留 `Market` 和 `markets.DEFAULT/CRYPTO/A_STOCK`。
   - 删除 `SimpleMarket/CryptoMarket/ChinaAStockMarket` 用户导出，避免类/工厂接口扩散。
   - 内部继续用市场特征校验交易时间、T+1、最小手数、tick 等规则。

5. 示例和测试
   - 更新单标的、多标的、止盈止损、分仓/市场规则等典型示例。
   - 更新测试以覆盖新接口真实行为。
   - 运行测试，修复发现的问题。

## 非目标

- 不实现完整撮合引擎。
- 不根据 bar 的 high/low 推断限价单路径。
- 不实现初始持仓参数。
- 不保留开发期旧接口兼容层。

## 验收标准

- 代码中不再暴露用户级 `set_data/on_data/on_bar/portfolio_id/add_sub_portfolio`。
- 订单接口返回结构化 `Order`。
- 限价单可挂单、成交、撤单。
- 退出条件可在提交订单时设置，也可按订单 ID 修改。
- 示例都可通过测试直接运行。
- `pytest` 通过。
