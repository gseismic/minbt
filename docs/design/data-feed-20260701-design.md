# minbt DataFeed 数据接入设计

## 状态

本文是数据接入层目标设计稿。

核心入口：

```python
exchange.add_feed(feed)
```

本文修正后的关键边界：

1. 第一阶段只实现历史 replay feed。
2. 实时 live feed 是目标模型，不在第一阶段落地。
3. `add_feed(...)` 第一阶段可以物化 feed 事件，并合并进现有 `Exchange` 时间线。
4. 对策略暴露的 `dt` 必须统一为 `datetime.datetime`，不能暴露 SQLite 毫秒整数。
5. 不公开 `DataStore` 作为主路径用户概念。
6. 内置 Binance 历史数据先支持 futures K 线，通过下载器适配层自动拉取，用户只感知 `cache_dir`。

## 背景

minbt 的目标是方便快捷的回测。当前用户写策略前，通常还要手工完成：

1. 找数据源。
2. 下载 K 线。
3. 保存 CSV。
4. 清洗字段。
5. 再传给 `Exchange.set_bars(...)`。

这会让入门路径被“准备数据”打断。

目标体验：

```python
from minbt import Exchange
from minbt.data import binance

exchange = Exchange()
exchange.add_feed(binance.BarsReplayFeed(
    symbols=["BTCUSDT", "ETHUSDT"],
    interval="1h",
    start="2024-01-01",
    end="2024-06-01",
    cache_dir="./data",
))
exchange.add_strategy(strategy)
exchange.run()
```

用户只指定：

- 数据源。
- 数据类型。
- 标的。
- 时间范围。
- 缓存目录。

下载、增量补齐、SQLite 缓存、排序、去重和复用由 feed 内部完成。

## 设计目标

1. 用户只需要理解一个新概念：`feed`。
2. `Exchange` 消费统一 feed，不关心数据来自 Binance、CSV、SQLite 还是未来 websocket。
3. `set_bars/set_books/set_trades/set_news` 继续服务“用户已经有数据”的最短路径。
4. `add_feed(feed)` 服务“用户希望系统自动接入、下载、缓存、复用数据”的路径。
5. 策略侧继续使用 `on_bars/on_books/on_trades/on_news(dt, data)`。
6. 第一阶段不引入完整实时运行时，避免把最简回测系统拖成数据平台。

## 非目标

1. 不做通用数据平台。
2. 不把 `DataStore` 暴露为主路径用户概念。
3. 不设计大而全的 provider 注册系统。
4. 不强制所有数据源支持 replay/live 成对能力。
5. 不在第一阶段支持私有账户数据、鉴权管理和实盘交易。
6. 不自动补齐缺失 bar，不生成合成行情。
7. 不把 SQLite 表结构变成用户需要直接操作的公共契约。
8. 不在第一阶段支持 live feed。
9. 不在第一阶段支持自定义 `event_type`。

## 核心决策

推荐主接口：

```python
exchange.add_feed(feed)
```

推荐 feed 命名：

```python
binance.BarsReplayFeed(...)
CsvBarsFeed(...)
SqliteBarsFeed(...)
NewsReplayFeed(...)
```

不推荐公开主路径：

```python
store = DataStore("./data")
feed = store.bars(...)
```

原因：

1. `DataStore` 更像数据平台概念。
2. minbt 用户的核心意图是“给 Exchange 接入一条数据流”。
3. 缓存只是 feed 的内部能力，用户只需要传 `cache_dir`。

不推荐：

```python
binance.ReplayFeed(kind="bars", ...)
```

原因：

1. `ReplayFeed` 只表达时间模式，没有表达数据结构。
2. `kind="bars"` 会导致参数随 kind 漂移。
3. bars 需要 `interval`，books 需要 `depth`，news 需要 `category`，接口会变胖。

不强制：

```python
binance.Bars.replay(...)
binance.Bars.live(...)
```

它可以后续作为便利工厂，但不作为统一契约。现实里有些数据只有 replay，有些只有 live，有些没有明确 replay/live 区分。

