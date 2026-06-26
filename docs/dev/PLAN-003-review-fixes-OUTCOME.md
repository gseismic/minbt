# PLAN-003-review-fixes-OUTCOME

## 修复内容
- 将 `Position` 的返回类型注解从 `tuple[...]` 改为 `typing.Tuple[...]`，保持 `python_requires >=3.8` 的导入兼容性。
- 将全仓模式的保证金水平改为账户级权益除以总保证金，使可用现金参与全仓风险缓冲。
- 全仓穿仓时将组合现金归零并清空仓位，避免清仓后权益错误恢复为剩余现金。
- 将 `Broker.get_total_equity()` 改为返回所有子组合权益加未分配现金，保留 `get_equity()` 作为默认组合权益查询。
- 增强 `I18nLogger` 的参数格式化：支持普通消息 `{}`、关键字格式化、无占位参数追加，以及 i18n 消息关键字格式化。

## 测试覆盖
- 新增 Python 3.8 注解兼容性回归测试。
- 更新全仓强平测试，按账户级权益计算风险。
- 新增全仓可用现金缓冲测试。
- 新增全仓穿仓后现金归零测试。
- 新增 broker 总权益包含多组合和未分配现金测试。
- 新增普通日志参数、无占位参数和 i18n 关键字参数格式化测试。

## 验证结果
- `pytest -q tests/test_position.py tests/test_portfolio2.py tests/test_broker.py tests/test_logger.py`: 29 passed，1 warning。
- `pytest -q`: 49 passed，1 warning。
- `python -m compileall -q minbt tests`: 通过。
- `git diff --check`: 通过。
- `rg -n "\b(tuple|list|dict|set)\[" minbt setup.py`: 无匹配，源码未继续使用 Python 3.9 内置泛型注解。

## 剩余风险
- 测试环境仍有 `Polars binary is missing!` warning，本轮未处理该环境依赖问题。
- 当前工作区存在与本次修复无关的 `README.md` 文案变更，本轮未回滚。
