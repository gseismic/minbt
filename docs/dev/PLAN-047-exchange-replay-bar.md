# PLAN-047 Exchange 回放与通用 Bar 实施

## 目标

按 `docs/design/exchange-20260921-replay-modes.md` 落地新的最小数据模型和历史回放流程。
当前处于开发阶段，不保留旧事件包装、历史读取参数或 Exchange 直接提取价格的兼容层。

## 交付范围

1. 新增只读 `Bar` 和 `News` 数据模型。
2. 让 Kline、OrderBook、Trade、Price 和 Custom 都通过 `Bar.kind` 表达。
3. 将 CSV、iosql 和内存数据实现为具体历史 Feed，不引入 Storage、Schema 或 Adapter。
4. 在 Exchange 内部实现 `ReplayCursor` 和 `TimeBatch`。
5. 实现全量预加载、渐进回放和 `load_mode=auto/preload/incremental`。
6. 使用多路归并保证全局时间顺序和同一时间批次完整收集。
7. 将估值价格选择和批量市场状态更新收敛到 Broker。
8. Feed 优先级只影响分发顺序，同优先级重叠时发出 Warning。
9. 更新策略回调、数据 Feed、公开导出、例子和测试。
10. 完成代码 review、性能/生命周期检查和结果文档。

## 主要接口

```python
exchange.set_bars(rows)
exchange.set_books(rows)
exchange.set_trades(rows)
exchange.set_news(rows)
exchange.add_feed(feed, feed_priority=0)
exchange.add_strategy(strategy)
exchange.run(load_mode="auto")
```

```python
broker = Broker(
    initial_cash=10_000,
    mark_price_source=("kline", "close"),
)
```

Feed 的 `events()` 直接产生 `Bar | News`；`ReplayCursor` 和 `TimeBatch` 不作为用户构造对象。

## 验证要求

- 全量预加载与渐进回放在相同输入下事件、订单、权益和持仓结果一致。
- 同一 `dt` 的多个来源先进入一个完整 `TimeBatch`，Broker 每个 `dt` 只批量推进一次。
- Exchange 不读取 `close`、`mid`、`last` 作为隐含估值价格。
- OrderBook、Trade、Price 和自定义 Bar 不强制 OHLCV。
- News 不参与默认估值。
- Feed 乱序、重复、能力不支持和资源释放异常有明确测试。
- 运行完整测试和例子，完成独立 review 后生成 `PLAN-047-exchange-replay-bar-OUTCOME.md`。
