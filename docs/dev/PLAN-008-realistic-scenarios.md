# PLAN-008 真实场景示例与不足分析计划

## 背景

minbt 的目标是方便快捷地完成回测。现有示例已经覆盖最小单标的、单标的均线、多标的轮动，但还不够接近实际研究工作中会遇到的策略形态和使用痛点。

## 目标

新增一组可直接运行的真实场景示例，用场景反推当前框架在快捷回测上的不足：

1. 单标的趋势突破：包含波动过滤、仓位目标、止损和换仓。
2. 多标的横截面轮动：包含多资产同截面、动量排序、等权目标仓位和再平衡。
3. 双标的配对均值回归：包含价差 z-score、双腿持仓、同步调仓和退出条件。
4. README 和测试同步这些示例。
5. 输出场景分析文档，明确 minbt 下一步最该补的能力。

## 实施方案

### 示例组织

- 新增 `examples/example_utils.py`，放置示例共用的项目路径注入、静默 logger 和目标仓位下单辅助函数。
- 新增 `examples/scenario_single_breakout.py`。
- 新增 `examples/scenario_multi_rotation.py`。
- 新增 `examples/scenario_pairs_mean_reversion.py`。

所有示例使用确定性合成行情，不依赖网络或外部数据源，确保 CI 和本地都能稳定运行。

### 文档

- README 增加“真实场景示例”列表和运行命令。
- 新增 `docs/dev/PLAN-008-realistic-scenarios-OUTCOME.md`，记录示例结果和不足分析。

### 测试

- 更新 `tests/test_examples.py`，把新示例纳入 subprocess 冒烟测试。
- 要求每个示例输出 `final_equity=`。

## 验证命令

```bash
python examples/scenario_single_breakout.py
python examples/scenario_multi_rotation.py
python examples/scenario_pairs_mean_reversion.py
pytest -q tests/test_examples.py
pytest -q
python -m compileall -q examples tests minbt
git diff --check
```

## 非目标

- 不接入真实交易所数据。
- 本计划只新增示例和分析，不单独实现限价单、止盈止损、滑点、订单簿或部分成交等核心能力。
- 不改变核心撮合模型，只通过示例暴露不足。
