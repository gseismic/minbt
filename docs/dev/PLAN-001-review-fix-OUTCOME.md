# PLAN-001-review-fix-OUTCOME

## 审查结果
- 已确认删除的 `_exchange_api.py`、`broker/order.py`、`broker/backup/broker_deprecated.py_` 没有剩余代码引用。
- 发现 `pytest` console-script 会优先导入环境中已安装的 `minbt`，导致测试和当前工作区代码不一致。
- 发现 `Strategy` 在缺少 `pyta_dev` 时，仓位历史回退容器不能追加记录。
- 发现 `Strategy` 允许 `broker=None`，但回调后仍会访问 broker 历史接口。
- 发现 `Broker.get_position_sizes` 与 `Portfolio.get_position_sizes` 的空仓过滤行为不一致。
- 发现 `get_figax` 已改为接收 `tx_colors`，但颜色没有应用到新增 y 轴。

## 修复内容
- 新增 `pytest.ini`，保证 `pytest` 和 `python -m pytest` 都优先加载当前仓库源码。
- 将 `pyta_dev` 向量依赖改为懒加载，并提供 list 回退实现。
- 补齐 `Strategy` 对 broker 协议的结构约束，修复 broker 为空时的历史记录行为。
- 让 `Broker.get_position_sizes` 复用 `Portfolio.get_position_sizes`，过滤空仓。
- 修复 `Portfolio.close_position` 平仓方向，并增加多仓、空仓、空仓位测试。
- 移除可变默认参数，应用 `get_figax` 的 y 轴颜色配置。
- 新增策略测试覆盖无 `pyta_dev`、无 broker、指定 portfolio 统计。

## 验证结果
- `python -m pytest -q tests/test_strategy.py`: 3 passed。
- `python -m pytest -q tests/test_portfolio.py`: 8 passed。
- `pytest -q`: 37 passed，1 warning。
- `python -m pytest -q`: 37 passed，1 warning。

## 剩余风险
- 测试环境仍会输出来自 polars 的 `Polars binary is missing!` warning，但不影响当前测试结果。
