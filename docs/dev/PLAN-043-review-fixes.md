# PLAN-043：正确性 Review 修复

## 背景

第六轮全量 Review 复测确认了三组会影响回测可信度的问题：

1. 子 portfolio 被 `close_portfolio()` 删除后，其 pending 限价单仍留在 Broker 中；后续价格触发订单时会因为 portfolio 已不存在而中断整个回测。
2. `Strategy` 历史查询的返回类型和缺失 symbol 行为随可选依赖 `pyta2` 是否安装而变化，当前全量测试在安装 pyta2 时有 1 个失败。
3. CSV / iosql Feed 对缺失 symbol、错误 interval/table 和无交集时间区间可能静默地产生空回测；CSV 月份空洞只写入默认关闭的日志。

minbt 的目标是以简单接口提供可信的回测结果。上述问题优先级高于继续扩展新功能，本计划先收紧状态不变式和数据错误语义。

## 用户接口决策

### `Broker.close_portfolio()`

- 只有在持仓关闭计划通过预检并执行成功后，才取消该 portfolio 的 pending 订单。
- portfolio 没有持仓时，调用仍视为成功关闭：先取消其 pending 订单，再删除非 `main` portfolio。
- `main` portfolio 不删除，但成功调用 `close_portfolio("main")` 同样取消其 pending 订单。
- 被取消的原订单转为 `canceled`，并清理 `_pending_order_ids` 与 `_pending_exit_params`，保证不存在指向已删除 portfolio 的活动订单。
- 预检失败时不取消 pending 订单，保持关闭操作的原子边界。

### `Strategy` 历史查询

- `get_hist_equity()` 和 `get_hist_position_sizes(symbol)` 始终返回 Python `list`，不把内部 pyta2 / NumPy 存储类型泄漏到用户接口。
- 从未交易过的 symbol 返回与历史长度相同的全零列表，与无 pyta2 路径一致。
- pyta2 继续作为内部高效存储，不改变记录阶段的性能路径。

### CSV / iosql Feed 缺数据

- 用户显式请求的每个 symbol 必须在指定 interval/table 和 `[start, end)` 范围内至少存在一行数据，否则在产生第一个事件前抛出包含缺失 symbol 的明确异常。
- CSV 中请求 symbol 完全没有匹配文件时抛 `FileNotFoundError`；有文件但指定区间无数据时抛 `ValueError`。
- CSV 根据时间边界与已发现文件推导应有月份；发现月份文件空洞时抛 `FileNotFoundError`，不再依赖默认关闭的 logger warning。
- iosql 在查询前检查目标表是否存在；错误 interval/table 转换为包含 `interval`、`table` 和可用表名的 `ValueError`。
- iosql 通过每个请求 symbol 的 `limit=1` 轻量查询完成预检；未指定 symbol 时也预检整体查询至少有一行。实际回放仍使用 `iter_rows()`，不得回退到 `select()` 全量读取。
- `batch_size` 的非法类型和值统一抛 `ValueError`。

## 实施步骤

1. 重构 pending 订单取消逻辑，使 `cancel_order()` 与 `close_portfolio()` 共享清理不变式。
2. 为无持仓、有持仓、预检失败以及 Exchange 物化/流式路径补充 portfolio 关闭回归测试。
3. 统一两个 Strategy 历史查询方法的返回类型，覆盖 pyta2 可用、不可用和缺失 symbol。
4. 为 `CsvBarsFeed.prepare()` 增加逐 symbol 文件与区间数据预检，并把月份空洞改为 fail-fast。
5. 为 `IosqlBarsFeed.prepare()` 增加表存在性、查询契约、逐 symbol/整体非空预检和用户可理解的错误转换。
6. 同步系统设计、CSV/iosql 设计稿、README 与使用 skill 中的公开契约。
7. 全量 review 后运行验收命令，修复发现的问题并生成结果文档。

## 测试与验收

必须覆盖：

- `close_portfolio()` 后价格穿越原限价也不会成交或抛错；物化和流式 Exchange 路径均覆盖。
- 关闭失败时 pending 订单仍保持 `pending`。
- 有无 pyta2 时历史接口返回同样的 `list` 语义；未交易 symbol 返回等长零序列。
- CSV 部分 symbol 缺文件、部分 symbol 在区间内无行、整体区间无数据、月份空洞均明确失败。
- iosql 错误 table/interval、缺失 symbol、整体区间无数据均明确失败；正常路径继续断言不调用 `Table.select()`。
- 现有示例与 API 契约测试不回退。

最终执行：

```bash
/home/lsl/miniconda3/bin/python -m pytest -q
/home/lsl/miniconda3/bin/python -m compileall -q minbt examples tests
git diff --check
```

验收标准：全量测试通过，无已知回测崩溃或静默空数据路径，文档与实现一致，并生成 `docs/dev/PLAN-043-review-fixes-OUTCOME.md`。

## 本计划不处理

第六轮 Review 中与本目标无直接关系的浮点交易单位容差、`get_positions()` 可变字典泄漏、A 股时区交易时段、加仓退出条件合并、`Portfolio.get_position()` 默认建空仓和 Binance 周/月周期等问题继续保留在 Review 清单中，后续单独立项，避免混淆本次正确性验收边界。
