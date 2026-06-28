# PLAN-006 示例体系更新计划

## 背景

当前 `examples/` 只有 `demo_mini.py`，该示例使用随机下单和绘图，能作为最小运行 demo，但不适合作为典型策略参考。用户希望同时具备单标的和多标的示例，并且各个示例要典型。

## 目标

1. 保留一个最小可运行示例，降低新用户入门成本。
2. 新增单标的典型示例，展示 `on_data(row)`、市价单、目标仓位调整和历史结果输出。
3. 新增多标的典型示例，展示 `on_bar(dt, rows_by_symbol)`、同一时间截面决策和组合轮动。
4. 示例应可重复、无随机行为、默认不依赖绘图。
5. README 应清楚列出每个示例的用途和运行命令。
6. 测试应覆盖示例能从仓库根目录运行。

## 实施方案

### 1. 单标的示例

- 新增 `examples/single_symbol_sma.py`。
- 使用 `examples/data.csv` 中的 BTCUSDT 行情。
- 策略采用典型的双均线趋势跟随：
  - 快均线高于慢均线时做多。
  - 快均线低于慢均线时做空。
  - 每次只调整到目标仓位，避免重复加仓。
- 输出最终权益、现金和持仓。

### 2. 多标的示例

- 新增 `examples/multi_symbol_rotation.py`。
- 使用脚本内构造的多标的内存行情，避免新增数据文件。
- 策略采用典型的横截面动量轮动：
  - 在同一 bar 内比较多个标的过去 N 期收益率。
  - 持有动量最高的标的，清空其他标的。
  - 使用 `on_bar(dt, rows_by_symbol)`，展示完整同一时间截面数据。
- 输出最终权益、现金和持仓。

### 3. 最小示例

- 将 `examples/demo_mini.py` 改为确定性的最小单标的示例。
- 移除随机下单和默认绘图依赖，保留最少代码路径。

### 4. 测试与文档

- 更新 `tests/test_examples.py`，覆盖三个示例脚本。
- 更新 README 的示例列表和运行命令。
- 生成 `PLAN-006-examples-OUTCOME.md` 记录结果。

## 验证命令

```bash
pytest -q tests/test_examples.py
pytest -q
python -m compileall -q examples tests minbt
git diff --check
```
