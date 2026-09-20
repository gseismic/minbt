# PLAN-042 CSV 与 iosql 渐进式数据 Feed

## 目标

为 minbt 增加面向 `crypto.bn_data_sync` 数据布局的 `CsvBarsFeed` 和
`IosqlBarsFeed`，并让 Exchange 在满足条件时按时间点渐进消费数据，避免在回测开始前
把全量行情物化到内存。

## 设计依据

- `docs/design/csv-iosql-feed-20260920-design.md`
- `minbt/data/feed.py` 的 `FeedEvent` / `DataFeedProtocol`
- iosql v0.3.x：`query(..., order_by=...).iter_rows()` 提供有序流式读取
- `/home/lsl/macbook/pai-studio-fin/library/iosql/examples/13_streaming_ordered_query.py`

## 实施范围

1. 增加共享的 K 线行流与事件分组实现。
2. 增加月度 Binance K 线 CSV Feed。
3. 增加 iosql K 线 Feed，使用有序 `iter_rows(batch_size=...)`。
4. 增加 Exchange 流式运行路径；默认仅对声明支持流式的 Feed 自动启用。
5. 保留现有 `set_*` 和 `BarsReplayFeed` 的物化路径及行为。
6. 增加单元测试、流式等价性测试、资源释放测试和两个使用示例。

## 公共接口

```python
CsvBarsFeed(
    root,
    symbols=None,
    start=None,
    end=None,
    *,
    interval=None,
    name=None,
)

IosqlBarsFeed(
    uri,
    interval,
    symbols=None,
    start=None,
    end=None,
    *,
    table=None,
    batch_size=10_000,
    name=None,
)

Exchange.run(streaming=None)
```

时间范围统一为 UTC 半开区间 `[start, end)`；iosql 查询的闭区间 `end` 转换为
`end_ms - 1`。CSV 默认严格处理缺失文件和非法数据，允许跳过数据必须由显式参数控制。

## 关键不变式

- Feed 事件按 `dt` 非递减输出；流式包装器显式检查乱序。
- 一个 `FeedEvent` 表示一个 distinct `dt`，同一时间点的多个 symbol 合并到同一切片。
- 多 Feed 同时刻按 Feed 注册顺序合并，事件类型仍遵循 `bars/books/trades/news` 顺序。
- 流式路径只保留当前时间点、各 Feed 的前置事件和源端批次缓冲。
- Feed 的文件句柄、iosql Database、查询生成器在正常结束和异常退出时都释放。
- 旧物化路径的公开行为保持不变。

## 验收标准

- CSV 多月、多标的、表头、区间过滤、重复数据和非法行测试通过。
- iosql 数据可以通过有序 `iter_rows` 按批读取，且不调用 `select()` 全量路径。
- 流式与物化路径的策略回调、价格、订单和权益结果一致。
- 流式源未耗尽时即可触发策略回调，证明不是先读完整个数据源。
- 同一 Exchange 可以重复 `run()`，结果一致。
- 现有测试保持通过；新增示例可在数据文件/数据库存在时运行。
