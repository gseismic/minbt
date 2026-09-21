# minbt CSV / iosql 渐进加载工作交接

## 交接目的

本文件用于交接当前 `minbt` 仓库中 CSV / iosql K 线渐进加载工作的状态。
目标是让下一位 Agent 无需重新阅读全部历史对话即可继续实现、修复和验收。

## 当前仓库状态

- 工作目录：`/home/lsl/macbook/pai-studio-fin/library/minbt`
- 当前分支：`main`
- 当前 HEAD：`c4e0cc0 Review 修正：arrow 时间兼容、缺月告警、CSV end 过滤优化（PLAN-042）`
- 上一个功能提交：`2d44b6e 新增 CSV / iosql 渐进式数据 Feed（PLAN-042）`
- 当前用户新增的 Review 文件：`docs/review/review-20260920-round6.md`
- 本交接文件由本次工作新增；不要覆盖用户已有的 Review 内容。
- 尚未创建 `PLAN-043`，也没有开始修复第六轮 Review 提到的遗留问题。

本项目约定：代码设计文档放在 `docs/design`，计划和结果放在 `docs/dev`，文档与注释使用中文；编辑文件使用 `apply_patch`；除非用户明确要求，不要擅自提交代码。

## 已完成工作：PLAN-042

设计、计划和结果文件：

- [设计稿](docs/design/csv-iosql-feed-20260920-design.md)
- [实施计划](docs/dev/PLAN-042-csv-iosql-streaming-feed.md)
- [实施结果](docs/dev/PLAN-042-csv-iosql-streaming-feed-OUTCOME.md)

### 数据 Feed

- `minbt/data/bars.py`
  - `_KlineRowFeed`：把有序行流按 `dt` 聚合为 `FeedEvent`。
  - 负责 UTC 时间转换、毫秒时间转换、标准 K 线字段归一化、同一 `(dt, symbol)` 去重。
  - `streaming = True`。
- `minbt/data/csv.py`
  - `CsvBarsFeed`：读取 `crypto.bn_data_sync` 的月度 Binance CSV。
  - 月内使用 `csv.reader` + `heapq.merge` 合并多个 symbol 文件；按时间逐行读取。
  - 支持表头、半开区间 `[start, end)`、乱序检测、畸形行报错、缺月 warning。
- `minbt/data/iosql.py`
  - `IosqlBarsFeed`：使用 `table.query(order_by="open_time").iter_rows(batch_size=...)`。
  - 使用最新 iosql 的有序流式查询能力，不调用 `select()` 全量路径。
  - iosql 的闭区间 `end` 转换为 minbt 的半开区间：`end_ms - 1`。
  - Database、查询生成器在正常结束和异常退出时释放。
- `minbt/data/__init__.py`
  - 顶层导出 `CsvBarsFeed` 和 `IosqlBarsFeed`。

### Exchange 流式路径

`minbt/exchange.py` 新增：

- `_can_stream_data_feeds()`：只有没有 `set_*` 物化数据、且所有 data feed 都声明 `streaming=True` 时才自动流式。
- `_checked_stream()`：检查每个 Feed 的事件 `dt` 非递减，并附加归并键。
- `_run_streaming()`：多个 Feed 按 `(dt, event_type 顺序, Feed 注册顺序)` 做 k 路归并，逐时间点分发后丢弃临时数据。
- `run(streaming=None)`：
  - `None`：自动选择；
  - `True`：要求全部 data feed 支持流式且没有 `set_*` 数据，否则抛 `ValueError`；
  - `False`：强制使用原有物化路径。

旧的 `set_bars`、`set_books`、`set_trades`、`set_news`、`BarsReplayFeed` 物化路径没有被改造成流式，混用时自动回退物化路径。

## 最新验证结果

执行命令：

```bash
/home/lsl/miniconda3/bin/python -m pytest -q
```

结果：`185 passed, 1 failed`。

唯一失败是既有测试：

```text
tests/test_exchange.py::test_exchange_updates_full_bar_before_strategy_callbacks
```

原因是当前安装了 pyta2，`Strategy.get_hist_equity()` 返回 NumPy 数组，测试直接与 Python list 比较，触发 NumPy 的 ambiguous truth value。该失败在 PLAN-042 改动前已经存在，不是 CSV / iosql 功能引入的。可以在后续修复测试断言，例如转为 `list(...)` 或使用 NumPy 专用断言。

已验证的其他内容：

