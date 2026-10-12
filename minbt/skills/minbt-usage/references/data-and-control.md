# 数据与运行控制

## 数据结构与时间

`Exchange.set_bars(data, date_key="dt", symbol_key="symbol")` 支持 pandas、polars 和 `list[dict]`。
不要求完整 OHLCV；默认估值需要 `close`。同一 `(dt, symbol)` 的重复 K 线会报错。
不要用行号代替时间，`date_key` 必须存在。

单标的 CSV 没有标的列时可先补列：

```python
data["symbol"] = "BTCUSDT"
exchange.set_bars(data, date_key="date", symbol_key="symbol")
```

回调的 `dt` 统一为 UTC datetime，无时区时间按 UTC 解释。数字时间戳按数量级推断
秒、毫秒、微秒或纳秒；有歧义时先调用
`minbt.data.model.normalize_datetime(value, unit="ms")` 显式转换，再传给 Feed。

## 数据回调与价格

具名数据入口及对应截面回调：

| 数据入口 | 策略回调 | 载荷 |
| --- | --- | --- |
| `set_bars(data)` | `on_bars(dt, bars)` | `{symbol: row}` |
| `set_books(data)` | `on_books(dt, books)` | `{symbol: row}` |
| `set_trades(data)` | `on_trades(dt, trades)` | `{symbol: [row, ...]}` |
| `set_news(data)` | `on_news(dt, news)` | News 元组 |

这些入口都可指定 `date_key`、`symbol_key` 和 `feed_priority`。
逐笔成交在同一时间可以有多条，保留在标的对应列表中；News 可不指定标的。
同一 dt 先收齐完整批次，由 Broker 选择估值价格、更新账户、处理挂单及退出条件，随后按
`bars → books → trades → bar → news` 分发策略行情回调。

默认 `Broker(mark_price="kline.close")` 用 K 线 close 估值。字段不同应在 Broker 配置：

```python
broker = Broker(initial_cash=100_000, mark_price="kline.price")
exchange.set_bars(data)  # 数据包含 dt、symbol、price
```

Exchange 不根据 Feed 优先级选择盈亏价格。多来源提供同一标的价格时应明确消除歧义；
高级的 `(feed_name, kind, field)` 可精确指定来源，也支持元组与 callable 价格选择方式。
`mark_price_aggregation` 默认 `error`，`mark_price_missing` 默认 `keep`。
一次下单显式传入的 `price` 用于该次成交，不替代持续估值来源。

通用事件可使用 `Bar(dt=..., symbol=..., kind=..., data=...)`，策略实现 `on_bar(dt, bar)`，
按单条事件接收，不聚合成多标的截面。普通 K 线策略优先 `on_bars`。
Feed 通过 `exchange.add_feed(feed)` 注册。

## Binance 自动下载与缓存

```python
from minbt import Exchange
from minbt.data import binance

exchange = Exchange()
exchange.add_feed(binance.BinanceKlineFeed(
    symbols=["BTCUSDT", "ETHUSDT"],
    interval="1h",
    start="2024-01-01",
    end="2024-01-03",
    cache_dir="./data",
))
```

首次运行下载到 `{cache_dir}/minbt-data.sqlite3`，后续相同区间复用缓存。
`cache_only=True` 用于离线运行，缓存缺失或覆盖不完整时会报错，不创建空缓存。
默认 `closed_only=True`，只回放准备时已确认收盘的 K 线；缓存不能证明收盘后抓取时重新下载，
离线模式报告缓存不完整。`closed_only=False` 可包含未收盘 K 线。
此 Feed 在准备阶段读取缓存查询结果，适合预加载；大数据渐进回放可使用 CSV 或 iosql Feed。

## CSV 与 iosql

Binance 月度 K 线文件或 iosql K 线表使用专用 Feed：

```python
from minbt.data import BinanceKlineCsvFeed, BinanceKlineIosqlFeed

exchange.add_feed(BinanceKlineCsvFeed(
    root="/path/to/kline.csv/1m",
    symbols=["BTCUSDT"],
    interval="1m",
    start="2023-01-01",
    end="2023-01-03",
))
# 数据库存储时可替换为 BinanceKlineIosqlFeed("sqlite:///path/to/data.iosql", "1m", ...)
```

`start/end` 为半开区间 `[start, end)`。Feed 在启动前检查请求 symbol、CSV 月份、
iosql table/interval 和时间范围；缺数据或配置错误直接报错。
`BinanceKlineIosqlFeed` 需要另行安装 iosql 0.3.x 或更新版本，`batch_size` 调整读取缓冲。

通用 `CsvBarFeed` 和 `IosqlBarFeed` 读取 OrderBook、Trade、Price 等 Bar 存储，
数据至少有 `dt,symbol,kind,data`，其中 `data` 是 JSON。
不要将这种格式与 Binance Kline 专用文件或表混用。

## 运行窗口与回放

每个 Exchange 只启动一次。普通用户调用 `result = exchange.run()`；需要限制区间时：

```python
result = exchange.run(start="2026-01-01", end="2026-02-01")
```

窗口为 `[start, end)`，`None` 不额外限制该侧。起点是新实验的起点，不自动恢复
之前的指标或持仓。比较运行方式或实验区间时，新建全部运行对象。

需要控制资源时，可在唯一一次启动中传 `load_mode="incremental"` 渐进读取，
`preload` 为全量预加载，默认 `auto` 自动选择。`stream` 不用于历史回放。

## 暂停与退出

控制回调无参数，返回当前期望状态：

```python
from threading import Event

pause_requested = Event()
exit_requested = Event()


def control():
    if exit_requested.is_set():
        return "exit"
    return "pause" if pause_requested.is_set() else "continue"


result = exchange.run(control=control)
```

- `continue`：行情、账户与策略继续。
- `pause`：跳过所有策略行情回调，账户、挂单、退出规则和历史继续更新。
- `exit`：结束整个回测并返回最后完整处理时间的结果。

每个完整时间批次开始前检查控制状态，暂停期间照常检查。继续时不补发暂停期间数据，
指标重建或预热由业务逻辑负责。`control()` 与 `on_finish()` 只读运行账户。
`run()` 阻塞调用线程；应用需要外部控制时可组织工作线程，控制线程仅更新 Event，
交易仍由策略行情回调和已有账户规则执行。

## 结果快照

```python
equity = result.get_equity_curve()  # (UTC 时间, 权益)
positions = result.get_position_sizes()
sizes = result.get_position_curve("BTCUSDT")
orders = result.get_orders()
pnl = result.get_total_pnl()
initial_cash = result.get_initial_cash()
print(result.meta["status"], result.meta["last_dt"])
```

快照不受原账户后续变化影响。多策略需要指定 `strategy_id`；共享 Broker 的策略查询
同一账户，不能重复累加。`meta` 记录请求与实际时间、步数、策略 ID、控制状态与变化。
自然完成为 `completed`，主动退出为 `exited`；异常继续抛出。
完成表示处理完可用数据，退出后的曲线仅覆盖已处理区间。
