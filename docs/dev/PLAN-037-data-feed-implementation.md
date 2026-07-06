# PLAN-037 DataFeed 实施

## 背景

当前设计已经明确：

1. `exchange.add_feed(feed)` 是自动下载、缓存复用和未来实时数据的统一入口。
2. 第一阶段只做有限 replay feed。
3. 加密货币领域先支持 Binance futures K 线。
4. 用户只需要传 `symbols`、`interval`、`start`、`end`、`cache_dir`，不直接操作 SQLite 或下载器。

当前代码还只有 `set_bars/set_books/set_trades/set_news`，没有 `minbt.data` 包，也没有 `Exchange.add_feed(...)`。

## 目标

1. 实现 `FeedEvent` 和 replay feed 基础契约。
2. 实现 `Exchange.add_feed(feed)`，把 finite replay feed 物化进现有时间线。
3. 实现 `minbt.data.binance.BarsReplayFeed`，支持 Binance futures K 线自动下载、SQLite 缓存和复用。
4. 在 `examples/` 增加加密货币 K 线上手示例。
5. 补充测试覆盖核心用户路径和缓存行为。

## 非目标

1. 不实现 live feed。
2. 不暴露公开 DataStore。
3. 不支持 Binance spot。
4. 不做复杂行情修复、补 bar 或队列撮合。

## 实施步骤

1. 新增 `minbt/data/feed.py`、`minbt/data/binance.py` 和包导出。
2. 修改 `minbt/exchange.py`，增加 `add_feed` 和 feed events 物化合并。
3. 增加 `tests/test_data_feed.py`。
4. 增加 `examples/11_crypto_binance_feed.py`。
5. 运行相关测试并生成 OUTCOME。