- CSV 多 symbol、表头/无表头、区间过滤、乱序检查通过。
- iosql 真实数据库读取通过，`Table.select` monkeypatch 防回退测试通过。
- 流式与物化回调/价格/权益等价性测试通过。
- 流式源未耗尽即可触发策略回调。
- 真实数据示例曾运行成功：CSV 与 iosql 均为 `final_equity=10053.92`、`bar_count=2880`。
- 第六轮 Review 实测 100k bars：流式峰值约 `38.3 MB`，物化约 `180.1 MB`；流式耗时约慢 40%。

示例：

- `examples/12_csv_feed.py`
- `examples/13_iosql_feed.py`

## 当前未完成事项

详细报告见 [第六轮 Review](docs/review/review-20260920-round6.md)。其中必须优先处理的是两个 P2 问题。

### P2-1：数据不存在时可能静默空回测

目前以下情况可能正常结束但产生 0 个事件或缺少部分 symbol：

- CSV 请求的部分 symbol 没有文件；
- CSV 请求的 interval 与实际文件不匹配；
- CSV 时间区间与文件没有交集；
- iosql 的 `interval/table` 拼错；
- iosql 请求的 symbol 不存在。

这会让用户误以为策略没有信号，而不是数据没有加载。建议在 `PLAN-043` 中明确策略：

1. 请求 symbol 至少应命中一个文件/一行，否则 `FileNotFoundError` 或明确的 `ValueError`；
2. iosql 目标表/契约不可用时转换为指向 `interval` / `table` 参数的错误；
3. 对显式时间区间完全无数据的回测，至少给出明确异常或可见告警；
4. 补齐对应单元测试。

### P2-2：warning 被默认 logger 策略隐藏

`minbt/logger.py` 当前默认 `logger.disable("minbt")`。因此 `CsvBarsFeed.prepare()` 的缺月 warning 默认不可见，数据完整性告警实际近似静默。

需要先做语义决策：

- 推荐数据完整性问题默认 fail-fast；或
- 调整默认日志策略，使 WARNING/ERROR 可见，同时保持 DEBUG/INFO 可关闭。

选定后同步 `csv.py`、`logger.py`、设计稿、README 和测试。

## P3 / 文档与测试遗留

这些不是当前渐进加载主功能的阻塞项，但建议一并登记到 `PLAN-043`：

- 设计稿仍有与最终实现矛盾的“`streaming=True` 包装 set_* 数据”描述；
- 设计稿示例缺文件行为与实际示例的 `SystemExit` 不完全一致；
- 多 event-type 流式归并顺序只有手工验证，缺少自动回归测试；
- 100k 内存/耗时基准只有 Review 记录，尚无正式测试或 README 性能取舍说明；
- `bars.py` 支持 arrow 时间对象，但 `binance.py` 的 `BarsReplayFeed` 仍不支持，两个 Feed 的时间参数行为不一致；
- `IosqlBarsFeed` 的错误信息仍可能来自 iosql 内部，未明确指向 `interval/table`；
- `batch_size=None` 的错误类型/消息可以规范化。

第六轮 Review 同时复测了前几轮与本次目标无直接关系的 broker/strategy 问题，例如 pending 限价单与已关闭 portfolio 的崩溃、pyta2 position history、`get_positions()` 泄漏、交易时段时区语义等。除非用户扩大范围，不要把这些问题混入 CSV / iosql 修复实现；应在 Review 报告中单独跟踪。

## 推荐下一步

1. 新建 `docs/dev/PLAN-043-review-fixes.md`，不要复用已完成的 PLAN-042 编号。
2. 先确定 P2-1/P2-2 的 fail-fast 与 warning 语义。
3. 实现 CSV / iosql 数据存在性校验，补齐空数据、缺 symbol、错误 table/interval 测试。
4. 修正文档中的流式边界、示例行为和性能说明。
5. 视是否要保持全量测试绿色，修复既有 NumPy list 测试断言；不要改变生产 API 语义来掩盖该测试问题。
6. 运行：

   ```bash
   /home/lsl/miniconda3/bin/python -m pytest -q
   python -m compileall -q minbt examples tests
   git diff --check
   ```

7. 代码 review 后生成 `docs/dev/PLAN-043-review-fixes-OUTCOME.md`，再根据用户要求决定是否提交。

## 重要实现约束

- iosql 的 `order_by` 流式问题已经由最新 iosql 修复；不要恢复成 `select()`，应继续使用 `query(..., order_by=...).iter_rows()` 或 `iter_batches()`。
- 不要把 `set_*` 伪装成低内存流式源；它们本身已先物化。当前显式 `streaming=True` 拒绝这种混合场景是有意设计。
- Feed 的时间范围统一为 UTC 半开区间 `[start, end)`。
- 不要覆盖用户的 `docs/review/review-20260920-round6.md` 或其他未提交修改。
- 所有新增/修改文档与注释使用中文；提交消息使用中文。
