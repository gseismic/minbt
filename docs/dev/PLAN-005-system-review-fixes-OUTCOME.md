# PLAN-005 系统审查问题修复结果

## 实施概览

本次按 `PLAN-005-system-review-fixes.md` 修复了系统审查中发现的核心问题，重点是多资产回测语义、运行时校验可靠性、查询接口副作用和用户入口可用性。

## 主要变更

### 1. 显式运行时校验

- 将 `Broker`、`Portfolio`、`Cash`、`Position`、`Strategy`、`Exchange` 中面向用户输入或运行状态的 `assert` 改为显式异常。
- 用户参数错误统一使用 `ValueError` 或 `TypeError`。
- 内部不变量失败使用 `RuntimeError`。
- `Broker` 与 `Portfolio` 的保证金阈值规则统一为 `0 <= min_margin_level < warning_margin_level < 1`。
- 增加 `python -O` 子进程测试，确认优化模式下非法 Broker 参数仍被拒绝。

### 2. 多资产 bar 级回测

- 新增 `Strategy.on_bar(dt, rows_by_symbol)` 默认钩子。
- `Exchange.run()` 现在按同一 `date_key` 聚合 bar。
- 每个 bar 会先更新 Exchange 和各个策略 Broker 中所有 symbol 的最新价，再触发 `on_data(row)` 和 `on_bar(dt, rows_by_symbol)`。
- 策略权益和持仓历史改为每个 bar 记录一次，避免多标的同一时间点重复记录。
- 新增测试验证第一条 `on_data` 回调也能看到同一时间点完整的多标的价格。

### 3. 查询接口无副作用

- `Portfolio.get_position_size()` 查询不存在 symbol 时返回 `0`，不创建空仓位。
- `Portfolio.get_position_equity()` 查询不存在 symbol 时返回 `0`。
- `Broker.get_position()` 增加 `create_if_missing` 参数，默认保持兼容；只读查询可显式关闭创建。
- 新增测试确认 `broker.get_position_size("UNKNOWN")` 不污染 `positions`。

### 4. 用户入口和依赖

- `examples/demo_mini.py` 使用 `Path(__file__)` 定位 `data.csv`。
- 示例脚本运行时将项目根目录加入 `sys.path`，避免直接运行时导入到其他已安装的 `minbt`。
- `setup.py` 增加 `plot` extra，声明 `matplotlib`。
- 新增示例冒烟测试，使用 `MPLBACKEND=Agg` 从仓库根目录执行 `python examples/demo_mini.py`。

### 5. 日志和组合关闭

- `create_logger()` 不再调用 loguru 全局 `remove()`，避免清空使用方已有 sink。
- 新增测试确认创建 minbt logger 后外部 loguru sink 仍可接收日志。
- `Broker.close_portfolio()` 改为先平仓成功，再从 `portfolios` 删除并释放现金。
- 新增测试确认关闭失败时 portfolio 不会提前丢失。

### 6. 文档与 skill 更新

- README 增加 `on_bar`、bar 级价格更新、保证金合约账户模型和 `plot` extra 说明。
- 更新 `skills/minbt-usage/SKILL.md`，同步新的多资产回测语义和测试命令。

## 验证结果

```bash
pytest -q
# 59 passed, 1 warning

python -m compileall -q minbt tests examples
# passed

git diff --check
# passed

PYTHONPATH=. python -O - <<'PY'
from minbt import Broker
try:
    Broker(initial_cash=1000, fee_rate=2, portfolio_cash=2000, leverage=0)
except ValueError as exc:
    print(type(exc).__name__)
else:
    raise SystemExit('invalid broker was accepted')
PY
# ValueError
```

当前唯一 warning 为测试环境中的 `Polars binary is missing!`，与本次变更无关。

## 后续关注

- 限价单、止盈止损、追踪止损仍未实现。
- 当前撮合仍按 `close` 市价成交，未模拟滑点、订单簿、部分成交和成交概率。
- `create_logger()` 仍基于 loguru 全局 logger 添加 sink；本次只修复不再移除外部 sink，后续如需更强隔离，可进一步设计日志配置 API。
