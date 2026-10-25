# PLAN-075 实施结果：本地 K 线 Feed 支持 `*`

日期：2026-10-25。
对应计划：[PLAN-075](PLAN-075-symbol-wildcard-local-kline-feeds.md)。

## 变更

- `BinanceKlineIosqlFeed` 与 `BinanceKlineCsvFeed` 支持 `symbols="*"` 和 `symbols=["*"]`，将独立通配符归一化为全量读取，与 `symbols=None` 或省略参数等价。
- 通配符与具体 symbol 混用时抛出 `ValueError`，不将模糊组合静默解释成某种筛选条件。
- Binance K 线下载缓存 Feed 保持要求显式 symbol 列表的行为。
- 将 `examples/20_iosql_all_symbols.py` 改为使用 `symbols="*"`；README 和随包使用指南同步说明写法与约束。

## 审阅与检查

- 静态审阅确认两种本地 Feed 在收到 `None` 后继续走原有全量读取路径；symbol 列表仍按原有规范校验并过滤。
- `python -m py_compile minbt/plugins/binance/kline.py minbt/plugins/binance/csv.py minbt/plugins/binance/iosql.py examples/20_iosql_all_symbols.py`：通过。
- `uv run --no-project ruff check minbt/plugins/binance/kline.py minbt/plugins/binance/csv.py minbt/plugins/binance/iosql.py examples/20_iosql_all_symbols.py`：通过。
- `git diff --check`：通过。
- 按本轮任务边界，没有新增或运行测试，也没有执行需要本地数据库的回放。
