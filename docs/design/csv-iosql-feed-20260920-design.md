# minbt CSV / iosql 渐进加载 Feed 设计

## 状态

本文是 CSV 与 iosql 渐进（流式）数据接入的设计稿，基于 `data-feed-20260701-design.md`
预留的 `CsvBarsFeed` 命名与 `add_feed(feed)` 入口，为其补齐"渐进加载"与"iosql 数据源"两个能力。

目标入口（用户视角）：

```python
exchange.add_feed(CsvBarsFeed(root=..., symbols=[...], start=..., end=...))
exchange.add_feed(IosqlBarsFeed(uri=..., interval="1m", start=..., end=...))
exchange.run()   # 自动进入流式路径，内存 O(单时间步)
```

## 背景

### 当前数据路径不渐进

minbt 当前两条数据路径都会在 `run()` 前把全部数据物化到内存：

1. `set_bars/set_books/set_trades/set_news`：整体转 rows → 按 dt 分组（`Exchange._set_feed`）。
2. `add_feed(feed)`：`DataFeedProtocol.events()` 虽是生成器形态，但
   `Exchange._run_feeds()` → `_materialize_data_feed()` 在 run 前把所有事件合并进
   `grouped` 时间线；随后 `_copy_feeds()` 再深拷贝一份，内存峰值约为 2 倍全量数据。

现有 `BarsReplayFeed` 也一样：`prepare()` 中 `_load_rows()` 一次性 SELECT 全部行。

对 1m K 线全年数据（BTCUSDT 约 52 万行/年），物化路径内存与启动耗时都不可扩展。

### 数据源现状（bn_data_sync 产出）

两类目标数据源已经存在且形态理想：

1. **月度 K 线 CSV 目录**（kline.csv 布局）：
   - 路径 `{root}/{symbol}-{interval}-{YYYY-MM}.csv`，如
     `.../kline.csv/1m/BTCUSDT-1m-2023-01.csv`。
   - 12 列：`open_time, open, high, low, close, volume, close_time,
     quote_volume, count, taker_buy_volume, taker_buy_quote_volume, ignore`。
   - 首行可能为表头（首列 `open_time`），行按 `open_time` 升序，可能混入少量畸形行。
2. **iosql 库**（`kline_{interval}` 表）：
   - 列：`symbol(text), open_time(int ms), open/high/low/close/volume(float),
     close_time(int), volume_quote(float), num_trades(float),
     volume_base_buy(float), volume_quote_buy(float), ignored(text)`。
   - 契约：`pk=(symbol, open_time)`，`partition=duration(open_time, every=1month)`，
     `order_key=open_time`，`symbol_column=symbol`。
   - 查询 API：`db.table(name).query(symbols=..., start=ms, end=ms,
     order_by="open_time")`，支持 `iter_rows(batch_size)` / `iter_batches(batch_size)`
     惰性分批迭代。
   - 注意：iosql `start/end` 是**闭区间**（`>=` 与 `<=`）。

## 设计目标

1. 新增 `CsvBarsFeed`、`IosqlBarsFeed` 两个 feed，事件流惰性产出，不一次性读入全部数据。
2. `Exchange.run()` 支持流式消费：数据到达即分发，内存与回测总时长无关。
3. 用户接口沿用既有心智模型：`exchange.add_feed(feed)`，参数风格对齐 `BarsReplayFeed`
   （symbols / start / end / name）。
4. 策略侧零变化：`on_bars(dt, bars)` 切片语义、价格更新语义与物化路径完全一致。
5. 混用不降级：与 `set_bars`、`BarsReplayFeed` 混用时可自动回退物化路径，行为不破坏。

## 非目标

1. 不支持任意列布局的通用 CSV（`date_key/symbol_key` 自定义映射）；该场景继续用
   `set_bars`（读进内存）。列为后续扩展。
2. 不做 binance HTTP 下载缓存之外的本地缓存补齐；缺月文件仅告警跳过，不自动补数。
3. 不自动补齐缺失 bar、不生成合成行情（延续 data-feed 设计）。
4. 不在本期实现 live feed / 自定义 event_type。
5. 不改变 `BarsReplayFeed` 的物化实现（它已是可用状态，改造无内存收益）。

## 核心决策

### 决策 1：两个 feed 类，共享"行流 → 按 dt 分组"内部层

```text
CsvBarsFeed    ─┐
                ├─→ 行归一化流（按 (dt_ms, symbol) 有序）→ 按 dt 分组 → FeedEvent(bars)
IosqlBarsFeed  ─┘
```

- 两个类只实现"自己的行怎么来"（`_row_stream()` 钩子），分组与事件产出共享。
- event_type 固定 `bars`，payload/prices 语义与 `BarsReplayFeed` 完全一致。

