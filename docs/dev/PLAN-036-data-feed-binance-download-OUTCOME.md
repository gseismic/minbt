# PLAN-036 DataFeed Binance 自动下载补充结果

## 完成内容

1. 更新 `docs/design/data-feed-20260701-design.md`，补充内置 Binance 历史数据的下载器适配层说明。
2. 明确参考实现 `BinanceKlineClient` 属于内部下载层，不是用户接口。
3. 明确 `list_symbols()`、`fetch_klines()`、`fetch_recent_klines()`、`fetch_raw_klines()` 的定位与边界。
4. 把 `market` 参数描述调整为产品线/市场特征，并明确第一阶段默认和唯一支持值为 `"futures"`。
5. 将自动下载、分页、重试、节流、落盘明确收敛到 feed 内部实现，用户只感知 `cache_dir` 和时间范围。
6. 更新 `docs/design/README.md`，补充 data-feed 设计稿的阅读入口说明。
7. 补充 Binance 原始字段到 minbt row 的归一化关系，保留 provider-specific 字段但不要求其他 feed 实现。
8. 修正 coverage 语义：成功请求并完成本地事务后即可记录 coverage，包括远端返回 0 行的无数据区间。

## 结论

本次修订没有扩大用户接口面，只是把现有 Binance K 线下载能力补到设计契约里。
设计当前仍保持：

1. `exchange.add_feed(feed)` 是主入口。
2. 第一阶段只做 replay feed。
3. 自动下载是 feed 的内部能力，不单独暴露 `DataStore`。
4. Binance 第一阶段对齐参考代码，只支持 futures K 线；spot 后续单独扩展。

## 未实施内容

1. 未修改代码。
2. 未实现 Binance 下载器。
3. 未实现 SQLite 缓存。
