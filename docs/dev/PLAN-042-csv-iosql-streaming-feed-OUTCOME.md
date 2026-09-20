# PLAN-042 结果：CSV 与 iosql 渐进式数据 Feed

## 状态

已完成。实施过程由 codex（会话 01a0bc86）完成主体，opencode（glm）接续补齐验收测试与结果文档。

## 实施内容

### 新增文件

| 文件 | 说明 |
|---|---|
| `minbt/data/bars.py` | 共享层：`_KlineRowFeed`（行流 → 按 dt 聚合 → FeedEvent）、`normalize_symbols`、`to_utc_datetime`、ms/datetime 转换 |
| `minbt/data/csv.py` | `CsvBarsFeed`：crypto.bn_data_sync 月度 CSV 布局，逐月打开文件、`heapq.merge` 按 `(open_time, symbol)` 多路归并 |
| `minbt/data/iosql.py` | `IosqlBarsFeed`：iosql `query(..., order_by="open_time").iter_rows(batch_size)` 有序流式查询 |
| `tests/test_streaming_feeds.py` | 9 个测试：CSV 增量读取、乱序拒绝、Exchange 流式提前分发、iosql 不走 `select()`、流式/物化等价性、重复 run 一致性、streaming 参数边界 |
| `examples/12_csv_feed.py` | CSV 渐进加载示例（`MINBT_CSV_ROOT` 可覆盖，缺省指向 Z 盘真实数据） |
| `examples/13_iosql_feed.py` | iosql 渐进加载示例（`MINBT_IOSQL_URI` 可覆盖） |
| `docs/design/csv-iosql-feed-20260920-design.md` | 设计稿 |

### 修改文件

| 文件 | 变更 |
|---|---|
| `minbt/exchange.py` | 新增 `_run_streaming()` 流式运行路径：各 feed 事件按 `(dt, 事件类型序, 注册序)` k 路归并，逐 dt 分发后丢弃，内存 O(单 dt)；`run(streaming=None)` 三态参数与自动选择规则；`finally` 中统一释放生成器与 feed 资源 |
| `minbt/data/__init__.py` | 导出 `CsvBarsFeed`、`IosqlBarsFeed` |
| `tests/test_api_contract.py` | `Exchange.run` 签名契约更新为 `["streaming"]` |
| `README.md` | 新增"渐进读取 CSV / iosql K 线"章节与示例列表 |

## 公共接口（最终）

```python
CsvBarsFeed(root, symbols=None, start=None, end=None, *, interval=None, name=None)
IosqlBarsFeed(uri, interval, symbols=None, start=None, end=None, *, table=None, batch_size=10_000, name=None)
Exchange.run(streaming=None)   # True 强制流式 / False 强制物化 / None 自动
```

- 时间区间统一为 UTC 半开区间 `[start, end)`；iosql 闭区间由 Feed 内部转换为 `end_ms - 1`。
- 自动规则：仅当全部 data feed 声明 `streaming=True` 且无 `set_*` 数据时走流式；否则回退物化路径。
- 旧物化路径（`set_bars` / `add_feed` 物化 / `BarsReplayFeed`）行为不变。

## 验收结果

| 验收项 | 结果 |
|---|---|
| CSV 多月、多标的、表头、区间过滤、重复/非法行 | 通过 |
| iosql 有序 `iter_rows` 按批读取，不调用 `select()` | 通过（monkeypatch 断言） |
| 流式与物化路径回调序列、价格、订单、权益一致 | 通过（`test_streaming_matches_materialized_set_bars`） |
| 流式源未耗尽即触发策略回调 | 通过（probe feed 断言） |
| 同一 Exchange 重复 `run()` 结果一致 | 通过（流式与物化两条路径均验证） |
| 现有测试保持通过 | 通过（183 passed） |
| 示例在真实数据上运行 | 通过（codex 会话中已实测：CSV `final_equity=10053.92, bar_count=2880`） |

## 测试说明

- `tests/test_exchange.py::test_exchange_updates_full_bar_before_strategy_callbacks`
  在基线（本次改动前）即失败，原因是 `get_hist_equity()` 返回 numpy 数组与
  list 比较抛 `ValueError`，与本计划无关，遗留待后续处理。
- 事件乱序防护为两级：feed 层（`_KlineRowFeed` 行级 + `CsvBarsFeed` 文件内行序）
  与 Exchange 层（`_checked_stream` 归并前检查）。

## Review 修正（实施后第二轮 review 发现并修复）

| 问题 | 处理 |
|---|---|
| `to_utc_datetime` 用 `callable(value.datetime)` 判断 arrow，但 arrow 的 `.datetime` 是 property，arrow 对象直接抛 TypeError | 修复：改按 `isinstance(.datetime, datetime)` 判断；新增 arrow start/end 测试 |
| 设计稿承诺"缺月文件记 warning 并跳过"未实现，缺月数据会静默跳过 | 实现：`CsvBarsFeed.prepare` 按 `[start, end)` 推导期望月份（缺省时按已发现月份首尾）检测空洞并 `logger.warning`；新增测试 |
| CSV 行级 end 过滤用 `continue` 逐行扫描到文件尾 | 优化：文件内已保证升序，越过 end 直接 `break` |
| 设计稿决策 3（`streaming=True` 包装 set_* 数据）与实现（抛 ValueError）不一致 | 更新设计稿记录最终决策（依据 PLAN-042 简化） |

## 遗留事项

1. 基线失败的 `get_hist_equity()` numpy 比较问题（与本计划无关）。
2. 通用列布局 CSV（`date_key/symbol_key` 自定义映射）未纳入本期，继续由 `set_bars` 覆盖。
3. iosql 依赖未进 `pyproject.toml` extras，保持惰性导入 + 文档说明。
