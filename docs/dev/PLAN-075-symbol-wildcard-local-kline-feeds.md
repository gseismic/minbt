# PLAN-075：本地 K 线 Feed 支持 `*` 订阅全部 symbol

日期：2026-10-25。
状态：已完成实施、代码审阅与静态检查。

## 目标与范围

- 让 `BinanceKlineIosqlFeed` 和 `BinanceKlineCsvFeed` 的 `symbols="*"` 表示读取所选来源及时间范围内的全部 symbol，与 `symbols=None` 等价。
- 兼容 `symbols=["*"]`；不允许通配符与具体 symbol 混用，明确报错。
- 不改变要求显式 symbol 列表的 Binance 下载缓存 Feed。
- 更新全部 symbol 示例、README 和随包 `minbt-usage` 文档。
- 不运行或新增测试；按本次任务边界进行源码审阅和静态检查。

## 实施步骤

1. [x] 在本地 K 线 Feed 共用的 symbol 归一化入口支持独立通配符，并拒绝与具体 symbol 混用。
2. [x] 将全部 symbol 示例改为 `symbols="*"`，保留 `None` / 省略参数的现有行为。
3. [x] 更新 README 和随包使用指南，写清支持写法及混用错误。
4. [x] 审阅修改，运行语法、ruff 和 diff 格式检查，不运行测试。
5. [x] 记录结果并更新开发计划索引。

静态检查通过；本轮未运行或新增测试，详见
[结果文件](PLAN-075-symbol-wildcard-local-kline-feeds-OUTCOME.md)。
