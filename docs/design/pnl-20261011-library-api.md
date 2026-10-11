# 库级盈亏查询设计

## 目标和代表场景

ISSUE-001 要求由库统一计算盈亏，避免策略和示例重复实现成交公式。按使用频率确定接口：

| 场景 | 使用方式 |
| --- | --- |
| 回测结束查看净盈亏和累计手续费 | `broker.get_total_pnl()` |
| 持仓期间区分已实现、未实现盈亏 | 读取结果的 `realized_pnl`、`unrealized_pnl` |
| 查看指定分仓结果 | `broker.get_pnl(portfolio="trend")` |
| 查看某个标的累计结果，包括已平仓部分 | `broker.get_pnl("BTCUSDT")` 或 `get_total_pnl("BTCUSDT")` |
| 核对某笔订单成交 | `broker.get_pnl_records(order_id=order.id)` |
| 核对部分平仓、反手、风险结算 | 按分仓或标的读取记账明细 |
| 分仓关闭后统计整个回测 | 查询仍包含已关闭分仓历史 |
| 展示净值曲线 | 继续使用 `strategy.get_hist_equity()` |

## 用户接口

```python
from minbt import Pnl, PnlRecord

broker.get_total_pnl(symbol: Optional[str] = None) -> Pnl
broker.get_pnl(symbol: Optional[str] = None, *, portfolio: Optional[str] = None) -> Pnl
broker.get_pnl_records(
    *,
    portfolio: Optional[str] = None,
    symbol: Optional[str] = None,
    order_id: Optional[str] = None,
) -> List[PnlRecord]
```

- `get_pnl()` 默认查询 `main`，与 `get_equity()` 的分仓默认值一致。
- `get_total_pnl()` 查询整个 Broker，支持跨分仓汇总一个标的。
- `get_pnl_records()` 默认查询全部记录，与 `get_orders()` 的筛选习惯一致；多个筛选条件取交集。
- `symbol=None` 表示不按标的筛选；从未交易的标的返回全零 `Pnl` 和空明细，不创建持仓。
- 分仓结果按名称累计，包含已关闭分仓；关闭后复用同名分仓仍累计历史。未知分仓抛 `ValueError`。
- 未知或未成交的 `order_id` 返回空列表。系统风险结算没有订单 ID。
- 拒绝订单本身不记成交盈亏；其显式价格若触发真实强平或穿仓，仍保留独立系统结算记录。
- 汇总和明细均为不可变数据类；明细查询返回新列表，调用者不能改写库内统计。
- 查询只读取当前估值，不更新价格、不交易；保留现有 `BrokerProtocol`，不增加自定义 Broker 的强制能力要求。

## 盈亏定义

`Pnl` 字段：

| 字段 | 口径 |
| --- | --- |
| `realized_pnl` | 按现有平均成本计算的累计平仓毛盈亏，不扣手续费 |
| `unrealized_pnl` | 当前持仓按最近一次估值价格计算的毛盈亏 |
| `fees` | 已实际扣除的累计手续费，包含开仓、加仓、减仓和平仓 |
| `settlement_adjustment` | 穿仓清零产生的结算调整，普通交易为零 |
| `net_pnl` | 以上字段计算的净盈亏属性 |

```text
net_pnl = realized_pnl + unrealized_pnl - fees + settlement_adjustment
全账户 net_pnl = get_total_equity() - broker.initial_cash
```

保证金占用和释放不是盈亏，杠杆影响保证金和风险条件，不改变单位价格变动的毛盈亏。

- 同方向加仓沿用加权平均成本。
- 部分平仓仅实现被平掉数量的毛盈亏，剩余仓位继续盯市。
- 反手成交记录旧方向平仓毛盈亏，全部成交数量的手续费只记一次，新方向从成交价建仓。
- 累计手续费不分摊到配对的往返交易。开仓明细可能只有负的手续费净贡献；本接口不提供 FIFO 批次配对和胜率分析。
- 分仓间划拨不算盈亏。主分仓净盈亏不能直接用当前主分仓权益减其初始资金，因为划拨改变了资金基数；全账户权益差不受内部划拨影响。
- 同名分仓结果包含历史生命周期，不能直接与重新创建后的单个分仓初始资金比较。

