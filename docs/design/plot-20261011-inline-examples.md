# 示例内联绘图设计

## 背景

用户希望运行示例后能直接看到图表。示例必须独立运行，因此绘图代码写在各自脚本中，不使用共享 `plot_utils.py`。

## 设计

- 当前维护的每个 `examples/*.py` 脚本直接导入 `matplotlib.pyplot`，在主入口运行示例后调用 `plt.show()`。
- 策略和数据 Feed 示例绘制 `Strategy.get_hist_equity()` 权益曲线。
- 盈亏 sanity check 在同一张图中绘制各场景的净盈亏曲线和零盈亏线。
- 100k 基准示例绘制数据构造、加载和回放各阶段的耗时。
- 图表仅使用公开结果数据；不为画图增加核心 API 或共享模块。
- 不指定 Matplotlib 后端，交互环境由 Matplotlib 选择；自动化测试使用 `Agg` 后端。
- Matplotlib 作为可选依赖保留，运行示例前可执行 `pip install -e ".[plot]"`。

## 逐例图表

| 示例 | 图表 |
|---|---|
| `01_quickstart.py` 至 `10_run_control.py` | 回测权益曲线；首例只调用 `plt.plot()` 和 `plt.show()` |
| `11_pnl.py` | 多空及手续费场景的净盈亏曲线 |
| `12_benchmark.py` | 各阶段耗时 |
| `13_binance_feed.py` 至 `15_iosql_feed.py` | Feed 回测权益曲线 |
| `16_replay_modes.py`、`17_bar_storage.py` | 通用 Bar 回测权益曲线 |

## 约束

- 不增加 `example_utils.py`、`plot_utils.py` 或其他示例共用文件。
- 不在示例中加入重复的可选依赖 try/except 检查；缺少 Matplotlib 时保留直接导入错误。
- 示例按需依赖各自明确的数据源；该数据源约束不由绘图代码处理。
