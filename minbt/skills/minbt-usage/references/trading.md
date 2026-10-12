# 交易、账户与盈亏

## 常用交易入口

在 `Strategy` 行情回调中通过 `self.broker` 下单，优先表达目标持仓：

```python
self.broker.order_target_size(symbol, target_size=1, price=price)
self.broker.order_target_value(symbol, target_value=10_000, price=price)
self.broker.order_target_percent(symbol, target_percent=0.8, price=price)
```

省略 `price` 时使用当前估值价格。精确增量、市价平仓和限价单：

```python
self.broker.submit_market_order(symbol, qty=1, price=price)
self.broker.close_position(symbol, price=price)
self.broker.close_portfolio("trend")
order = self.broker.submit_limit_order(symbol, qty=1, limit_price=95)
self.broker.cancel_order(order.id)
```

`close_portfolio()` 成功时取消该组合的 pending 限价单；关闭预检失败时不撤单。

读取结构化的订单结果：

```python
order = self.broker.order_target_percent(symbol, 0.8, price=price)
if order.status == "filled":
    print(order.filled_qty, order.avg_price)
elif order.status == "rejected":
    print(order.reason)  # 用于诊断，不按精确文本分支
```

状态有 `filled`、`pending`、`canceled`、`rejected`、`skipped`；目标没有变化时返回 skipped。
可通过 `get_order(order_id)`、`get_orders(portfolio=..., symbol=...)` 查询订单。

买入限价单在最新价小于等于限价时触发，卖出在最新价大于等于限价时触发。
提交与触发时都检查资金和市场规则；pending 不预留资金，不模拟队列或部分成交。
回放时只有该批次更新了标的估值价格才尝试触发，其他事件不会使用旧价触发。

## 退出条件

下单时可设置固定止损、止盈和追踪止损：

```python
order = self.broker.order_target_percent(
    symbol, 0.8, price=price,
    stop_loss_price=price * 0.95,
    take_profit_price=price * 1.10,
    trailing_stop_pct=0.05,
)
```

持仓中使用订单 ID 修改或清除：

```python
self.broker.set_exit(order.id, stop_loss_price=price * 0.98)
self.broker.clear_exit(order.id, trailing_stop=True)
```

复杂条件使用独立函数式退出：

```python
def exit_if_breaks_support(ctx):
    return ctx.price < ctx.state["support"]


self.broker.add_exit(
    order.id,
    name="support_break",
    condition=exit_if_breaks_support,
    state={"support": price * 0.96},
)
```

`trailing_stop_pct` 与 `trailing_stop_amount` 互斥，可与固定止损/止盈并存。
同一净持仓生命周期内，同方向成交只更新显式传入的退出字段，未传字段沿用已有配置；
用 `clear_exit()` 显式清除。函数返回 True 退出当前 `portfolio + symbol` 的净持仓。
订单必须仍属于当前持仓生命周期，才可新增或修改规则。

## 分仓与多市场

```python
from minbt import Broker, markets

broker = Broker(initial_cash=100_000, fee_rate=0.0005, market=markets.CRYPTO)
broker.add_portfolio("trend", cash=60_000)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH", "510300.SH"])
```

未显式路由的 symbol 使用默认 `market`。在任何交易和回测运行前配置 `add_market()`。
查询市场使用 `broker.get_market(symbol)`。
分仓通过交易参数 `portfolio="trend"` 指定；省略时使用 main。

`markets.A_STOCK` 具有交易时间、100 股一手、价格 tick、不可做空和 T+1 锁定规则。
直接调用 Broker 下单时传 `price_dt`；Exchange 回放会提供时间。
默认 Market 为 UTC，A 股为 Asia/Shanghai；带时区时间转换到市场时区，无时区时间先按 UTC 解释。
自定义 `lot_size/tick_size/min_qty/min_notional` 必须使用有限正数。

跨市场可在一个 Broker 中分仓交易：

```python
broker = Broker(initial_cash=100_000, market=markets.CRYPTO)
broker.add_portfolio("ashare", cash=60_000)
broker.add_portfolio("crypto", cash=40_000)
broker.add_market("AStock", markets.A_STOCK, symbols=["600519.SH"])
self.broker.order_target_percent("600519.SH", 0.8, price=a_price, portfolio="ashare")
self.broker.order_target_percent("BTCUSDT", 0.8, price=btc_price, portfolio="crypto")
```

分仓总额不能超出可用资金。

## 查询与历史

```python
equity = broker.get_total_equity()
positions = broker.get_position_sizes()
position = broker.get_position(symbol)
cash = broker.get_cash()
curve = strategy.get_hist_equity()
sizes = strategy.get_hist_position_sizes(symbol)
```

历史始终为 Python list；未交易标的的持仓历史返回与权益历史等长的全零列表。
`get_position(symbol)` 对未持仓标的返回 None，不创建空仓。
`get_positions()` 返回新字典，但其中的 Position 仍是当前对象；不要直接修改。

## 盈亏查询

用库级接口查询，无需在策略内重写成交盈亏公式：

```python
pnl = broker.get_total_pnl()
print(pnl.net_pnl, pnl.realized_pnl, pnl.unrealized_pnl, pnl.fees)
main_pnl = broker.get_pnl()
symbol_pnl = broker.get_pnl(symbol, portfolio="trend")
all_symbol_pnl = broker.get_total_pnl(symbol)
records = broker.get_pnl_records(order_id=order.id)
```

Pnl 和 PnlRecord 为不可变快照。已实现、未实现盈亏为毛盈亏，fees 累计实际手续费；
`net_pnl = realized_pnl + unrealized_pnl - fees + settlement_adjustment`。
普通交易结算调整为零，穿仓清零时用于反映结算；全账户净盈亏等于总权益减 Broker 初始资金。

`get_pnl()` 默认查询 main；支持分仓或标的筛选。分仓关闭、同名重建仍保留历史，内部划拨不计利润。
`get_pnl_records()` 可按 portfolio、symbol、order_id 交集筛选，按实际记账顺序返回。
系统风险结算无订单 ID，全仓穿仓调整无标的归属。每次成交独立记账，不配对往返交易、不分摊开仓费。
未知标的为零，未知分仓抛 ValueError。

净盈亏曲线可由权益历史计算，在回测前保存初始权益：

```python
initial_equity = broker.get_total_equity()
exchange.run()
pnl_curve = [equity - initial_equity for equity in strategy.get_hist_equity()]
```

持仓未平时包含浮动盈亏，最终结果包含手续费。
