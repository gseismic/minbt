# PLAN-048 简单用户门面与通用 Bar 存储实施计划

## 目标

在保持 Exchange/Broker 内核正确性的前提下，降低普通用户的认知负担，并落实 Bar 的通用语义：

1. 普通 Kline 用户只需要 `set_bars()`、`Broker()` 和 `run()`。
2. 估值规则仍由 Broker 负责，默认规则可用但不能静默产生歧义结果。
3. 普通自定义 Feed 不必声明全部回放能力；高性能来源仍可声明渐进回放。
4. CSV、iosql 既支持现有 Kline 数据，也提供通用 Bar 存储读取路径。
5. Kline 行解析与通用 Bar 模型、通用 Bar 读取实现分离。

## 设计决定

- 用户常用估值配置使用 `mark_price="kind.field"` 简写；精确 Feed 路由和 callable 保留为高级能力。
- 默认估值为 `kline.close`；缺失价格的错误必须给出可执行的配置提示。
- 简单 Feed 采用安全默认值：支持全量预加载、不假设有序、不默认支持渐进回放、可重复读取。
- 通用 CSV Bar 文件使用 `dt,symbol,kind,data` 最小信封，`data` 为 JSON；通用 iosql 表使用
  `dt,symbol,kind,data`，`dt` 为毫秒时间戳。
- Binance Kline 外部格式使用明确的 `BinanceKlineCsvFeed`、`BinanceKlineIosqlFeed` 和
  `binance.BinanceKlineFeed`；通用入口命名为 `CsvBarFeed`、`IosqlBarFeed`。
- 不引入 Storage、Schema、Adapter 层级；具体读取类直接产生 `Bar`。

## 实施范围

1. 更新设计稿和 README/使用指南的分层叙事。
2. 实现 Broker 的 `mark_price` 简写、默认与错误提示。
3. 实现 `SimpleFeed` 及 Exchange 的能力默认值。
4. 抽出通用 Bar 行转换逻辑，保留 Kline 专用行解析。
5. 实现通用 CSV/iosql Bar Feed，并增加可运行示例。
6. 更新 API 契约、回放、Broker、数据源和示例测试。
7. 运行完整测试、静态检查、示例和独立 review，生成结果文档。

## 非目标

- 不实现实时模式。
- 不为 OrderBook 增量快照增加恢复协议。
- 不保留旧接口兼容层。
