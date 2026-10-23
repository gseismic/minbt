# PLAN-070 实时交易阶段性实施结果

> 2026-10-23 更新：下列实现和测试证据均属于已归档的旧工作区；用户已要求回退到 `6c1e7a0`。
> 当前源码不包含这些功能。参考 [PLAN-071](PLAN-071-backtest-first-design.md) 与 [v1 备份](../ref/v1/README.md)。

状态：**进行中，原目标未完成**。本文件是当前证据与交接记录，不代表设计第 14 节已全部验收。
日期：2026-10-23。基准：minbt `76b6d7a70bedaebaeac7f0a090fdd479096568e6`，WORKTREE。

用户最新要求：**先认可代码，再测试，避免过分测试**。当前已停止测试与自动验证；后续只做代码、文档和人工自查，整理审阅材料。以下历史测试结果不作为最新工作区的验收结论。

## 已实施内容

- `replay.Exchange`、`sim.Broker`、旧同类弃用别名及薄配置委托；公共事件会话/运行上下文和独立 Exchange 协议。
- 共用 Runtime 的串行通知、默认延后成交、目标占用、只读生命周期、一次 on_ready、Fill/AccountUpdate 和兼容快照。
- Binance 实时行情映射、固定标的闭合 K 线收齐/去重/缺口停止、无行情控制、SDK 失败与积压监测，以及原始接收/事件/单调时间检查。
- 独立 live.Broker 的 Decimal 过滤器、模式校验、worker 准备握手、最终发送许可、账户投影、部分成交与原 ID 查询恢复。
- SQLite WAL/FULL、目录锁和身份绑定；queued/dispatch_prepared/not_sent/unknown 请求阶段，唯一成交/资金流水及本地退出配置、极值与触发义务。
- 本地追踪高点 120 / 5% 阈值 114 的耐久保存；离线路径无法证明时保留原阈值并阻止恢复交易。
- funding_pnl、complete/incomplete/unsupported 冻结、缺手续费待补全事实、非 USDT 费用诊断，以及策略 JSON 检查点。
- 可选完整结果日志、PersistentResult 按需查询和重新打开、会话截止隔离；有界策略/采样/终态明细缓存，累计账本保留。
- 新快速开始、历史经济模型示例的显式 legacy_immediate、[迁移指南](../migration/0.2-event-execution.md) 与 SDK 依赖补丁。

## 验证证据

原工作区基线：594 passed。实施中完整回归：634 passed、639 passed、641 passed；最近一轮含全部最新代码的结果在本节末追加。
独立插件测试只用公开契约，未继承 Binance 类、未调用私有运行函数、未注册插件名。
实时账户测试只发一次行情，后续部分成交、资金费、账户通知、就绪与退出均由账户事实驱动。
末轮审查还修复了：终态被迟到 unknown RPC 回退、未发送撤单释放原占用、缺费用填零、私有断线被旧 REST 快照提前解闸、恢复日志认证字段泄露等问题。

常用验证命令：

```bash
uv run --no-project python -m pytest -q --tb=short -W ignore::DeprecationWarning
uv run --no-project ruff check minbt tests examples --output-format concise
git diff --check
```

SDK 前置扩展：相邻 crypto_api 基准 `fbc4ab8ca8f70801592020c4c568e6e9182b1794`。
公开 `api.send_permission(check)` 的本机 HTTP/WS 验证及相关回归为 54 passed、280 subtests passed；Ruff/diff 检查通过。
详见该仓库 `docs/plans/PLAN-20261023-001-model-unknown-send-permission-OUTCOME.md`。
本仓库 [SDK 补丁](../integration/crypto-api-send-permission.patch) 与该工作区反向应用预检匹配。

## 尚未完成

原生固定价保护与设计第 26 项尚未实施；当前 native 明确拒绝。不得移除这个保护性拒绝来绕过验收。
仍需完成全部故障矩阵、恢复分页的有界交付、模拟部分成交注入、长运行压力及真实 SDK 本机整链路测试。
策略检查点、结果清理错误诊断、目标归一化边界、私有/REST 交错及账户同步时效仍需补齐审查与用例。
需要在全部本机验证后进行真实 demo 集成；当前没有使用凭证或发送任何交易所订单。

发布版本切换、最终文档同步、最终结果与提交/推送尚未执行。原有 PLAN-069 数值修复、设计稿、
BRAIN、GOAL 及原交接内容均保留，未回滚或混入提交。


## 2026-10-23 17:23 最终阶段验证

- minbt 全量：**643 passed，44.85 秒**。日志：`/tmp/minbt-live-handoff-final.log`。
- Ruff：`minbt tests examples` 全部通过；`git diff --check` 通过。
- 当前没有运行中的测试进程。未提交、未推送，原 goal 保持 active。
- 这只是当前实施阶段的回归证据；native 与剩余验收仍按上节继续，未将总体目标标为完成。
