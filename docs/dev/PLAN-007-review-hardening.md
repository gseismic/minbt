# PLAN-007 系统 review 后加固计划

## 背景

本计划承接系统 review 发现的问题，目标是在不扩大到限价单、止盈止损等新功能的前提下，修复当前工作树中的确定性缺陷和用户接口歧义。

## 目标

1. 强化多标的行情数据契约，避免重复 `(date_key, symbol)` 在 `on_data` 和 `on_bar` 中产生不一致语义。
2. 修复日志初始化重复添加 sink 的问题，避免导入或示例运行时重复输出日志。
3. 避免失败订单创建空仓位污染 `positions`。
4. 明确并保护多策略共享同一个 `Broker` 的语义，避免同一 bar 对同一 broker 重复喂价。
5. 统一 `date_key=None` 时的时间戳语义，使实现符合“使用行号”的文档描述。
6. 更新测试、README 和本地 skill 文档，确保用户接口说明与实现一致。

## 实施方案

### 1. Exchange 数据契约

- `date_key` 非空时，在 `set_data()` 阶段检查 `(date_key, symbol)` 是否唯一。
- pandas、polars、`list[dict]` 三类输入都需要覆盖。
- 重复时抛出 `ValueError`，错误信息包含重复键。

### 2. `date_key=None` 时间语义

- 对所有输入统一使用顺序行号作为时间戳。
- pandas 不再使用 DataFrame index 作为默认时间戳，避免非默认 index 或重复 index 改变 bar 分组。

### 3. 日志生命周期

- `create_logger()` 默认只返回绑定 logger，不主动添加 sink。
- 只有显式传入 sink 时才添加 sink，避免库导入时污染全局 loguru 配置。
- 示例脚本不再调用 `logger.remove()`；改用本地空 logger 让示例输出保持干净。

### 4. 失败订单副作用

- `Portfolio.submit_order()` 在资金不足或零数量等失败路径中不留下新建空仓位。
- 保持 `get_position()` 默认可创建仓位的兼容行为。

### 5. 共享 Broker 语义

- `Exchange._update_strategy_broker_for_bar()` 在每个 bar 内按 broker 对象去重喂价。
- 保持多个 strategy 可共享同一个 broker，但避免重复 `on_new_price()` 副作用。

## 测试计划

- 新增/更新 `tests/test_exchange.py`：
  - 重复 `(date_key, symbol)` 会报错。
  - pandas 自定义 index 下 `date_key=None` 仍使用顺序行号。
  - 共享 broker 在同一 bar 只喂价一次。
- 新增/更新 `tests/test_logger.py`：
  - 导入全局 logger 不重复添加 sink。
  - `create_logger()` 默认不添加 sink，显式传 sink 时才添加。
- 更新 `tests/test_portfolio2.py`：
  - 失败订单不污染 `positions`。
- 保持示例测试通过。

## 验证命令

```bash
pytest -q
python -m compileall -q minbt tests examples
git diff --check
```

## 非目标

- 不实现限价单、止盈止损、追踪止损。
- 不改变市价单以 `close` 成交的撮合模型。
- 不引入滑点、订单簿或部分成交模型。
