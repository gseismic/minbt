# PLAN-022 Broker 事务原子性 - 结果

## 真实性复核

计划中的三个问题均通过当前代码和运行态场景确认真实存在：

1. 高手续费、多仓位关闭会出现第一笔 filled、第二笔 rejected，留下部分持仓。
2. 资金不足的限价单仍会进入 pending。
3. pending 期间仓位反向后，限价单会先成交，再因退出条件方向错误抛出异常。

## 已完成

1. Portfolio 增加无副作用的顺序订单预检。
2. `close_portfolio()` 在真实成交前完成全部 Market 校验和 Portfolio 顺序预检。
3. 原子关闭预检失败时不修改任何持仓。
4. 限价单提交时使用 limit price 和当前组合状态做资金预检。
5. 限价单不预留资金；触发时仍通过真实 Portfolio 校验。
6. 限价退出参数在提交时只校验数值和互斥关系。
7. 限价触发时根据预计成交后持仓和成交价完成方向校验。
8. 退出条件失效时整笔限价单 rejected，不成交、不抛出成交后异常。
9. 有效退出配置在成交后直接激活，并以实际成交价初始化 trailing anchor。
10. terminal pending 订单会清理对应退出参数元数据。

## 测试覆盖

1. 高手续费组合关闭不会部分成交。
2. 提交时资金不足的限价单立即 rejected。
3. 提交后资金被占用的限价单在触发时原子 rejected。
4. pending 期间持仓方向变化不会产生半完成成交。
5. 有效退出配置在限价成交后正常激活。
6. 取消和拒绝订单不会残留 pending 元数据。

## 验证

```text
pytest -q tests/test_broker.py tests/test_strategy.py tests/test_design_mvp.py
50 passed

python -m compileall -q minbt tests examples
通过

pytest -q
112 passed
```

## 结论

`PLAN-022` 的行为目标已经完成。限价单资金预留、部分成交和订单簿撮合仍不进入当前 MVP。
