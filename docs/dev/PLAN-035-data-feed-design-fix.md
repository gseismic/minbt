# PLAN-035 DataFeed 设计修正

## 背景

`docs/design/data-feed-20260701-design.md` 已确定 `exchange.add_feed(feed)` 作为自动下载、缓存复用和未来实时数据的统一入口，但 review 发现若直接落地会有几个边界不清：

1. 当前 `Exchange.run()` 是预聚合时间线，不兼容阻塞无限实时 feed。
2. `set_bars(...)` 和 `add_feed(...)` 双路径并存时，合并规则未定义。
3. `dt` 对外类型未规范，可能因数据来源不同导致策略代码不稳定。
4. `callback`、`priority`、`is_live` 等字段暴露过多，和最简目标不一致。
5. 自定义事件、价格冲突、SQLite coverage、Binance 分页等实现约束需要提前定义。

## 目标

1. 将第一阶段明确收敛为 replay feed，不实现 live feed。
2. 明确第一阶段 `add_feed` 可以物化 replay events，并合并进现有时间线模型。
3. 规范 `FeedEvent.dt` 对外类型。
4. 去掉公开 `callback` 和 `priority` 字段，降低 DataFeed 契约面。
5. 明确价格冲突、同 event_type 多 feed 合并、自定义事件边界。
6. 补充 SQLite coverage merge、refresh、source 命名和 Binance 分页约束。

## 非目标

1. 不实施代码。
2. 不设计完整实时运行时。
3. 不引入公开 `DataStore`。
4. 不让 DataFeed 成为通用数据平台。

## 实施步骤

1. 重写 `docs/design/data-feed-20260701-design.md`。
2. 保留 `exchange.add_feed(feed)` 和 `set_xx(...)` 的关系。
3. 在文档中区分第一阶段 replay 模型和后续 live 目标模型。
4. 更新自审结果并生成 OUTCOME。
