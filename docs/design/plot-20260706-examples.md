# 示例绘图功能设计

## 背景

绘图功能最初针对 11 个示例脚本设计，用于补充终端输出的可视化。当前 `examples/` 中的 16 个可运行示例采用分级编号命名，并在交互环境中弹出图表窗口。

## 目标

1. 每个示例运行后自动生成对应的可视化图表
2. 图表保存到 `examples/screenshots/` 目录（git ignored）
3. 在有图形界面的环境中默认弹出图表；关闭窗口后程序继续退出
4. 绘图工具模块可复用，各示例只需简单配置即可

## 设计决策

### 1. 截图目录

- 路径: `examples/screenshots/`
- git 忽略: 在 `.gitignore` 中添加 `examples/screenshots/`
- 自动创建: 首次绘图时自动创建目录

### 2. 共享绘图模块: `examples/plot_utils.py`

封装常用图表类型，避免每个示例重复绘图代码：

| 函数 | 用途 | 适用示例 |
|---|---|---|
| `plot_equity_curve(strategy, title)` | 绘制权益曲线 | 所有策略示例 |
| `plot_price_and_equity(strategy, bars_df, symbol, title)` | 价格+权益双面板 | `001_core_demo_mini`、`002_core_single_symbol_sma`、`300_feed_crypto_binance` |
| `plot_feed_price_and_equity(name, title, bar_records, strategy)` | Feed/通用 Bar 的价格+权益双面板 | `301_feed_csv`、`302_feed_iosql`、`400_exchange_replay_modes`、`401_exchange_generic_bar_storage` |
| `plot_multi_price_equity(strategy, bars_df, symbols, title)` | 多标的价+权益 | `003_core_multi_symbol_rotation`、`103_scenario_multi_rotation` |
| `plot_price_positions(strategy, bars_df, symbols, title)` | 价格+持仓变化 | `100_scenario_exit_rules`、`101_scenario_limit_order` |
| `plot_breakout(strategy, bars_df, symbol, title)` | 突破入场+权益 | `102_scenario_single_breakout` |
| `plot_pairs(strategy, bars_df, base, pair, title)` | 配对价差+z-score+权益 | `104_scenario_pairs_mean_reversion` |
| `plot_benchmark_timing(run_data, title)` | 基准测试耗时 | `200_benchmark_100k_empty` |
| `plot_cross_market(strategy, bars_df, sym_a, sym_c, title)` | 跨市场价格+分仓权益 | `105_scenario_cross_market` |
| `save_figure(name)` | 通用保存，自动管理路径和 `tight_layout` | 内部调用 |

### 3. 示例改造原则

- 仅在 `run_strategy()` 函数末尾（return 之前）添加绘图调用
- 不改变策略逻辑、不改变现有输出
- 单标的示例：读取原始数据传给绘图函数
- 多标的/合成数据示例：直接使用 `build_sample_data()` 的结果
- 不影响 `if __name__ == "__main__": run_strategy()` 的调用方式

### 4. 基准示例绘图

- `200_benchmark_100k_empty.py`: 空策略基准测试以阶段耗时柱状图展示性能

### 5. matplotlib 后端

不强制指定后端，由 Matplotlib 按运行环境选择交互后端。`save_figure()` 保存 PNG 后调用 `plt.show(block=True)`，用户关闭窗口后再关闭 Figure 并继续程序。自动化或无窗口运行可设置 `MINBT_EXAMPLE_SHOW=0`，保留截图但不弹窗。

## 各示例图表设计

| 示例 | 图表 | 说明 |
|---|---|---|
| 000_core_pnl_sanity_check | 多组净盈亏曲线和零盈亏基线 | 手算校验 |
| 001_core_demo_mini | 价格线 + 权益曲线（双面板） | 标注开仓/平仓点 |
| 002_core_single_symbol_sma | 价格+双均线（上） + 权益+持仓方向（下） | 看出金叉死叉与权益关系 |
| 003_core_multi_symbol_rotation | 四标的价走势（上） + 权益+动量排行（下） | 看出轮动效果 |
| 100_scenario_exit_rules | 双标的价格（上） + 持仓变化（下） | 追踪止损/止盈触发点 |
| 101_scenario_limit_order | 价格+限价线（上） + 持仓变化（下） | 限价单成交时机 |
| 102_scenario_single_breakout | 价格+高亮突破区（上） + 权益+z-score（下） | 突破入场+ATR止损 |
| 103_scenario_multi_rotation | 四标的走势（上） + 权益+选股标记（下） | 定期再平衡效果 |
| 104_scenario_pairs_mean_reversion | 价差+z-score+阈值线（上） + 权益曲线（下） | 均值回归信号 |
| 105_scenario_cross_market | 两标的价格（上） + 分仓权益（下） | A股+crypto分仓 |
| 200_benchmark_100k_empty | 各阶段耗时柱状图 | 性能基准 |
| 300_feed_crypto_binance | 价格+权益（双面板） | 真实币安数据 |
| 301_feed_csv | 价格+权益（双面板） | CSV K 线 Feed |
| 302_feed_iosql | 价格+权益（双面板） | iosql K 线 Feed |
| 400_exchange_replay_modes | 价格+权益（双面板） | 通用 Bar 和 Feed 回放 |
| 401_exchange_generic_bar_storage | 价格+权益（双面板） | 通用 Bar CSV 存储 |

## 实施计划

1. 创建 `examples/plot_utils.py`
2. 更新 `.gitignore`
3. 逐个更新当时编号为 01-11 的示例脚本
4. 验证所有示例可运行且截图生成正确