## 阶段边界

### 第一阶段：Replay Feed

第一阶段只支持有限历史数据流：

```text
Replay DataFeed -> FeedEvent -> Exchange 物化合并 -> 现有 run loop
```

第一阶段允许实现策略：

1. `add_feed(feed)` 只注册 feed，不下载数据。
2. `Exchange.run()` 开始时调用 `feed.prepare()`。
3. `Exchange.run()` 读取 `feed.events()`。
4. feed events 必须是有限事件流。
5. Exchange 可以把 events 物化到当前内部 grouped 时间线。
6. 物化完成后复用现有按 `dt` 排序遍历的 run loop。

这样做的原因：

1. 改动小。
2. 不破坏当前 `set_bars(...)` 主路径。
3. 避免第一阶段就实现阻塞队列、watermark、stop 等实时运行时能力。

### 未来阶段：Live Feed

live feed 不能复用当前“预先收集全部 dt 再遍历”的模型。

目标模型应是事件驱动：

```text
DataFeed events -> event queue -> dt batch -> price update -> broker process -> strategy callbacks
```

live 阶段必须重新定义：

1. 多个 live feed 如何非阻塞读取。
2. 同一 `dt` 的事件何时认为收集完成。
3. watermark 或 timeout 机制。
4. `stop()` 机制。
5. `Exchange.run(until=None, max_events=None)` 等运行控制。
6. replay feed 和 live feed 混合时的终止条件。

终止条件目标：

1. 只有 replay feed 时，所有 feed 耗尽后退出。
2. 存在 live feed 时，默认阻塞直到用户停止、feed 结束或达到运行控制条件。

注意：

`heapq.merge` 只适合多个有限、有序 replay feed。它不足以解决 live feed，因为 live feed 还需要非阻塞读取和同一时间批次收敛机制。

## 用户接口

### Exchange.add_feed

目标签名：

```python
def add_feed(self, feed) -> None:
    ...
```

行为：

1. 校验 feed 是否实现 DataFeed 契约。
2. 校验 `feed.name` 唯一。
3. 注册 feed。
4. 不立即下载数据。
5. 不隐式覆盖已有 feed。

第一阶段约束：

1. `add_feed(...)` 只接受 replay feed。
2. 如果 feed 声明为 live feed，应抛出 `NotImplementedError` 或 `ValueError`。
3. 如果用户需要替换 feed，应后续增加显式 `replace_feed(name, feed)`，不要让 `add_feed` 同时承担新增和覆盖语义。

### DataFeed 最小契约

第一阶段最小契约：

```python
from typing import Iterable, Protocol, runtime_checkable

@runtime_checkable
class DataFeedProtocol(Protocol):
    name: str
    event_type: str

    def events(self) -> Iterable["FeedEvent"]:
        ...
```

可选生命周期：

```python
def prepare(self) -> None:
    ...

def close(self) -> None:
    ...
```

实现规则：

1. `prepare()` 缺失时视为空操作。
2. `close()` 缺失时视为空操作。
3. `callback` 不进入公开 DataFeed 契约。
4. `priority` 不进入公开 DataFeed 契约。
5. `is_live` 不作为第一阶段公开必需字段。

`callback` 规则：

```python
callback = f"on_{event_type}"
```

例如：

|event_type|callback|
|---|---|
|`bars`|`on_bars`|
|`books`|`on_books`|
|`trades`|`on_trades`|
|`news`|`on_news`|

第一阶段只支持标准事件类型：

```text
bars, books, trades, news
```

自定义事件类型放到后续阶段。后续如果支持自定义事件，建议规则是：策略缺少 `on_{event_type}` 时跳过该策略该事件，并最多记录一次 warning。

## FeedEvent 契约

Feed 向 Exchange 产出的标准事件：

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

@dataclass(frozen=True)
class FeedEvent:
    event_type: str
    dt: datetime
    data: object
    prices: Mapping[str, float] | None = None