## 单笔成交和系统结算明细

`PnlRecord` 包含 `portfolio`、`symbol`、`qty`、`price`、`dt`、`order_id`、`reason`，以及 `realized_pnl`、`fees`、`settlement_adjustment` 和 `net_pnl`。

- 普通成交 `reason="trade"`，一笔已成交订单对应一条记录，`qty` 为有符号的实际成交数量。
- `net_pnl` 表示该次记账对累计已结算净盈亏的贡献，不包含之后的未实现盈亏。
- 系统强平 `reason="liquidation"`，沿用当前免手续费规则，不伪造普通订单。
- 穿仓清仓 `reason="bankruptcy"`；系统记录实际被清掉的仓位及其盯市毛盈亏。
- 全仓清零调整 `reason="bankruptcy_settlement"`，`symbol=None`、`qty=0`、`price=None`，单独表示账户层面的债务清零或资产核销。
- 明细按实际记账顺序排列，不按行情时间重新排序；直接显式下单可以使用未提供或非递增的 `dt`。

## 强平和穿仓

正常强平将 `Position.commit_close_all()` 返回的毛盈亏计入已实现盈亏，未实现盈亏随平仓归零。系统不额外扣除原模型中不存在的手续费。

逐仓穿仓时，当前模型只损失该仓位保证金。记录全部盯市毛亏损，同时记录 `-position.equity` 的结算调整，使实际净损失等于被清零的保证金；该调整可归属标的。

全仓穿仓时，当前模型清空所有持仓和现金，最终权益为零。先按标的记录所有持仓毛盈亏，再增加 `-清零前账户权益` 的账户结算调整。账户层面的调整不能合理分摊到某个标的，因此不人为分配；此时各标的净盈亏之和加上账户结算调整才等于账户净盈亏。

重复推进行情或重复标记破产不重复记录同一结算。

## 内部实现和生命周期

1. Portfolio 保存按标的的已记账汇总和不可变明细；仅在实际现金与仓位提交后记录普通成交。
2. Broker 为实际 Portfolio 接入内部记录回调，将不可变记录加入统一日志，保证跨分仓记账顺序。
3. `can_submit_orders()` 复制统计汇总、使用独立临时明细并禁用真实记录回调，避免挂单和批量关闭预检污染状态。
4. 关闭非主分仓时保存其不可变汇总，断开实际日志回调，并正常归还现金；不把分仓历史转记为主分仓利润。账户日志继续保留原归属。
5. 独立 Portfolio 的 `reset()` 清空现金、持仓和自身统计。Broker 管理的 Portfolio 不应绕过 Broker 直接修改或重置，与既有交易边界一致。
6. 不修改 Position 的公式或保存逐笔 FIFO 批次，不从可被用户修改的 `Order` 对象重建盈亏。

查询汇总按标的及持仓数线性汇总，不回放成交历史；单标的查询为常数时间，跨分仓查询按分仓数汇总。明细查询按记录数扫描并分配返回列表，存储空间随实际成交和风险结算记录数量增长。接口沿用现有单线程回测模型，不额外承诺并发写入。

## 验证

- 独立手算多空、手续费、加仓均价、部分平仓、双向反手和不同杠杆。
- 每个交易阶段核对汇总公式和账户权益差。
- 核对多标的与多分仓汇总、资金划拨、关闭及同名重建。
- 检查限价单预检、失败预检、拒绝、撤单和跳过不新增成交统计。
- 覆盖普通退出、逐仓/全仓强平、穿仓、批量行情和显式单价入口。
- 验证明细与订单关联、跨分仓顺序、不可变查询及未知筛选语义。
- 盈亏示例只展示公开接口；手算和正确性断言留在测试中，保留权益曲线绘图。
