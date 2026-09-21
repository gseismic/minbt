# PLAN-047 Exchange 回放与通用 Bar 实施结果

## 状态

已完成。当前实现与 `docs/design/exchange-20260921-replay-modes.md` 的最小设计一致。

## 已完成内容

### 数据模型与来源

- 新增只读 `Bar` 和 `News`。
- `Bar` 只要求 `dt`、`symbol`、`kind`、`data`，Kline、OrderBook、Trade、Price 和自定义
  数据不共享 OHLCV 强制字段。
- `data` 递归冻结常见容器；时间统一为 UTC 毫秒精度；无效时间、空 symbol 和空 kind 明确报错。
- CSV、iosql、Binance Feed 直接产生 `Bar`；内存入口使用同一模型。
- 没有引入 Storage、Schema 或 Adapter 层。

### Exchange 回放

- `Exchange` 只负责来源读取、时间排序、同一时间批次收集、Feed 顺序和策略分发。
- `ReplayCursor`、`TimeBatch`、`BatchItem` 作为内部回放结构。
- 支持 `load_mode="auto"`、`"preload"`、`"incremental"`。
- 有序来源使用多路归并；无序来源在全量预加载模式下排序。
- 同一时间点按事件族、`feed_priority`、注册顺序和来源序号稳定排序。
- 同优先级 Feed 在同一时间、同一事件族、同一 symbol 真正重叠时 Warning。
- Kline 和 OrderBook 的同一来源重复快照报错；Trade 允许同一时间多个事件。
- 正常结束和异常路径都会尝试关闭来源及迭代器，关闭异常不会覆盖原始业务异常。

### Broker 与账户更新

- Exchange 不从 `close`、`mid` 或 `last` 猜测价格。
- Broker 支持 `(kind, field)`、`(feed_name, kind, field)` 和 callable 三种估值来源。
- 多候选价格默认报错，也可显式选择 `first`、`last` 或自定义聚合函数。
- Broker 每个 `TimeBatch` 只批量更新一次所有 Portfolio，再处理挂单和退出条件。
- News 默认不更新市场价格、不参与浮动盈亏。

### 文档、例子和测试

- 更新 README、使用指南、设计索引和当前设计稿。
- 新增 `examples/14_exchange_replay_modes.py`，覆盖自定义 Price Bar、Feed 优先级和显式估值来源。
- 删除旧回放接口测试，新增回放模式、Bar/News、优先级、资源生命周期、Broker 批量估值和 iosql
  实际读取测试。

## 验证结果

```text
/home/lsl/miniconda3/bin/python -m pytest -q
193 passed in 20.90s

ruff check minbt
All checks passed!

git diff --check
通过

/home/lsl/miniconda3/bin/python examples/14_exchange_replay_modes.py
final_equity=10000.12
mark_price=101.20
```

## 当前边界

- 实时模式尚未实现，`stream` 保留给未来实时接口。
- 当前 Binance `BarsReplayFeed` 在准备阶段读取缓存结果，默认走全量预加载；CSV 和 iosql
  支持渐进回放。
- OrderBook 当前按完整快照处理，不处理需要序号、校验和及恢复的增量盘口。
- 按开发阶段约定，不保留旧事件包装、旧历史读取参数和旧的 Exchange 隐式估值行为的兼容层。
