# 当前工作交接

日期：2026-10-23。最新任务为 PLAN-072；此前复杂实盘实现已回退，新版薄适配已落地。

## 用户动机和最新约束

先读 `GOAL.md`。minbt 是 mini、低认知负荷的 K 线回测库，回测第一位，实盘是附加能力。
用户明确允许为减少复杂度放弃回测/实盘的一致性；实盘只通过外部 Binance2 Broker/Exchange 接入，
先定义协议或基类。用户先要求约 150 行，最新明确“150 行不是硬性规定”，仍以精简为目标。
用户已要求“实施”，PLAN-072 已完成代码和源码审阅。此前“代码认可后再测试”的偏好继续保留，尚未运行测试。

## 当前代码与备份

- PLAN-071 将工作代码恢复到 `6c1e7a01c56578728bc44cf6e382659bac069a8f`，其时共 91 个活动文件逐文件核验一致。
- PLAN-072 在此基线上新增协议、live.py、共用策略示例，并更新 Strategy 绑定、历史 Exchange 校验与文档；当前活动代码已不等于原基线。
- 原 HEAD 保持 `76b6d7a70bedaebaeac7f0a090fdd479096568e6`，没有 reset 提交历史、提交或推送；HEAD 与目标的差异本来主要是设计文档。
- 回退前的全部未忽略工作文件（含未提交/未跟踪实现）和目标提交分别归档在 `docs/ref/v1`，见该目录 README。
- 工作区快照校验 352 个文件，目标提交快照校验 307 个普通文件；备份后从代码/测试中删除 34 个后续新增文件。
- PLAN-069 数值修复也随精确回退撤出，保存在工作区快照；不可声称当前源码包含该修复。
- GOAL.md、BRAIN.md 保留原内容；相邻 crypto_api 仓库未修改。

## 新设计

`docs/design/live-trading-20261023-design.md` 第七版，已按 PLAN-072 实施，待用户代码审阅后验证。

主要决定：

1. 保留 `minbt.Exchange/Broker/Strategy`、同步回测撮合、目标单、分仓、退出规则、RunResult。
2. 以两个最小 Protocol 表达共同策略能力；Strategy 的最小 Broker 绑定与历史运行的完整账户校验分开。
3. 实盘一个文件，Broker 只薄适配市价 signed qty 与单向持仓查询；其他操作使用 SDK 原始接口。
4. live.Exchange 使用外部 SDK 的单线程回调、连接和队列，只交付单标的闭合 K 线。
5. 实盘同步请求、SDK 订单字典、run 正常返回 None；不提供 target_*、分仓、自动退出或实盘绩效。
6. 不建 Runtime/Session/私有流投影/持久化/保护管理/自动恢复；异常停止，不重发未知请求。
7. 实际生产代码新增/替换 219 行：live.py 186 行、协议及导出 22 行、核心改动 11 行，包含空行与注释。

本机依赖实际为 `crypto_api.binance2.usdm`；相邻 finapi 未发现用户所称 binance2。
使用显式工厂注入和 SDK 账户实例，未绑定或修改相邻 SDK。

实现要点：Broker 仅适配 submit_market_order/get_position_size；所属 Exchange 状态与回调线程检查
下单许可，写异常封禁后续适配写入。Exchange 一次运行一个策略，订阅参数在账户查询前校验，
确认单向模式后初始化并启动 SDK；只交付闭合 K 线，检查去重、连续性与接收/事件/收盘时间。
stop 关闭后续准入；已准入的回调/请求仍可继续，close 复用 SDK 的等待语义，不撤单或平仓。
装配/run 由调用者顺序执行，不新增通用并发启动保护；高级 broker.sdk 调用不受适配许可限制。

## 文档状态

- PLAN-071 记录此次备份、回退和设计修订，结果见对应 OUTCOME。
- PLAN-072 与 OUTCOME 记录薄适配实现、219 行统计、源码审阅和后续验证范围；设计索引指向第七版。
- PLAN-069 结果、PLAN-070 计划/结果、旧事件迁移说明已标明历史/回退状态。
- `docs/integration/crypto-api-send-permission.patch` 仅为历史材料，新设计不依赖它。
- 原 HANDOFF 与第六版全文在工作区快照中可恢复。

## 下一步

等待用户审阅代码；按反馈精简或修正。代码认可后做少量 fake SDK 行为验证与既有回测回归，见 PLAN-072。
主要入口：minbt/plugins/binance/live.py、minbt/protocols/trading.py、examples/19_live.py。
不要恢复 PLAN-070 的阶段 A–D 或其故障矩阵。不要主动补回原生保护、统一事件执行、恢复数据库等已取消能力。
本轮只人工审阅、统计源码与 git diff --check；未运行测试、导入/编译检查或示例，未连接 SDK 或发送订单。
