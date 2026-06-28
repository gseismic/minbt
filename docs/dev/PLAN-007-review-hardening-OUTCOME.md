# PLAN-007 系统 review 后加固结果

## 实施概览

本次按 `PLAN-007-review-hardening.md` 完成系统 review 后的加固工作，重点修复数据契约、日志生命周期、失败订单副作用和共享 broker 喂价语义。

## 主要变更

### 1. 行情数据契约

- `Exchange.set_data()` 增加必需字段校验和重复截面校验。
- 当传入 `date_key` 时，`(date_key, symbol)` 必须唯一；重复数据会抛出 `ValueError`。
- `list[dict]` 输入改为 Exchange 原生迭代和排序，不再强制转换为 polars DataFrame。

### 2. 时间戳语义

- `date_key=None` 时，pandas、polars、`list[dict]` 都使用输入顺序行号作为时间戳。
- pandas 的 DataFrame index 不再影响默认时间戳和 bar 分组。

### 3. 共享 Broker 价格更新

- `Exchange.run()` 在每个 bar 内按 broker 对象去重更新价格。
- 多个策略共享同一个 broker 时，同一个 bar 内不会重复调用该 broker 的 `on_new_price()`。

### 4. 订单失败副作用

- `Portfolio.submit_order()` 对新标的先使用临时仓位做保证金校验。
- 资金不足等失败订单不再向 `positions` 写入空仓位。
- 保持 `get_position(..., create_if_missing=True)` 的兼容行为。

### 5. 日志生命周期

- `create_logger()` 默认只返回绑定 logger，不主动添加 loguru sink。
- 只有显式传入 `sink` 时才添加 sink。
- 全局 `minbt.logger` 导入时不再增加 loguru handler。
- 示例脚本不再调用全局 `logger.remove()`，改为给 `Exchange` 和 `Broker` 注入空 logger。

### 6. 文档和 skill

- README 同步说明：
  - 同截面 `symbol` 唯一约束。
  - `list[dict]` 原生支持。
  - `date_key=None` 使用输入顺序行号。
  - 共享 broker 按 bar 去重喂价。
- `skills/minbt-usage/SKILL.md` 同步新的数据契约、broker 日志注入和测试命令。

## 测试覆盖

- `tests/test_exchange.py`
  - 重复 `(date_key, symbol)` 报错。
  - pandas 自定义 index 不影响 `date_key=None` 时间戳。
  - `list[dict]` 输入可原生运行并按 `date_key` 排序。
  - 共享 broker 同一 bar 只更新一次。
- `tests/test_logger.py`
  - `create_logger()` 默认不添加 sink。
  - 显式 sink 可用且可清理。
  - 导入 `minbt.logger` 不增加 loguru handler。
- `tests/test_portfolio2.py`
  - 资金不足订单不创建空仓位。

## 验证结果

```bash
pytest -q
# 68 passed, 1 skipped, 1 warning

python -m compileall -q minbt tests examples
# passed

git diff --check
# passed
```

当前唯一 warning 仍为测试环境中的 `Polars binary is missing!`。polars DataFrame 构造用例在该环境下会跳过；pandas 和 `list[dict]` 路径已验证通过。

## 后续关注

- 限价单、止盈止损、追踪止损仍未实现，保持为非目标。
- 撮合模型仍按当前 `close` 市价成交，未模拟滑点、订单簿、部分成交。
- `I18nLogger.remove()` 仍直接透传 loguru remove；示例已避免使用该接口，后续如需更安全的日志 API，可单独设计 handler 管理能力。
