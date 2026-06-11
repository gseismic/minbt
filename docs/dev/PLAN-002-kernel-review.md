# PLAN-002-kernel-review

## 目标
重点审查回测内核，发现并修复会影响资金、仓位、保证金、行情事件流正确性的缺陷。

## 审查范围
- `minbt/broker/struct.py`: `Cash`、`Position` 的资金和仓位计算。
- `minbt/broker/portfolio.py`: 下单、平仓、保证金、强平和账户权益。
- `minbt/broker/broker.py`: 多组合资金分配、市价单和查询接口。
- `minbt/exchange.py`: 行情迭代、时间对齐和策略回调。
- `minbt/strategy.py`: 策略事件包装和 broker 交互。

## 验证方式
- 对确认的问题增加聚焦回归测试。
- 运行相关测试和全量测试。
- 提交前执行 `git diff --check`。
