# PLAN-074：增加 iosql 全部 symbol 示例

日期：2026-10-25。
状态：已完成实施、代码审阅与静态检查。

## 目标与范围

- 基于 `examples/15_iosql_feed.py` 新增独立示例，使用 `BinanceKlineIosqlFeed(symbols=None)` 读取指定 iosql K 线表和时间范围内的全部 symbol。
- 在策略的 `on_bars` 中遍历当前时间批次实际出现的 symbol，统计 symbol 集合、K 线数和回调数。
- 更新 README 和随包 `minbt-usage` 参考文档，说明 `symbols=None` 的读取范围及回调行为。
- 不修改已有 `examples/15_iosql_feed.py`；保留其中用户未提交的 `END` 修改。

## 实施步骤

1. [x] 新增 `examples/20_iosql_all_symbols.py`，复用 iosql URI 和时间范围配置约定。
2. [x] 更新 README 的 iosql 说明、示例命令和示例列表。
3. [x] 更新随包使用指南的 Binance CSV/iosql 全部 symbol 语义。
4. [x] 审阅代码和文档差异，执行语法、ruff 和 diff 格式检查。
5. [x] 写入本计划对应的 OUTCOME 文件并更新开发计划索引。

静态检查通过；实际数据库回放未运行，详见
[结果文件](PLAN-074-iosql-all-symbols-example-OUTCOME.md)。
