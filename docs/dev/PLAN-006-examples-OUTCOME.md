# PLAN-006 示例体系更新结果

## 实施概览

本次检查后确认原有 `examples/demo_mini.py` 只有随机下单和绘图演示，不适合作为典型策略参考。已将示例体系调整为三层：最小示例、典型单标的策略、典型多标的策略。

## 主要变更

### 1. 最小示例

- 更新 `examples/demo_mini.py`。
- 移除随机下单和默认绘图依赖。
- 示例逻辑改为：BTCUSDT 开仓一次，固定步数后平仓。
- 默认静默 minbt 内部日志，只输出最终权益和最终持仓。

运行命令：

```bash
python examples/demo_mini.py
```

### 2. 单标的典型示例

- 新增 `examples/single_symbol_sma.py`。
- 使用 `examples/data.csv` 中的 BTCUSDT 行情。
- 策略为双均线趋势跟随：
  - 快均线高于慢均线时目标仓位为多头。
  - 快均线低于慢均线时目标仓位为空头。
  - 通过差额订单调整到目标仓位，避免重复加仓。
- 使用 `Strategy.on_data(row)`，适合作为单标的行级策略模板。

运行命令：

```bash
python examples/single_symbol_sma.py
```

### 3. 多标的典型示例

- 新增 `examples/multi_symbol_rotation.py`。
- 脚本内构造 BTCUSDT、ETHUSDT、SOLUSDT 的同时间截面行情。
- 策略为横截面动量轮动：
  - 在 `on_bar(dt, rows_by_symbol)` 中读取完整同一时间截面。
  - 比较过去 N 期收益率。
  - 持有动量最高的标的，清空其他标的。
- 该示例直接展示 PLAN-005 新增的多资产 bar 级语义。

运行命令：

```bash
python examples/multi_symbol_rotation.py
```

### 4. 文档与测试

- README 已更新三个示例的用途和运行命令。
- `skills/minbt-usage/SKILL.md` 已同步新的示例入口。
- `tests/test_examples.py` 改为参数化测试，覆盖三个示例脚本从仓库根目录运行。

## 验证结果

```bash
python examples/demo_mini.py
# final_equity=10000.05
# final_position=0.000000

python examples/single_symbol_sma.py
# final_equity=10001.29
# final_cash=9984.11
# final_position=0.002000
# trade_count=17

python examples/multi_symbol_rotation.py
# final_equity=10010.44
# final_cash=9885.44
# final_positions={'SOLUSDT': 1.0}
# last_selected=SOLUSDT
# rebalance_count=3

pytest -q tests/test_examples.py
# 3 passed

python -m compileall -q examples tests minbt
# passed

git diff --check
# passed

pytest -q
# 61 passed, 1 warning
```

唯一 warning 仍为当前环境的 `Polars binary is missing!`，与示例变更无关。
