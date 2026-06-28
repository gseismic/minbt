# PLAN-005 系统审查问题修复计划

## 背景

本计划用于修复系统审查中发现的架构、命名、逻辑和用户接口问题。目标是在保持现有单标的行级策略兼容的前提下，提升多资产回测语义、输入校验可靠性和用户入口可用性。

## 问题范围

1. 运行时代码大量使用 `assert` 做输入校验，`python -O` 会跳过校验并允许非法状态进入系统。
2. `Exchange.run()` 按行更新价格并立即调用策略，多资产同一时间点会出现半截面价格状态。
3. 查询未知标的持仓会创建空 `Position`，污染持仓状态。
4. `examples/demo_mini.py` 使用不稳定的相对路径读取 `data.csv`。
5. `Exchange.run()` 未设置数据时错误信息不清晰。
6. `Broker` 与 `Portfolio` 的保证金阈值约束不一致。
7. 默认 logger 创建会移除 loguru 全局 handler，影响使用方日志配置。
8. `Broker.close_portfolio()` 先移除 portfolio 再平仓，失败时状态不可恢复。
9. 资金和持仓命名、文档对保证金合约模型的解释不足。
10. 绘图示例依赖 `matplotlib`，但安装配置未声明。

## 修复方案

### 1. 显式校验替换 assert

- 将用户输入和公开接口校验改为 `ValueError` 或 `TypeError`。
- 将内部状态不变量校验改为 `RuntimeError`，避免优化模式跳过。
- 统一 `Broker` 和 `Portfolio` 的保证金阈值规则，要求 `0 <= min_margin_level < warning_margin_level < 1`。

### 2. 多资产截面回测

- 保留现有 `Strategy.on_data(row)`，保证已有单标的和行级策略继续可用。
- 新增 `Strategy.on_bar(dt, rows_by_symbol)`，用于同一时间点的多资产截面决策。
- `Exchange.run()` 在同一 `dt` 下先更新全部 symbol 的价格，再调用策略回调，避免策略看到半截面状态。
- 策略历史权益和持仓默认按 bar 记录一次，避免多资产同一时间点重复记录。

### 3. 查询接口无副作用

- `get_position_size()` 和 `get_position_equity()` 查询不存在标的时返回 `0`，不创建仓位。
- `get_position()` 保持可创建语义，用于需要显式获取或创建仓位对象的场景。

### 4. 用户入口和依赖

- 示例使用基于 `__file__` 的稳定数据路径。
- `Exchange.run()` 在未设置数据时抛出明确 `ValueError`。
- `setup.py` 增加 `plot` extra，声明 `matplotlib`。
- 文档说明 `python -m examples.demo_mini` 或直接脚本运行的可用方式。

### 5. 日志和组合关闭

- 调整 `create_logger()`，避免默认移除全局 loguru handler。
- `close_portfolio()` 改为先平仓成功，再从 `portfolios` 删除并释放资金。

## 测试计划

- 新增或更新 Exchange 测试，覆盖同一 `dt` 多标的价格先完整更新再触发策略、`on_bar` 回调和未设置数据错误。
- 新增或更新 Broker/Portfolio/Position/Cash 测试，覆盖显式异常、查询无副作用、`python -O` 下非法参数仍被拒绝。
- 新增示例测试，覆盖 `examples/demo_mini.py` 能从仓库根目录找到数据文件。
- 新增 logger 测试，覆盖创建 minbt logger 不清空外部 loguru sink。

## 验证命令

```bash
pytest -q tests/test_exchange.py tests/test_strategy.py tests/test_broker.py
pytest -q tests/test_portfolio.py tests/test_portfolio2.py tests/test_position.py tests/test_cash.py tests/test_logger.py
pytest -q
python -m compileall -q minbt tests
git diff --check
```

## 预期结果

- 多资产策略不再在同一时间点看到部分新价格和部分旧价格。
- 用户输入错误在正常模式和优化模式下都能被明确拒绝。
- 查询接口不污染持仓状态。
- 示例和文档中的入口命令可运行。
- 日志、依赖和文档契约更接近库用户预期。
