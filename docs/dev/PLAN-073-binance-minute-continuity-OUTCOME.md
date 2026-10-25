# PLAN-073 实施结果

日期：2026-10-25。
对应计划：[PLAN-073](PLAN-073-binance-minute-continuity.md)。

## 变更

- 修正 Strategy 旧协议测试：最小账户可绑定，历史 Exchange.run 在回放前按 ReplayBrokerProtocol 拒绝能力不足的账户；同时验证缺少任一最小方法时的错误提示。
- Binance CSV / iosql 的 `interval="1m"` 自动检测缺口。从各 symbol 首次出现开始，按 open_time 每 60 秒检查；每次 events() 迭代，每个 symbol 只报告第一处缺口。
- 使用 Python RuntimeWarning，默认可见，不依赖 minbt 默认关闭的 loguru 日志。内容包含 Feed、symbol、最后有效时间和首次缺失时间，并提示检查数据库漏数或 delist；回测继续交付实际数据。
- 按完整分钟截面检查，最多缓冲一个截面，避免同分钟不同 symbol 读取顺序导致误报。已报告的 symbol 不再跟踪连续性；其他未报告 symbol 的检查仍继续。
- 检查中间缺口、整分钟缺失、持续消失和 Feed end 前的尾部缺口。无 end 时以实际数据最后一分钟为边界；生成器提前关闭不报告未读取的尾部。下载缓存 Feed 的严格完整性报错保留，避免将尚未收盘区间误判成尾部漏数。
- 更新 README、执行不变量设计、库内使用技能参考和两处原有稀疏 CSV 测试的预期 warning。

## 人工造库验证

另行运行一次不依赖 pytest 的 Python 脚本：在 TemporaryDirectory 内建立真实 iosql SQLite 时序表
`kline_1m`，手工写入假 K 线，通过 BinanceKlineIosqlFeed（batch_size=1）和历史 Exchange
做 incremental 回测，捕获并检查 RuntimeWarning；完成后自动删除临时数据库。
没有启用 minbt 内部日志，也没有接触真实行情或交易环境。

时间窗口：UTC 2026-10-01 00:00 至 00:05（半开）。

| 场景 | 手工数据（分钟） | 结果 |
| --- | --- | --- |
| 连续 + 晚出现 | BTCUSDT: 0,1,2,3,4；LATEUSDT: 3,4 | 7 条数据，5 个回调，0 warning |
| 漏数 + 持续消失 | BTCUSDT: 0,1,2,3,4；GAPUSDT: 0,2,4；DROPUSDT: 0,1；LATEUSDT: 3,4 | 12 条数据，5 个回调，2 warning |

第二个场景的实际诊断内容如下（省略来源前缀及重复的排查提示）：

```text
RuntimeWarning: GAPUSDT 1m Kline missing; first missing open_time=2026-10-01T00:01:00+00:00, last seen open_time=2026-10-01T00:00:00+00:00.
RuntimeWarning: DROPUSDT 1m Kline missing; first missing open_time=2026-10-01T00:02:00+00:00, last seen open_time=2026-10-01T00:01:00+00:00.
```

GAPUSDT 再次漏掉 00:03 不重复提醒；DROPUSDT 后续一直消失也只提醒一次。
LATEUSDT 首次出现前没有误报。脚本对上述数量、symbol、首次缺失时间和完成回调数全部断言通过。

可重复运行的假数据回归见 `tests/test_binance_continuity.py`，同时覆盖 CSV 与真实 iosql 数据库：

```bash
uv run --no-project python -m pytest -q tests/test_binance_continuity.py
```

## 验证与审阅

- 修复前重现协议失败：`uv run --no-project python -m pytest -q tests/test_strategy.py`，1 failed、5 passed，失败为旧测试要求最小账户绑定时抛错。
- 初次直接调用 PATH 中的 pytest 使用了缺少 pandas 的系统 Python，未完成收集；按仓库既有 uv 命令切回已安装依赖的开发解释器后完成全部验证。
- 针对性回归（Strategy、分钟连续性、Binance 缓存、数据 Feed）：63 passed。
- 全量回归：`uv run --no-project python -m pytest -q --tb=short`：**581 passed in 38.82s**，没有剩余 warning。
- 静态检查：`uv run --no-project ruff check minbt/plugins/binance/kline.py minbt/plugins/binance/cache.py tests/test_strategy.py tests/test_binance_continuity.py tests/test_data_feed.py`：通过。
- `git diff --check`：通过。
- 人工审阅了截面分组、首处缺口计算、每 symbol 去重、end 半开边界、重复读取和提前关闭时的资源释放；未发现待修复问题。

用户追加要求全部提交，代码、测试、设计说明、计划和本结果文件统一纳入本次提交；未推送。