```

字段语义：

|字段|说明|
|---|---|
|`event_type`|事件类型，必须和 feed 的 `event_type` 一致|
|`dt`|事件时间，必须是 `datetime.datetime`|
|`data`|传给策略回调的数据切片|
|`prices`|可选，用于更新 broker 最新价格|

### dt 类型规范

对外策略回调中的 `dt` 必须稳定。

目标规范：

1. `FeedEvent.dt` 必须是 `datetime.datetime`。
2. 推荐使用带 UTC 时区的 `datetime.datetime`。
3. SQLite 内部可以使用 UTC 毫秒整数 `dt_ms`。
4. 不允许把 `dt_ms` 直接暴露给策略。
5. `set_xx(...)` 路径也应逐步标准化为同样的 `datetime.datetime`。

推荐转换：

```text
SQLite dt_ms -> datetime.datetime(..., tzinfo=datetime.timezone.utc)
用户输入 date_key -> datetime.datetime
```

如果用户传入无法转换的 dt，应抛出 `ValueError`，不要让不同数据源在策略回调里暴露不同 dt 类型。

## 标准事件结构

### bars

```python
FeedEvent(
    event_type="bars",
    dt=dt,
    data={
        "BTCUSDT": {
            "dt": dt,
            "symbol": "BTCUSDT",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 12.3,
        }
    },
    prices={"BTCUSDT": 100.5},
)
```

策略回调：

```python
def on_bars(self, dt, bars):
    ...
```

### books

```python
FeedEvent(
    event_type="books",
    dt=dt,
    data={
        "BTCUSDT": {
            "dt": dt,
            "symbol": "BTCUSDT",
            "bids": [(100.0, 1.2)],
            "asks": [(100.1, 0.8)],
        }
    },
    prices=None,
)
```

策略回调：

```python
def on_books(self, dt, books):
    ...
```

### trades

```python
FeedEvent(
    event_type="trades",
    dt=dt,
    data={
        "BTCUSDT": [
            {
                "dt": dt,
                "symbol": "BTCUSDT",
                "price": 100.0,
                "qty": 0.1,
                "side": "buy",
            }
        ]
    },
    prices={"BTCUSDT": 100.0},
)
```

策略回调：

```python
def on_trades(self, dt, trades):
    ...
```

### news

```python
FeedEvent(
    event_type="news",
    dt=dt,
    data=[
        {
            "dt": dt,
            "title": "...",
            "symbols": ["BTCUSDT"],
            "sentiment": 0.4,
        }
    ],
    prices=None,
)
```

策略回调：

```python
def on_news(self, dt, news):
    ...
