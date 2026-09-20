# PLAN-043：正确性 Review 修复结果

## 状态

已完成。计划中的 portfolio pending 订单生命周期、pyta2 历史接口一致性、CSV/iosql
缺数据 fail-fast、文档同步和全量验收均已落地。

## 修复摘要

### 1. portfolio 关闭与 pending 订单

- `Broker` 新增内部统一取消路径，原 pending 订单转为 `canceled`，并同步清理
  `_pending_order_ids` 和 `_pending_exit_params`。
- `close_portfolio()` 无持仓时先取消该组合 pending 订单，再删除非 `main` 组合。
- 有持仓时只有全部平仓订单成功后才取消 pending 订单；关闭预检失败时保持 pending，
  不破坏原子边界。
- `main` 不会被删除，但成功关闭时同样取消其 pending 订单。
- 物化与流式 Exchange 都新增“关闭组合后价格穿越原限价”的回归测试，确认不会再访问
  已删除 portfolio 或中断事件循环。

### 2. Strategy 历史查询

- `get_hist_equity()` 与 `get_hist_position_sizes(symbol)` 统一返回 Python `list` 快照。
- pyta2 仍用于内部向量存储，但不再向用户泄漏 NumPy 返回类型。
- pyta2 的缺列填充值不再进入持仓结果：新 symbol 出现前、持仓关闭后都显式记录 `0`。
- 从未交易的 symbol 返回与历史长度相同的全零列表。
- 修复了安装 pyta2 时既有全量测试因 NumPy 数组比较失败的问题。

### 3. CSV 数据完整性

- 显式请求的任一 symbol 没有匹配文件时抛 `FileNotFoundError`，错误包含缺失 symbol、
  interval 和 root。
- 文件存在但 symbol 在 `[start, end)` 内没有任何行时抛 `ValueError`，不再产生空回测。
- 根据 start/end 与已发现月份校验每个 symbol 的月文件，缺月直接
  `FileNotFoundError`，不再依赖默认关闭的 loguru warning。
- 只有 `start` 时也从 start 月开始检查缺月；有时间边界时先按文件名月份裁剪候选文件，
  避免预检和回放扫描明显不相关月份。

### 4. iosql 数据完整性

- `prepare()` 先通过 `Database.table_names()` 检查目标 table；错误 interval/table 的消息
  包含目标表、interval 和可用表。
- 每个显式请求 symbol 使用 `limit=1` 的 `iter_rows()` 查询预检区间数据；未指定 symbol
  时预检整体查询至少一行。
- 表契约或查询错误转换为带 `uri/table/interval/symbols/time range` 修复指引的
  `ValueError`，保留原始异常链。
- `batch_size` 使用整数协议校验，`None`、布尔值、浮点数和非正整数统一抛 `ValueError`。
- 正常回放继续使用有序 `iter_rows(batch_size=...)`，测试仍禁止回退到 `select()`。
- 所有预检失败路径都会关闭 Database。

### 5. 文档与附加回归

- 更新 `README.md`：Feed fail-fast、流式性能取舍、关闭组合撤单、历史 list 语义。
- 更新系统设计与 CSV/iosql 设计稿，删除 `set_*` 包装流式源、缺月仅 warning、示例缺文件
  自动跳过等过期描述。
- 更新 `skills/minbt-usage/SKILL.md`，补充 CSV/iosql 用法、数据错误、portfolio 关闭和历史
  查询契约。
- 增加同一 dt 下流式 Feed 即使逆序注册也按 `bars → books → trades → news` 分发的测试。
- 记录第六轮 Review 的参考性能：10 万根 bar 流式峰值约 38.3 MB、物化约 180.1 MB，
  流式耗时约慢 40%；该环境敏感指标作为手工基准，不设不稳定的单元测试阈值。

## 变更文件

核心代码：

- `minbt/broker/broker.py`
- `minbt/strategy.py`
- `minbt/data/csv.py`
- `minbt/data/iosql.py`

测试：

- `tests/test_broker.py`
- `tests/test_exchange.py`
- `tests/test_strategy.py`
- `tests/test_streaming_feeds.py`

文档：

- `README.md`
- `docs/design/minbt-20260630-system-design.md`
- `docs/design/csv-iosql-feed-20260920-design.md`
- `skills/minbt-usage/SKILL.md`
- `docs/dev/PLAN-043-review-fixes.md`
- `docs/dev/PLAN-043-review-fixes-OUTCOME.md`

## 验证结果

修复前：

```text
1 failed, 185 passed
```

修复后：

```bash
/home/lsl/miniconda3/bin/python -m pytest -q
# 208 passed in 15.71s

/home/lsl/miniconda3/bin/python -m compileall -q minbt examples tests
# 通过，无输出

git diff --check
# 通过，无输出
```

新增 22 个测试实例，覆盖：

- portfolio 无持仓/有持仓/预检失败以及物化/流式事件循环；
- pyta2 可用和不可用、晚出现/已平仓/从未交易 symbol；
- CSV 部分缺 symbol、区间无行、缺月、单边 start、回测启动前失败；
- iosql 缺 table、缺 symbol、空区间、空表、错误表契约、非法 batch_size、资源释放；
- 流式多 event-type 固定分发顺序。

## Review 结论

本计划范围内未发现剩余阻塞问题。代码与文档契约一致，全量测试、编译检查和 diff 格式检查
均通过。

第六轮 Review 中明确不属于 PLAN-043 的浮点交易单位容差、`get_positions()` 可变字典泄漏、
A 股时区交易时段、加仓退出条件合并、`Portfolio.get_position()` 默认建空仓和 Binance
周/月周期问题仍保留，后续应单独立项处理。
