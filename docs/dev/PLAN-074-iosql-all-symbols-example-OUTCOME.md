# PLAN-074 实施结果：iosql 全部 symbol 示例

日期：2026-10-25。
对应计划：[PLAN-074](PLAN-074-iosql-all-symbols-example.md)。

## 变更

- 新增 `examples/20_iosql_all_symbols.py`，使用 `BinanceKlineIosqlFeed(symbols=None)` 读取指定时间范围内所有有数据的 symbol。
- 策略遍历每次 `on_bars` 收到的标的，输出区间内出现过的 symbol、symbol 数量、K 线数和回调数；示例不下单，也不依赖 Matplotlib。
- README 补充 `symbols=None` 与截面回调语义、运行命令及示例索引；随包使用指南同步全部 symbol 的读取范围。
- 保留了用户在 `examples/15_iosql_feed.py` 中未提交的 `END = "2023-02-03"` 修改，没有改动该文件。

## 审阅与检查

- 确认 `BinanceKlineIosqlFeed` 在 `symbols=None` 时以时间范围和 `open_time` 排序构造查询，不添加 symbol 过滤；`on_bars` 只传当前时间实际有数据的 symbol。
- `python -m py_compile examples/20_iosql_all_symbols.py`：通过。
- `uv run --no-project ruff check examples/20_iosql_all_symbols.py`：通过。
- `git diff --check`：通过。
- 未运行实际回放；示例默认指向本地大体量 iosql 数据库，本轮仅完成静态检查与源码审阅。
