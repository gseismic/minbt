# PLAN-053：第七轮 Review 问题修复结果

## 状态

已完成。Review 报告中的运行逻辑问题已修复或明确其 API 语义，并为每组行为增加回归测试。

## 修复摘要

### 1. Portfolio 与 Broker 状态

- 逐仓批量风险检查不再在首个穿仓/强平后提前返回；同一批次继续检查其余仓位，并汇总穿仓、强平结果。
- `Portfolio.get_position()` 默认只查询，不再创建空仓；`close_position()` 对不存在的仓位无副作用。需要显式建空仓时仍可传 `create_if_missing=True`。
- `get_positions()` 和 `positions` 返回字典浅快照，清空快照不会删除组合内部的持仓索引。
- 挂单仅在当前市场批次包含该 symbol 的估值价格时检查成交，避免用旧价在其他 symbol 或 News 时间点成交。
- 同方向新成交附带部分退出参数时，未提供的标准止损、止盈和追踪止损字段继承该仓位之前的活动配置；反向或平仓仍按既有生命周期清理。

### 2. Market 规则

- `Market` 新增 IANA `timezone`，默认 UTC；A 股预设使用 `Asia/Shanghai`。带时区时间会转换到市场时区；无时区时间按 UTC 解释；交易日也按市场时区计算。午夜日线仍可由 UTC 或市场本地午夜时间表示。
- `lot_size`、`tick_size`、`min_qty`、`min_notional` 必须是有限正数；target 数量不会被归一化到目标值之上。
- tick/lot 倍数检查改用按浮点精度缩放的容差，高价小 tick 可正确接受，同时半 tick 仍会拒绝。
- 为保持 Python 3.8 支持，添加条件依赖 `backports.zoneinfo`。

### 3. Feed、缓存与时间

- `Exchange.set_*()` 可替换自身此前创建的内存来源；与用户注册的同名 Feed 冲突时明确报错。
- 通用 Bar CSV 的 `end` 过滤不再提前停止读取；仍按流式方式验证范围外尾部顺序，乱序输入会报错。
- Binance K 线只把有明确收盘时间且收盘后的数据作为 `closed_only` 结果。缓存记录新增抓取时间，以区分“收盘前缓存、后来时间已过”的过期未收盘数据；此类覆盖会触发重抓，cache-only 会报缓存不完整。
- Binance 空响应、内部周期缺口、末尾截断和逐 symbol 空缓存不会登记/接受为完整覆盖。旧 SQLite schema 会增加抓取时间列并清空旧 coverage 标记，下一次普通读取会重新验证。
- Kline CSV 未指定时间边界时按各 symbol 自己的文件跨度推断月份；显式边界仍按请求区间严格检查。
- `normalize_datetime(value, unit=...)` 增加 `s/ms/us/ns` 显式单位，保留原有自动推断以兼容已有调用。

## 回归测试

新增或更新测试覆盖：逐仓同批多仓风险处理、持仓查询与快照、A 股时区和交易单位、tick 浮点容差、跨 symbol 挂单触发、部分退出条件继承、Feed 名称冲突、通用 CSV 截断后的乱序、Kline CSV 不同上市跨度、Binance 空/不完整响应、缓存未收盘过滤和旧缓存 schema 迁移，以及显式时间戳单位。

## 变更文件

- 核心代码：`minbt/broker/broker.py`、`minbt/broker/market.py`、`minbt/broker/markets.py`、`minbt/broker/portfolio.py`、`minbt/data/bar_feed.py`、`minbt/data/binance.py`、`minbt/data/csv.py`、`minbt/data/model.py`、`minbt/exchange.py`。
- 依赖：`pyproject.toml`。
- 测试：`tests/test_broker.py`、`tests/test_data_feed.py`、`tests/test_exchange.py`、`tests/test_generic_bar_feed.py`、`tests/test_portfolio.py`、`tests/test_binance_feed.py`。
- 文档：本结果文件、`docs/dev/PLAN-053-review-20261002-fixes.md`、`docs/review/review-20261002-round7.md`。

## 验证结果

```text
/home/lsl/miniconda3/bin/python -m pytest -q
222 passed in 25.89s

/home/lsl/miniconda3/bin/python -m compileall -q minbt examples tests
通过，无输出

git diff --check
通过，无输出
```

示例代码和其他并行工作区文件没有纳入本次修复；全量测试与编译检查按用户要求在当前工作区运行。