```

## set_xx 与 add_feed 的共存规则

现有接口继续保留：

```python
exchange.set_bars(data)
exchange.set_books(data)
exchange.set_trades(data)
exchange.set_news(data)
```

定位：

1. `set_xx` 是“我已经有数据”的最短路径。
2. `add_feed` 是“我需要自动下载、缓存、复用或后续实时订阅”的路径。

第一阶段内部策略：

1. `set_xx(...)` 可以继续走当前 `_set_feed(...)` 实现。
2. `add_feed(replay_feed)` 可以在 `run()` 开始时物化 events。
3. 物化后的 events 按 `event_type` 合并进同一时间线。
4. `set_xx(...)` 和 `add_feed(...)` 的同类数据必须执行同一合并规则。
5. 不允许后注册数据 silently overwrite 先注册数据。

示例：

```python
exchange.set_bars(local_df)
exchange.add_feed(binance.BarsReplayFeed(...))
```

行为：

1. 两份 bars 数据按 `dt` 和 `symbol` 合并。
2. 如果同一 `(dt, symbol)` 同时存在两条 bar，抛出 `ValueError`。
3. 如果没有重复，则策略只收到一次 `on_bars(dt, bars)`。

## 同一时间调度规则

Exchange 需要把同一 `dt` 下的数据合并成同一时间截面。

推荐流程：

1. 收集当前 `dt` 下所有事件。
2. 合并同类事件。
3. 收集所有事件提供的 `prices`。
4. 更新 broker 最新价。
5. 每个 `dt` 只执行一次 `broker.process_pending_orders(dt=dt)`。
6. 每个 `dt` 只执行一次 `broker.check_exit_rules(dt=dt, data=slices)`。
7. 按标准事件顺序调用策略回调。
8. 记录策略历史。

标准事件顺序由 Exchange 固定，不由 feed 公开字段决定：

```text
bars -> books -> trades -> news
```

原因：

1. 保持当前设计中 `on_bars -> on_books -> on_trades -> on_news` 的确定性。
2. 避免用户为了基础数据接入理解 priority。
3. 保持同一时间截面聚合，避免横截面策略时序偏差。

## 多 feed 合并规则

同一个 `dt` 下，多个 feed 可能产出相同 `event_type`。

标准事件类型的合并规则：

|event_type|合并规则|
|---|---|
|`bars`|按 symbol 合并为一个 dict；同一 `(dt, symbol)` 重复时抛出 `ValueError`|
|`books`|按 symbol 合并为一个 dict；同一 `(dt, symbol)` 重复时抛出 `ValueError`|
|`trades`|按 symbol 合并为 `dict[str, list[TradeRecord]]`；同一 symbol 的列表按 feed 注册顺序拼接|
|`news`|拼接为一个 list，保留 feed 注册顺序|

同 event_type 多 feed 的拼接顺序由 `add_feed(...)` 注册顺序决定。

## 价格更新和冲突规则

`FeedEvent.prices` 是用于 broker 的最新价格，不等同于策略数据本身。

规则：

1. 同一 `dt` 下先收集所有 `prices`。
2. 同一 symbol 如果只有一个价格，直接更新 broker。
3. 同一 symbol 如果多个 feed 提供相同价格，可以接受。
4. 同一 symbol 如果多个 feed 提供不同价格，默认抛出 `ValueError`。
5. 不希望更新 broker 价格的 feed 应提供 `prices=None`。

设计原因：

1. 避免 bars close 和 trades last price 在同一 `dt` 下隐式覆盖。
2. 避免限价单和退出条件使用哪个价格不清楚。
3. 让用户显式选择价格来源。

后续如果确实需要多价格源，可以增加显式高级参数，例如：

```python
price_conflict="error"        # 默认
price_conflict="last"         # 按事件顺序覆盖
price_conflict="prefer_bars"  # 固定使用 bars
```

第一阶段不实现这些高级策略。

## Binance BarsReplayFeed

首个内置数据源建议只做 Binance K 线历史回放。

用户接口：

```python
from minbt.data import binance

feed = binance.BarsReplayFeed(
    symbols=["BTCUSDT", "ETHUSDT"],
    interval="1h",
    start="2024-01-01",
    end="2024-06-01",
    cache_dir="./data",
)
```

目标签名：

```python
class BarsReplayFeed:
    def __init__(
        self,
        symbols,
        interval,
        start,
        end,
        cache_dir,
        *,
        market="futures",
        name=None,
        refresh=False,
        cache_only=False,
        closed_only=True,
    ):
        ...
