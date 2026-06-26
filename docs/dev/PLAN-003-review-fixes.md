# PLAN-003-review-fixes

## 目标
修复代码审查中确认的兼容性、权益统计、全仓保证金和日志参数问题，并补充聚焦回归测试。

## 修复范围
- `minbt/broker/struct.py`: 修复 Python 3.8 不兼容的内置泛型类型注解。
- `minbt/broker/portfolio.py`: 修正全仓模式的保证金水平、强平和穿仓后的权益状态。
- `minbt/broker/broker.py`: 明确总权益与默认组合权益的语义，修复多组合总权益统计。
- `minbt/utils/i18n_logger.py`: 让非 i18n 日志消息也能正确透传参数。

## 验证方式
- 为每个已发现问题增加或更新回归测试。
- 运行全量 `pytest -q`。
- 执行 `python -m compileall -q minbt tests`。
- 执行 `git diff --check`。

## 预期结果
- Python 3.8 用户不会因 `tuple[...]` 注解导入失败。
- 全仓模式使用账户级权益判断风险，不会在仍有可用现金覆盖亏损时提前强平。
- 穿仓后账户权益不会因为清空持仓而错误恢复为剩余现金。
- `Broker.get_total_equity()` 返回 broker 下所有组合和未分配现金的总权益。
- `I18nLogger` 对普通消息和 i18n 消息都支持参数格式化。
