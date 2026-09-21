# PLAN-049 Kline 专用 Feed 命名与通用 Bar 分层修复

## 背景

`Bar` 是通用市场观测，但当前 `CsvBarsFeed(_KlineRowFeed)` 和 `IosqlBarsFeed(_KlineRowFeed)`
使用了看似通用的 `Bars` 名称，实际读取的是 Binance Kline 专用格式，容易让用户误以为 CSV/iosql
中的 Bar 都必须是 Kline。

## 设计决定

1. `CsvBarFeed`、`IosqlBarFeed` 是通用存储入口，只读取 `dt,symbol,kind,data`，不解释字段。
2. Binance Kline 外部格式使用明确的专用入口：
   - `BinanceKlineCsvFeed`
   - `BinanceKlineIosqlFeed`
   - `binance.BinanceKlineFeed`
3. 内部 `_KlineRowFeed` 可以继续存在，因为它只负责解析 Kline 外部行格式；它不属于通用 Bar 模型。
4. 不保留 `CsvBarsFeed`、`IosqlBarsFeed`、`BarsReplayFeed` 的兼容别名，避免继续暴露错误语义。
5. `Exchange.set_bars()` 继续作为普通 Kline 行数据的最短入口，但文档明确它是 Kline 便利入口，
   不代表 Bar 只有 Kline 一种。

## 实施范围

- 重命名 Kline 专用类、默认 Feed 名称、错误信息和导出。
- 更新 README、使用技能、当前设计稿、示例及测试。
- 增加通用 Feed 与 Kline 专用 Feed 的 API 分层回归测试。
- 运行全量测试、示例、静态检查并生成结果文档。

## 非目标

- 不改变 Bar、News、TimeBatch、Broker 估值或回放算法。
- 不引入 Storage、Schema、Adapter 新抽象。