```

参数语义：

|参数|说明|
|---|---|
|`symbols`|标的列表，例如 `["BTCUSDT"]`|
|`interval`|K 线周期，例如 `"1m"`、`"5m"`、`"1h"`、`"1d"`|
|`start`|开始时间，包含|
|`end`|结束时间，不包含|
|`cache_dir`|缓存目录|
|`market`|Binance 市场类型或产品线。第一阶段只支持 `"futures"`，因为参考客户端使用 futures API；后续支持 spot 时再显式扩展|
|`name`|feed 名称，默认自动生成|
|`refresh`|是否忽略已有覆盖范围并重新下载|
|`cache_only`|是否只读本地缓存，缺数据时直接报错|
|`closed_only`|是否排除未闭合 K 线，默认排除|

行为：

1. 初始化时只做参数校验，不发网络请求。
2. `prepare()` 时检查 SQLite 缓存覆盖范围。
3. `cache_only=True` 且缓存不足时抛出 `RuntimeError`。
4. 对缺失区间按 Binance 分页限制下载。
5. 下载结果写入 SQLite。
6. 从 SQLite 读取完整请求区间。
7. `events()` 按 `dt` 产出有限 `bars` 事件。
8. `market` 不是 `"futures"` 时第一阶段直接抛出 `ValueError`，不静默切换数据源。

时间范围规则：

1. `start` 包含。
2. `end` 不包含。
3. Binance K 线使用 open time 作为 `dt`。
4. 内部统一存储为 UTC 毫秒整数。
5. 产出给 Exchange 的 `dt` 必须转换为 `datetime.datetime`。
6. 默认不返回未闭合 K 线，避免回测未来函数风险。

字段规则：

```python
{
    "dt": dt,
    "symbol": symbol,
    "open": open,
    "high": high,
    "low": low,
    "close": close,
    "volume": volume,
}
```

Binance 字段归一化：

|Binance 字段|minbt 字段|说明|
|---|---|---|
|`open_time`|`dt` / `dt_ms`|策略看到 `datetime.datetime`，SQLite 内部存毫秒整数|
|`open`|`open`|float|
|`high`|`high`|float|
|`low`|`low`|float|
|`close`|`close`|float，默认作为 broker price|
|`volume`|`volume`|float|
|`close_time`|`close_time`|provider-specific，可存储但不作为通用 bars 必需字段|
|`volume_quote`|`volume_quote`|provider-specific|
|`num_trades`|`num_trades`|provider-specific，写入前转为 int|
|`volume_base_buy`|`volume_base_buy`|provider-specific|
|`volume_quote_buy`|`volume_quote_buy`|provider-specific|

通用策略只依赖 `dt/symbol/open/high/low/close/volume`。Binance feed 可以保留 provider-specific 字段，但 `CsvBarsFeed`、`SqliteBarsFeed` 等其他 feed 不需要实现这些字段。

分页规则：

1. Binance K 线 REST 单次请求有数量上限。
2. 第一阶段按 `interval * limit` 分段请求。
3. 每个请求成功处理并完成本地事务后，才能更新 coverage。
4. 网络失败时抛出异常，不写 coverage。

## Binance 下载适配层（参考现有代码）

现有参考实现 `binance.kline.dserver/kline_dserver/binance_client.py` 中的 `BinanceKlineClient` 只是内部下载适配层，不是用户接口。

它暴露的能力可以直接映射到 feed 内部：

```python
class BinanceKlineClient:
    def list_symbols(self) -> list[str]:
        ...

    def fetch_klines(
        self,
        symbol: str,
        period: str,
        start_dt,
        end_dt,
        chunk_size: int = 1440,
        delay: float = 0.5,
    ) -> list[dict]:
        ...

    def fetch_recent_klines(self, symbol: str, period: str, limit: int) -> list[list]:
        ...

    def fetch_raw_klines(
        self,
        symbol: str,
        period: str,
        start_time: int,
        end_time: int,
        limit: int = 5,
    ) -> list[list]:
        ...