### 决策 2：渐进在 feed 层与 Exchange 层两级实现

- **L1 feed 层**：`events()` 生成器逐 dt 产出，读缓冲有界（CSV 逐行，iosql 一批）。
  Exchange 零改动即可用；但当前物化路径仍会缓冲全部事件，本阶段内存未省。
- **L2 Exchange 流式路径**：`run()` 直接消费生成器，按 dt k 路归并、
  逐 dt 分发后即丢弃，内存 O(单 dt 事件)。这是本设计的内存目标。

### 决策 3：流式路径自动选择 + 显式覆盖

`run()` 的路径选择规则（`streaming` 参数默认 `None`）：

```text
run(streaming=None):
  streaming=True  强制流式：任意数据源都可（set_* 数据包装为逐 dt 事件源）
  streaming=False 强制物化：现有路径，零变化
  streaming=None  自动：
    所有 data feed 声明 streaming 能力 → 流式
    否则                               → 物化（现有路径）
```

- 流式能力声明：feed 类属性 `streaming = True`（缺省 False，`getattr` 探测）。
  新增两个 feed 为 True；`BarsReplayFeed` 保持 False。
- `set_*` 数据在流式模式下包装为内存事件源（grouped 时间线本身有序），
  保证 `run(streaming=True)` 总是可用。
- 自动规则的意义：默认行为对用户透明，且永远不会因混用而出错——只要存在一个
  未声明流式能力的 feed，就退回经过验证的物化路径。

### 决策 4：iosql 命名为 `IosqlBarsFeed`

data-feed 设计预留了 `SqliteBarsFeed`，但本 feed 依赖 iosql 的分区查询契约
（`query(symbols=, start=, end=)`），命名诚实优于通用：**`IosqlBarsFeed`**。
后续若需要通用 SQLite 路径，再单独提供 `SqliteBarsFeed`。

## 用户接口

### CsvBarsFeed

```python
from minbt.data import CsvBarsFeed

exchange.add_feed(CsvBarsFeed(
    root="/media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv/1m",
    symbols=["BTCUSDT"],
    start="2023-01-01",       # 半开区间 [start, end)，arrow/datetime/str
    end="2023-01-03",
))
```

签名：

```python
CsvBarsFeed(
    root,                          # 目录或单个 CSV 文件
    symbols=None,                  # str 或 list[str]；None=目录模式下从文件名解析全部
    start=None, end=None,          # 过滤 [start, end)，缺省不限
    *,
    name=None,                     # feed.name，缺省自动生成
)
```

规则：

1. **目录模式**（root 为目录）：扫描 `{symbol}-*-{YYYY-MM}.csv`，按文件名解析
   symbol 与月份，月份升序逐月加载；缺月文件记一条 warning 并跳过。
2. **单文件模式**（root 为文件）：symbols 缺省从文件名前缀解析（`BTCUSDT-1m-2023-01`
   的首段）；解析失败且未传 symbols 时抛 ValueError。
3. 表头处理：首个非空行若首列不能解析为整数（ms 时间戳）则视为表头跳过；
   空行跳过。
4. 畸形行（列数不足 12 / 数值转换失败）：抛 ValueError 并携带文件名与行号，
   **fail-fast**，不静默跳过（回测正确性优先，与 bn_data_sync 导入时的宽容策略不同）。
5. 行内时间：`open_time` 毫秒 epoch → UTC datetime；区间过滤在行级执行。

### IosqlBarsFeed

```python
from minbt.data import IosqlBarsFeed

exchange.add_feed(IosqlBarsFeed(
    uri="sqlite:///media/lsl/Z1/findata/crypto/binance/future_usdt/kline.csv.iosql",
    interval="1m",
    symbols=["BTCUSDT"],
    start="2023-01-01",
    end="2023-01-03",
))
```

签名：

```python
IosqlBarsFeed(
    uri,                           # iosql Database uri
    interval,                      # 用户概念，推导表名 kline_{interval}
    symbols=None,                  # None = 库中全部 symbols
    start=None, end=None,          # [start, end) 半开区间
    *,
    table=None,                    # 显式覆盖表名（缺省 f"kline_{interval}"）
    batch_size=10_000,             # iter_rows 批大小，内存微调项
    name=None,
)
```

规则：

1. 区间适配：feed 契约是半开区间；向 iosql 查询时 `end` 转为 `end_ms - 1`
   （iosql 为闭区间），保证与 `BarsReplayFeed`、`set_bars` 的区间语义一致。
2. 依赖导入：类内惰性 `from iosql import Database`，ImportError 时给出
   安装指引（对齐 `binance.py` 对 crypto_api 的处理）。
