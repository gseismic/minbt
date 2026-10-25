# PLAN-073 Binance 分钟 K 线缺口探测与协议回归修复

日期：2026-10-25。
状态：已完成实施、人工源码审阅、人工造库验证与全量回归。

## 目标与范围

- 修复 Strategy 最小交易协议的过时测试：允许仅实现市价单和净持仓查询的账户绑定；历史 Exchange.run 拒绝不符合 ReplayBrokerProtocol 的账户。
- Binance CSV / iosql 的 `interval="1m"` 默认检查连续性，使用默认可见的 Python `RuntimeWarning`，不依赖关闭的内部日志。
- 每个 symbol 从请求区间内首次出现开始，按 open_time 每 60 秒期待一条 K 线。首次出现前无数据不告警；每次 events() 迭代，每个 symbol 只报告第一处缺口。
- 检测单 symbol 漏分钟、整分钟全部缺失、出现后持续消失和显式 end 前的尾部漏数。未指定 end 时，以实际数据最后一分钟为边界；不能从 K 线单独确认 delist，warning 提示排查漏数或下架。
- 保持历史回放只交付真实 Bar。下载缓存 Feed 已有严格的首尾/中间完整性错误，继续保持该检查。
- 不修改实盘适配，不联网。用户追加要求全部提交，本轮提交全部改动，不推送。

## 实施步骤

1. [x] 复现协议回归失败，更新最小绑定和历史运行拒绝测试。
2. [x] 在 Binance 共用 K 线读取层加入分钟探测，按完整时间截面检查，确保其他 symbol 的同分钟数据读完后才判断缺失。
3. [x] 用手工构造的 CSV 和真实临时 iosql 数据库覆盖缺口、消失、晚上市、连续数据、end 边界、重复读取和提前关闭；验证 preload/incremental 回测。
4. [x] 更新使用说明，审阅改动并运行针对性/全量回归与静态检查。
5. [x] 记录人工造库的 warning 输出及测试结果，完成 OUTCOME 文件。

验证：全量 **581 passed in 38.82s**，ruff 与 git diff --check 通过。详见
[结果文件](PLAN-073-binance-minute-continuity-OUTCOME.md)。
