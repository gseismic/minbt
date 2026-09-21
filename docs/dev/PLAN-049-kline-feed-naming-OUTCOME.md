# PLAN-049 Kline 专用 Feed 命名与通用 Bar 分层修复结果

## 状态

已完成。

## 变更

- 通用存储入口保持为 `CsvBarFeed` 和 `IosqlBarFeed`，只读取 `dt,symbol,kind,data`，不解释
  Kline、OrderBook 或其他 kind 的字段。
- `CsvBarsFeed` 重命名为 `BinanceKlineCsvFeed`。
- `IosqlBarsFeed` 重命名为 `BinanceKlineIosqlFeed`。
- `binance.BarsReplayFeed` 重命名为 `binance.BinanceKlineFeed`。
- 旧的歧义名称不再导出，也不保留兼容别名，避免用户继续把 Kline 专用格式误认为通用 Bar 存储。
- 内部 `_KlineRowFeed` 保留为 Kline 外部行格式解析器；它只负责转换输入格式，不改变 `Bar` 的
  通用语义。
- 更新 README、使用技能、当前设计稿、CSV/iosql 示例及 API/数据源测试。

## 验证

- 全量测试：`202 passed`。
- 定向测试：`40 passed`。
- `examples/12_csv_feed.py`：运行成功，`bar_count=2880`。
- `examples/13_iosql_feed.py`：运行成功，`bar_count=2880`。
- `examples/15_generic_bar_storage.py`：运行成功，验证通用 OrderBook/Price Bar。
- Binance 示例使用离线替代 Feed 的测试通过；真实 API 是否可用取决于 Binance 地区限制和网络环境。
- `ruff check minbt`、`compileall`、`git diff --check` 通过。

## 设计结论

现在公开接口按“数据语义”和“外部文件格式”分层：

```text
Bar                         通用市场观测
CsvBarFeed / IosqlBarFeed   通用 Bar 存储
BinanceKline*               Binance Kline 外部格式
```

这样保留了 Kline 数据源的读取能力，同时不再让 `Bars` 这个通用名称暗示所有 Bar 都是 Kline。