```

设计约束：

1. `list_symbols()` 只用于能力探测、参数校验或测试，不是用户主路径。
2. `fetch_klines(...)` 是历史数据下载的优先路径。
3. `fetch_recent_klines(...)` 和 `fetch_raw_klines(...)` 只作为低层兼容或测试辅助，不进入公开 feed 契约。
4. 下载器返回的原始行数据由 `BarsReplayFeed` 统一归一化成标准 `FeedEvent`。
5. 下载、分页、重试、节流、落盘都属于 feed 内部实现，用户只需传 `cache_dir` 和时间范围。
6. 如果当前实现只支持某个 Binance 产品线，应在初始化时显式校验，不要静默回退到别的产品线。
7. 用户参数 `interval` 映射到下载器参数 `period`，该命名差异不暴露给策略。
8. 第一阶段不把 `client`、`chunk_size`、`delay`、`retry` 作为主路径用户参数；测试可通过内部工厂或模块替换注入 fake client。

## SQLite 缓存设计

SQLite 是 feed 的内部实现，不作为主路径用户接口。

推荐文件：

```text
{cache_dir}/minbt-data.sqlite3
```

`source` 命名规范：

|来源|source|
|---|---|
|Binance|`binance`|
|CSV|`csv`|
|用户自定义|建议使用小写短名称|

推荐表：

```sql
CREATE TABLE bars (
    source TEXT NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    dt_ms INTEGER NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    close_time INTEGER,
    volume_quote REAL,
    num_trades INTEGER,
    volume_base_buy REAL,
    volume_quote_buy REAL,
    PRIMARY KEY (source, market, symbol, interval, dt_ms)
);
```

```sql
CREATE TABLE bar_coverage (
    source TEXT NOT NULL,
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    start_ms INTEGER NOT NULL,
    end_ms INTEGER NOT NULL,
    updated_at_ms INTEGER NOT NULL,
    PRIMARY KEY (source, market, symbol, interval, start_ms, end_ms)
);
```

索引：

```sql
CREATE INDEX idx_bars_query
ON bars (source, market, symbol, interval, dt_ms);
```

缓存规则：

1. `bars` 用 upsert 去重。
2. coverage 使用半开区间 `[start_ms, end_ms)`。
3. 只有成功请求远端并完成本地事务的区间才能写入 coverage。
4. 成功请求但返回 0 行时也可以写入 coverage，避免每次运行重复请求上市前或无数据区间。
5. 覆盖范围只表示“曾成功请求并处理”，不表示交易所没有缺失 bar。
6. 读取时始终按 `dt_ms, symbol` 排序。
7. 不自动补齐缺失时间点。
8. 网络失败时抛出异常，不把失败区间标记为已覆盖。
9. 第一阶段不保证多进程同时写同一个 cache sqlite 的安全性。

coverage 合并规则：

1. 写入新 coverage 前读取同一 `(source, market, symbol, interval)` 的已有区间。
2. 将重叠或相邻区间合并。
3. 删除旧 coverage 区间。
4. 写入合并后的 coverage 区间。

`refresh=True` 规则：

1. 忽略请求范围内已有 coverage。
2. 重新下载请求范围。
3. bars 使用 upsert 覆盖旧值。
4. 成功后对 coverage 执行同样的区间合并。
5. 如果下载失败，不删除原有可用 coverage。

为什么不公开 DataStore：

1. 用户主路径只需要 `cache_dir`。
2. SQLite 表结构属于内部实现，后续可迁移到 Parquet 或其他格式。
3. 如果将来需要缓存管理能力，可以补充 CLI 或辅助接口，例如 `minbt data list`、`minbt data clear`。
4. 这些能力不影响 `exchange.add_feed(feed)`。

## 错误语义

第一阶段不需要复杂异常层级。

推荐规则：

|场景|异常|
|---|---|
|参数错误|`ValueError`|
|feed 类型不符合契约|`TypeError`|
|重复 feed name|`ValueError`|
|第一阶段传入 live feed|`NotImplementedError` 或 `ValueError`|
|下载失败|`RuntimeError`|
|cache_only 且缓存不足|`RuntimeError`|
|SQLite 读写失败|保留原始异常或包装为 `RuntimeError`|
|数据字段缺失|`ValueError`|
|重复 `(dt, symbol)` 且无法合并|`ValueError`|
|同一 `dt, symbol` 出现不同 broker price|`ValueError`|
|dt 无法转换为标准 datetime|`ValueError`|

错误消息必须包含 source、symbol、interval、时间范围等关键信息。

## 典型用户场景

### 场景 1：用户已有 DataFrame

```python
exchange.set_bars(df)
```

这是最短路径，继续保留。

### 场景 2：用户要 Binance 历史 K 线并自动缓存

```python
exchange.add_feed(binance.BarsReplayFeed(
    symbols=["BTCUSDT", "ETHUSDT"],
    interval="1h",
    start="2024-01-01",
    end="2024-06-01",
    cache_dir="./data",
))
```

用户不需要手工下载 CSV。

### 场景 3：用户从 CSV 回放

```python
exchange.add_feed(CsvBarsFeed(
    path="bars.csv",
    date_key="dt",
    symbol_key="symbol",
    price_key="close",
))
```

CSV 只有 replay，不需要 live。

### 场景 4：未来接入实时 Binance K 线

```python
exchange.add_feed(binance.BarsLiveFeed(
    symbols=["BTCUSDT"],
    interval="1m",
))
```

策略仍然写：

```python
def on_bars(self, dt, bars):
    ...
