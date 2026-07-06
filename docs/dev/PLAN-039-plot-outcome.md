# PLAN-039-plot-outcome.md

## 概述

为 examples/ 目录下所有示例脚本添加绘图功能，运行后自动生成可视化图表并保存到 git-ignored 截图目录。

## 执行摘要

- 创建了共享绘图模块 `examples/plot_utils.py`（~550 行），包含 9 个图表类型
- 新增 `examples/screenshots/` 到 `.gitignore`
- 11 个示例全部更新，运行后自动保存截图
- 设计文档: `docs/design/plot-20260706-examples.md`

## 变更文件

### 新增
- `examples/plot_utils.py` — 共享绘图工具模块
- `docs/design/plot-20260706-examples.md` — 设计文档
- `examples/screenshots/` — 截图输出目录（git ignored）

### 修改
- `.gitignore` — 添加 `examples/screenshots/`
- `examples/01_demo_mini.py` — +import +plot_price_and_equity
- `examples/02_single_symbol_sma.py` — +import +plot_price_and_equity(plot_ma=(12,36))
- `examples/03_multi_symbol_rotation.py` — +import +plot_multi_price_equity
- `examples/04_scenario_exit_rules.py` — +import +plot_price_positions
- `examples/05_scenario_limit_order.py` — +import +plot_price_positions
- `examples/06_scenario_single_breakout.py` — +import +plot_breakout
- `examples/07_scenario_multi_rotation.py` — +import +plot_multi_price_equity
- `examples/08_scenario_pairs_mean_reversion.py` — +import +plot_pairs
- `examples/09_benchmark_100k_empty.py` — +import +plot_benchmark_timing
- `examples/10_scenario_cross_market.py` — +import +plot_cross_market
- `examples/11_crypto_binance_feed.py` — +bar_records +import +plot_price_and_equity

## 图表功能覆盖

| 示例 | 图表类型 | 截图文件名 |
|---|---|---|
| 01 | 价格 + 权益双面板 | `01_demo_mini.png` |
| 02 | 价格+双均线 + 权益（标注多空） | `02_single_symbol_sma.png` |
| 03 | 多标的价格 + 权益 | `03_multi_symbol_rotation.png` |
| 04 | 双标的价格 + 持仓变化 | `04_scenario_exit_rules.png` |
| 05 | 价格 + 持仓变化 | `05_scenario_limit_order.png` |
| 06 | 价格+突破高亮 + 权益 | `06_scenario_single_breakout.png` |
| 07 | 多标的价格 + 权益 | `07_scenario_multi_rotation.png` |
| 08 | 价差+z-score+阈值 + 权益 | `08_scenario_pairs_mean_reversion.png` |
| 09 | 基准测试耗时柱状图 | `09_benchmark_100k_empty.png` |
| 10 | 跨市场价格 + 权益 | `10_scenario_cross_market.png` |
| 11 | 价格 + 权益（真实币安数据） | `11_crypto_binance_feed.png` |

## 验证结果

- `python -m compileall` 全部通过
- 示例 01-10 全部运行通过，截图正确生成
- 示例 11 需要 Binance API 网络连接（未在本环境测试）
- `examples/screenshots/` 已被 git 正确忽略

## 已知问题

- 示例 11 需要联网下载 Binance 数据，无网络时跳过
- matplotlib 为可选依赖，需 `pip install minbt[plot]` 或 `pip install matplotlib`