3. 生命周期：`prepare()` 打开 Database 并发起查询（`iter_rows`），`events()`
   消费查询流，`close()` 关闭连接。生成器不会在 `run()` 之外存活。
4. `order_by="open_time"`：iosql 保证同 dt 行相邻；组内按 symbol 排序后产出，
   与物化路径 payload 顺序一致。

### 默认 feed name

1. `csv:bars:{目录名}:{symbols}`，如 `csv:bars:1m:BTCUSDT`。
2. `iosql:bars:{table}:{symbols}`，如 `iosql:bars:kline_1m:BTCUSDT`。
3. name 冲突时用户显式传 `name=...`（延续 data-feed 设计）。

## FeedEvent 与 payload 契约

与现有 `BarsReplayFeed` 一致：

```python
FeedEvent(
    event_type="bars",
    dt=<UTC datetime>,            # open_time 的毫秒 epoch 转换
    data={symbol: {               # OrderedDict，按 symbol 排序
        "dt": dt, "symbol": symbol,
        "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...,
        # 可选：close_time, volume_quote, num_trades,
        #       volume_base_buy, volume_quote_buy（源数据存在才带）
    }},
    prices={symbol: close},       # 每标的收盘价，驱动 broker 最新价
)
```

1. 每根 bar 一个 FeedEvent；多标的同 dt 合并为一个事件的 data dict。
2. `(dt, symbol)` 重复 → ValueError（对齐 `set_bars` 的 require_unique）。
3. `dt` 统一 UTC datetime，不向策略暴露毫秒整数（延续 data-feed 设计第 4 条边界）。

## 渐进加载内部设计

### 行流管道

```text
源级行流（惰性）                 归并/分组                    事件
─────────────────────────    ───────────────────────    ──────────────
CSV: 逐月逐 symbol 文件        月内 heapq.merge            组内按 symbol 排序
     csv.reader 逐行           key=(open_time, symbol)    → yield FeedEvent(dt)
iosql: query.iter_rows        单流，ORDER BY open_time，  同左
       batch_size 一批          按 dt 变化切组
```

公共实现 `_KlineRowFeed`（内部基类，不公开）：

```python
class _KlineRowFeed:
    streaming = True
    event_type = "bars"
    name: str
    # 子类钩子：产出归一化行 {dt: datetime, symbol, open, high, low, close, volume, ...}
    def _row_stream(self) -> Iterator[dict]: ...
    # 共享：按 dt 分组 → FeedEvent
    def events(self) -> Iterable[FeedEvent]: ...
    def prepare(self) -> None: ...
    def close(self) -> None: ...
```

分组实现要点：

1. 维护 `current_dt` + `current_bars`（OrderedDict），行的 dt 变化即产出上一组。
2. 输入必须按 `open_time` 有序（CSV 由归并保证；iosql 由 ORDER BY 保证），
   乱序行抛 ValueError（乱序 = 数据损坏，fail-fast）。
3. 归一化 `dt` 与去重检查逐组进行，`_validate_standard_row` 语义复用。

### CSV 目录模式内存边界

1. 逐月迭代：每月为每个 symbol 打开当月文件（`csv.reader` 惰性），
   `heapq.merge` 多文件流（key=(open_time_ms, symbol)）。
2. 同一时刻打开的文件数 ≤ len(symbols)；内存 ≤ 当月各 symbol 当前行缓冲。
3. 文件句柄在当月结束后全部关闭；跨月天然有序（文件名月份升序迭代）。

### iosql 模式内存边界

1. 单查询流 `iter_rows(batch_size)`：内存 ≈ batch_size 行 + 当前 dt 组。
2. `batch_size` 是用户唯一需要理解的内存微调项（默认 10_000）。

## Exchange 流式 run 路径（L2）

### 数据流

```text
各 feed events() ──tag(dt, 事件类型序, feed 名)── heapq.merge ── 按 dt 收敛 batch ── 分发
```

### 归并键

```python
key = (event.dt, _FEED_ORDER.index(event_type), feed.name)
```

1. `event_type` 序沿用 `_sort_feeds` 的 `_FEED_ORDER = ("bars","books","trades","news")`，
   同 dt 的价格更新与回调顺序与物化路径一致。
2. 每个 feed 的事件必须按 dt 非递减（流式 feed 的契约；`heapq.merge` 输入要求），
   违反在归并处自然暴露为排序错误 → ValueError 明确报错。

### 逐 dt 分发（复用现有语义）

对收敛出的每个 dt batch：

