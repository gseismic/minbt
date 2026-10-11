# PLAN-057 结果：库级盈亏查询

## 完成内容

- 完成 ISSUE-001，新增 `Broker.get_total_pnl(symbol=None)`、`get_pnl(symbol=None, *, portfolio=None)` 和 `get_pnl_records(*, portfolio=None, symbol=None, order_id=None)`。
- 导出不可变的 `Pnl` 和 `PnlRecord`；查询不创建空持仓，返回新明细列表，修改可变订单不影响已完成记账。
- 直接使用 Position 实际成交返回的平均成本毛盈亏和 Portfolio 实际手续费，不从订单历史或示例重算。
- 覆盖开仓、加仓、部分平仓、反手、限价成交、订单退出条件和系统风险结算。
- 逐仓穿仓保留标的毛亏损及保证金清零调整；全仓穿仓保留各标的毛盈亏，并单独记录账户结算调整，净盈亏与实际权益差一致。
- 隔离预检副本的汇总、明细和 Broker 日志回调；拒绝、撤销、跳过与预检不重复记成交手续费。
- 关闭分仓后保存原归属的不可变汇总，归还资金不计为主分仓利润；同名分仓重建继续累计历史。
- 盈亏示例已精简，使用公开查询展示结果和订单明细；独立手算公式及正确性断言保留在测试中，继续显示权益历史转换的净盈亏曲线。
- 同步 README、usage skill、当前设计索引、账户查询设计及绘图说明；ISSUE 状态更新为已完成。历史 `docs/versions/v0` 快照未修改。

## 自行审阅

- 检查所有实际资金与持仓变化入口，包括显式下单价格触发的系统风险结算；拒绝订单本身没有成交明细，真实系统结算仍保留。
- 检查预检回调隔离与不可变汇总的复制，避免模拟强平或穿仓写入真实日志；预检不复制整段历史明细。
- 检查分仓归档、名称复用及账户汇总，归档后断开原分仓的实际日志回调。
- 检查系统记录的价格、数量和时间：账户层面调整无标的及价格，行情触发的账户结算保留本次行情时间。
- 现有 BrokerProtocol 和 Strategy 历史查询保持兼容，不给用户自定义 Broker 增加强制盈亏方法。

## 验证结果

- `uv run --no-project python -m pytest -q`：**257 passed**，20.74 秒。
- `uv run --no-project python -m pytest -q tests/test_pnl.py tests/test_api_contract.py`：50 项通过。
- `uv run --no-project python -m pytest -q tests/test_examples.py`：16 项通过。
- 盈亏示例使用 `MPLBACKEND=Agg` 实际运行成功，三组净盈亏为 `20`、`10`、`-0.15005`；最终权益为 `1020`、`1010`、`999.84995`。
- `ruff check minbt tests examples`：通过。
- 以 Python 3.8 的语法模式解析 `minbt/tests/examples` 中 57 个 Python 文件：通过；此项为语法兼容验证。
- `git diff --check`：通过。

## 统计边界

- 普通交易：`net_pnl = realized_pnl + unrealized_pnl - fees`；穿仓额外包含 `settlement_adjustment`。
- 全账户净盈亏等于总权益减 Broker 初始资金；分仓内部资金划拨不计盈亏。
- 同名分仓查询包含全部历史生命周期，不能只与新分仓当前权益及初始资金比较。
- 全仓穿仓的账户结算调整不分摊到标的；各标的结果与该账户调整合计后才等于全账户结果。
- 明细按单次成交或系统结算记录，不提供 FIFO 往返配对、手续费批次分摊或胜率分析；系统强平沿用原模型的免手续费规则。

## 交付文件

- 设计：`docs/design/pnl-20261011-library-api.md`。
- 计划：`docs/dev/PLAN-057-library-pnl.md`。
- 结果：本文件。
- 代码：`minbt/broker/pnl.py`、`minbt/broker/portfolio.py`、`minbt/broker/broker.py` 和包导出。
- 验证：`tests/test_pnl.py`、`tests/test_api_contract.py`、`tests/test_examples.py`。