```

但该能力不属于第一阶段。

### 场景 5：未来接入新闻数据

```python
exchange.add_feed(NewsReplayFeed(
    path="news.sqlite",
))
```

策略：

```python
def on_news(self, dt, news):
    ...
```

新闻 feed 不需要有 `Bars`、`Replay` 或 `Live` 这些命名。

## 命名规则

推荐：

|类型|命名|
|---|---|
|Binance 历史 K 线|`binance.BarsReplayFeed`|
|Binance 实时 K 线|`binance.BarsLiveFeed`，后续阶段|
|CSV K 线|`CsvBarsFeed`|
|SQLite K 线|`SqliteBarsFeed`|
|新闻回放|`NewsReplayFeed`|
|用户信号回放|`SignalReplayFeed`|

原则：

1. 类名表达数据结构和接入方式。
2. 不要求所有类都有 replay/live 成对命名。
3. `Feed` 后缀表示这个对象可以直接传给 `exchange.add_feed(feed)`。
4. `Bars` 和 `on_bars` 对齐，不使用 Binance 专属的 `Kline` 作为通用用户概念。

默认 feed name：

1. 内置 feed 自动生成 name。
2. name 应包含 source、event_type、mode、核心参数。
3. 示例：`binance:bars:<market>:1h:BTCUSDT,ETHUSDT`。
4. 如果自动 name 冲突，用户应显式传 `name=...`。

## 实施顺序建议

第一阶段：Replay DataFeed 基础契约

1. 新增 `FeedEvent`。
2. 新增 `Exchange.add_feed(feed)`。
3. 第一阶段只接受 finite replay feed。
4. `add_feed` 注册 feed，`run()` 时 prepare 并物化 events。
5. 将物化 events 合并进现有 grouped 时间线。
6. `set_xx` 和 `add_feed` 共用合并规则。
7. 测试多个 feed 同一 `dt` 的合并、重复冲突、价格冲突和回调顺序。

第二阶段：本地 replay feed

1. 实现 `CsvBarsFeed` 或 `LocalBarsFeed`。
2. 用它验证 `add_feed` 不依赖网络。
3. 覆盖 bars/trades/news 的基本合并规则。

第三阶段：Binance BarsReplayFeed

1. 实现 Binance HTTP 下载。
2. 实现 SQLite 缓存。
3. 实现 coverage merge 和缺失区间补齐。
4. 实现 `cache_only`、`refresh` 和未闭合 K 线过滤。
5. 增加 10 万行级别性能测试。

第四阶段：实时 feed

1. 重新设计事件驱动 run loop。
2. 增加 stop/watermark/timeout 机制。
3. 实现 `BarsLiveFeed`。
4. 验证 live feed 和 replay feed 能使用同一个策略回调。

## 当前推荐决策

1. 不引入公开 `DataStore` 主接口。
2. 以 `exchange.add_feed(feed)` 作为数据接入稳定入口。
3. 第一阶段只做 replay feed，不做 live feed。
4. 第一阶段不暴露 `callback`、`priority`、`is_live`。
5. 第一阶段不支持自定义 `event_type`。
6. 内置 Binance 首先只做 `BarsReplayFeed`。
7. SQLite 缓存只作为 feed 内部能力，用户只传 `cache_dir`。
8. 策略侧继续保持 `on_xx(dt, data)`。
9. `set_bars(...)` 继续作为用户已有数据的最简单入口。