```text
1. 构造每 event_type 的临时 _Feed（per-dt），复用 _merge_payload /
   _merge_event_prices 做冲突与重复校验
2. _update_market_prices(...) → broker.on_new_price
3. _process_brokers_before_callbacks(dt, slices)
4. 逐 feed 回调 strategy.on_{event_type}(dt, slices)
5. strategy._record_broker_history()
6. 丢弃 batch → 进入下一 dt
```

### 生命周期与异常

1. 迭代前逐 feed `prepare()`；`finally` 中逐 feed `close()`，未耗尽的
   `events()` 生成器一并 `.close()`（释放 CSV 句柄 / DB 连接）。
2. 异常传播语义与物化路径相同：抛出即终止 run，不调用 `on_finish`。
3. `on_init` 在首轮分发前调用（与现有路径一致）。

### 行为等价承诺

流式与物化路径在同一数据集上必须满足（列为验收测试）：

1. 策略回调序列 `(dt, event_type, payload)` 完全一致。
2. 权益曲线、持仓记录逐位一致。
3. 价格冲突、重复行等错误的报错时机可能不同（延迟到事件到达），但错误类型与
   消息语义一致。
4. `run()` 可重复调用（feed 每轮重新 `prepare/events/close`）。

## 错误语义

| 错误 | 触发 | 类型 | 修复指引 |
|---|---|---|---|
| start ≥ end | 构造时 | ValueError | 调整区间 |
| CSV 文件缺失 | prepare | FileNotFoundError | 检查 root 与 symbols |
| 表头/列数/数值非法 | 逐行 | ValueError（含文件、行号） | 修复数据源 |
| iosql 依赖缺失 | 构造时 | ImportError + 指引 | 安装 iosql |
| 表契约缺少 symbol_column | prepare | ValueError | 建表时声明 symbol_column |
| 事件乱序（流式归并处） | run | ValueError | 检查数据源顺序性 |
| (dt, symbol) 重复 | 逐事件 | ValueError | 去重数据源 |
| 同 dt 价格冲突 | 逐事件 | ValueError | 排查多 feed 重叠 |

## 内存边界分析

| 路径 | 峰值内存 |
|---|---|
| 现状（set_bars / 物化） | ≈ 2 × 全量数据（grouped + _copy_feeds） |
| 流式 + CSV | 当月各 symbol 单行 + 当前 dt 组 |
| 流式 + iosql | batch_size 行 + 当前 dt 组（batch_size 可调） |
| 策略自身历史 | 策略自行累积，与 feed 无关（既有行为） |

## 测试计划

1. **行归一化单测**：CSV 表头/无表头、畸形行报错、区间过滤、毫秒→UTC datetime。
2. **CSV feed 集成**：临时目录构造多月多 symbol 文件；验证缺月告警、
   (dt,symbol) 重复报错、跨月连续回放顺序正确。
3. **iosql feed 集成**：临时 iosql 库写入样例 → 端到端读取；
   验证 end-1ms 区间适配、symbols 过滤、batch_size 生效。
4. **等价性测试（核心）**：同一小数据集分别经 set_bars / add_feed(物化) /
   run(streaming=True) 运行同一策略 → 权益曲线与回调序列逐位一致。
5. **多 feed 归并顺序**：bars + books + trades 同 dt，断言分发顺序符合 _FEED_ORDER。
6. **可重复 run**：同一 exchange 两次 run 结果一致。
7. **内存基准**：约 10 万行数据，tracemalloc 对比物化 vs 流式峰值。

## 实施计划建议

1. **Phase 1（L1）**：`_KlineRowFeed` 公共层 + `CsvBarsFeed` + `IosqlBarsFeed`，
   在现有物化路径下可用；单测与 feed 集成测试。
2. **Phase 2（L2）**：`Exchange` 流式 run 路径 + `streaming` 声明 + 自动选择规则 +
   等价性/归并顺序/内存基准测试。
3. **Phase 3**：`examples/12_csv_feed.py`、`examples/13_iosql_feed.py`
   （数据路径缺省指向用户 Z 盘目录，文件缺失时自动跳过），导出 `minbt.data` 顶层。

## 开放问题

1. 通用列布局 CSV（date_key/symbol_key 自定义映射）是否纳入本期 —— 建议不做，
   由 `set_bars` 覆盖；如需文件级通用读取再单独立项。
2. iosql 依赖是否进 `pyproject.toml` extras（`minbt[data-iosql]`）—— 建议仅文档
   说明 + 惰性导入，不强制依赖。
3. 流式路径对 `_copy_feeds` 的替代校验（防 feed 内部可变状态跨 run 污染）依赖
   feed 每次 run 重建生成器 —— 已由 prepare/events/close 生命周期保证，无需额外机制。
