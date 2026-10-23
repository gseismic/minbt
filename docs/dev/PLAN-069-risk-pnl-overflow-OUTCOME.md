# PLAN-069 实施结果：行情风险结算的盈亏溢出预检

> 2026-10-23 更新：用户要求精确回退到 `6c1e7a0`，本报告所述后续修复和测试已从工作代码撤出并保存在 [v1 备份](../ref/v1/README.md)。
> 以下为历史结果，不代表当前基线已经包含该修复；恢复需另行决定。

- 日期：2026-10-18（Asia/Shanghai）。
- 计划：[PLAN-069](PLAN-069-risk-pnl-overflow.md)。
- 状态：已完成。

## 修复结果

原复现通过正常交易产生 `A` 累计已实现亏损 `-1e308`，随后行情触发另一笔 `-1e308` 的穿仓结算。
此前 `math.fsum` 在风险记账时抛出 `OverflowError`，价格和估值已经更新，全仓破产清理尚未执行。
现在该候选行情在写入之前抛出 `ValueError: realized_pnl must be finite`，账户完整保留原状态。

1. `Portfolio._preview_mark_prices` 在候选持仓上判断实际强平/穿仓条件，并校验随后的盈亏变更。
2. 纯预检检查逐标的累计已实现盈亏、费用、结算调整，再检查完整账户汇总及剩余持仓浮动盈亏参与的净盈亏；不修改持仓、追加明细或通知 Broker。
3. 逐仓单价预检限定于该标的；批量预检覆盖全部非空仓位。Broker 在行情和时钟推进前检查全部分仓，后续分仓溢出不会留下前面分仓的结算。
4. 成交预检还检查成交后的即时风控；新订单增加保证金、成交价与估值价不同等情况不会先成交再发现风险记账溢出。普通整组全平跳过组内即时风控预检，保持原整组结算语义。
5. 直接调用全仓 `mark_bankrupt` 时，先验证整组盈亏变更，再写入首条明细。
6. 同步 [全仓减仓与数值结算](../design/execution-20261013-cross-settlement.md) 的行情与成交预检说明。

## 回归覆盖

新增 `tests/test_risk_pnl_overflow.py`，共 43 个参数化用例，覆盖：

- 全仓/逐仓、强平/穿仓、单价/批量的溢出拒绝及合法极值成功结算。
- Broker 行情、批次和显式下单入口；后一个分仓或持仓发生溢出时，前面的状态没有部分提交。
- 逐标的与账户已实现盈亏汇总、逐标的与账户结算调整、保留持仓浮亏参与净盈亏求和的独立溢出。
- 成交后即时穿仓、新订单增加总保证金触发强平、直接全仓破产清理。
- 拒绝前后完整账户状态一致，包含价格、报价时间、时钟、现金、持仓内容、锁仓数据、破产标记、账本、明细及 Broker 订单；持仓对象身份保留。
- 合法结算金额与实际权益对齐，预检不写日志，风险记录时间正确，重复行情不重复记账。

## 验证结果

- 针对性回归：`uv run --no-project python -m pytest -q tests/test_risk_pnl_overflow.py tests/test_pnl.py tests/test_portfolio.py tests/test_broker.py tests/test_review_round9_round10.py --tb=short`：**219 passed in 3.67s**。
- 全量回归：`uv run --no-project python -m pytest -q --tb=short`：**594 passed in 73.54s**。
- 静态检查：`uv run --no-project ruff check minbt/broker/portfolio.py minbt/broker/broker.py tests/test_risk_pnl_overflow.py`：**通过**。
- 差异检查：`git diff --check`：**通过**。

## 代码复核

逐项核对候选风险条件与实际结算的负保证金水平、最低保证金水平、零保证金及单价/批量范围。
预检只在候选字典和不可变盈亏快照上计算，未对原持仓的锁仓列表执行操作。
复核成交、整组全平和直接破产入口的校验顺序；普通风险结算、挂单、退出条件和回放由全量测试共同验证。
