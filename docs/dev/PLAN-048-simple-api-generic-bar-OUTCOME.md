# PLAN-048 实施结果：简单用户门面与通用 Bar 存储

## 结果

本计划已完成。普通 Kline 用户仍然只需要 `set_bars()`、`Broker()` 和 `run()`；
Exchange/Broker 内核保留显式的时间批次、Feed 优先级和估值规则，避免由入口函数静默猜价。

## 主要变更

### 1. 降低公开接口认知负担

- `Broker()` 默认使用 `kline.close`。
- 常用估值来源使用 `mark_price="kind.field"`，例如 `"orderbook.mid"`、`"trade.price"`。
- 精确 Feed 路由、聚合函数和缺失价格策略仍可配置，但作为进阶能力保留在 Broker 内部边界。
- 缺失估值价格的错误会指出当前来源，并给出可直接修改的 `mark_price` 示例。
- `SimpleFeed` 只要求名称和 `events()`；能力属性有安全默认值，已知有序来源仍可声明渐进回放能力。

### 2. 恢复 Bar 的通用语义

- `Bar` 只要求 `dt`、`symbol`、`kind`、`data`，不强制 OHLCV。
- Kline、OrderBook、Trade、Price 和自定义数据均可作为 Bar。
- 自定义 kind 通过 `Strategy.on_bar(dt, bar)` 接收，不为每种数据增加新的 Exchange API。
- 自定义 Bar 的回调排序明确位于 Trade 之后、News 之前，保持公开回调顺序稳定。
- `News` 保持独立事件，不默认参与估值或收益计算。
- Kline 行解析移动到 `minbt/data/kline.py`；通用 Bar 模型和通用读取逻辑不再依赖 Kline 字段。

### 3. CSV / iosql 的最小通用存储入口

- 新增 `CsvBarFeed` 和 `IosqlBarFeed`，统一读取 `dt,symbol,kind,data` 信封。
- `data` 使用 JSON 表示，读取后保留原始 kind 和载荷，不解释为 OHLCV。
- Binance Kline 外部格式使用明确的 `BinanceKlineCsvFeed`、`BinanceKlineIosqlFeed` 和
  `binance.BinanceKlineFeed`；通用入口保持为 `CsvBarFeed`、`IosqlBarFeed`。
- 不引入 `Storage`、`Schema`、`Adapter` 层级。

### 4. Exchange 正确性与性能边界

- 同一时间点仍先收齐完整 `TimeBatch`，Broker 再批量更新账户，消除跨 symbol 更新顺序对全仓估值的影响。
- Feed 优先级只决定处理顺序；同一时间、同一数据族、同一 symbol 的同优先级来源会 Warning，
  不静默覆盖。
- 全量预加载适合小数据和速度优先；渐进回放适合有序 CSV/iosql，Exchange 只保留来源头部、
  当前时间批次和底层读取缓冲。
- `ReplayCursor`、`TimeBatch` 继续是 Exchange 内部概念，普通用户无需创建。

## 验证

- 全量测试：`201 passed`。
- 定向测试：`64 passed`。
- `ruff check minbt examples/15_generic_bar_storage.py`：通过。
- `git diff --check`：通过。
- `python -m compileall -q minbt tests examples`：通过。
- `examples/14_exchange_replay_modes.py`：运行成功。
- `examples/15_generic_bar_storage.py`：运行成功，验证通用 OrderBook/Price Bar 回放和 Broker 估值。

## Review 结论

当前设计在“普通路径少配置”和“内核不隐式猜价”之间收敛：

- 普通用户不需要理解 Feed 能力位、`TimeBatch` 或精确来源路由。
- 多来源冲突、估值字段缺失和回放能力不满足时仍显式报错或 Warning。
- Bar 的数据语义与存储形式分离，Kline 不再充当通用 Bar 的隐含定义。

未扩展实时模式，也未引入 Storage/Schema/Adapter 抽象；这些都符合当前 mini 回测范围。
