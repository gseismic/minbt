# PLAN-059：简化入门示例和文件命名

- 创建时间：2026-10-12 14:30（Asia/Shanghai）。
- 模型：Codex；环境仅提供 GPT-6 系列信息，实际模型 ID 未提供，文件名使用 `model-unknown`。
- 分析范围：当前 `examples/`、示例测试、README 和维护中的示例引用。
- 基准提交：`768b213710a95f0c2cd2c38b39eee39ee4ebef37`；实施结果属于 WORKTREE。

## 目标和依据

用户希望第一个例子的代码极度简单，文件命名也简单易懂。当前排在最前面的盈亏示例同时讲解多空、手续费和订单明细，最小示例又包含 CSV 读取及步数状态，不适合作为首次阅读入口。

将入门示例改为两条内联行情、一个买入并持有的策略回调、最终权益和两行绘图。其他示例保留现有行为，盈亏专题后移。文件名统一采用两位阅读顺序编号和用途名称，替代三位分类编号及重复的类别前缀。

## 命名映射

| 当前文件 | 新文件 |
| --- | --- |
| `001_core_demo_mini.py` | `01_quickstart.py` |
| `002_core_single_symbol_sma.py` | `02_moving_average.py` |
| `003_core_multi_symbol_rotation.py` | `03_rotation.py` |
| `100_scenario_exit_rules.py` | `04_exit_rules.py` |
| `101_scenario_limit_order.py` | `05_limit_orders.py` |
| `102_scenario_single_breakout.py` | `06_breakout.py` |
| `103_scenario_multi_rotation.py` | `07_rebalance.py` |
| `104_scenario_pairs_mean_reversion.py` | `08_pairs_trading.py` |
| `105_scenario_cross_market.py` | `09_cross_market.py` |
| `106_scenario_run_control.py` | `10_run_control.py` |
| `000_core_pnl_sanity_check.py` | `11_pnl.py` |
| `200_benchmark_100k_empty.py` | `12_benchmark.py` |
| `300_feed_crypto_binance.py` | `13_binance_feed.py` |
| `301_feed_csv.py` | `14_csv_feed.py` |
| `302_feed_iosql.py` | `15_iosql_feed.py` |
| `400_exchange_replay_modes.py` | `16_replay_modes.py` |
| `401_exchange_generic_bar_storage.py` | `17_bar_storage.py` |

## 范围和约束

- 重命名当前全部 17 个独立示例，并简化首例；保留每个示例的内联绘图。
- 同步 README 快速开始、阅读顺序、使用指南、测试路径及维护中的设计文档引用。
- 已完成的计划、Review、历史绘图设计、v0 快照和旧交接记录保留历史名称；问题记录保留原始依据，追加当前路径说明。
- 不修改 minbt 公共接口和内部实现，不新增共享示例工具，不改其他策略或外部 Feed 配置。
- 根据用户后续明确要求，将本次变更及计划、结果提交到本地 Git。

## 实施步骤

1. [x] 核对当前示例、命名规则、引用和验证环境，完成计划自查。
2. [x] 按映射重命名，首例使用默认零手续费，以 100、120 两条行情展示目标持仓 1 和最终权益 1020。
3. [x] 同步当前文档及测试引用，README 快速开始与首例保持一致。
4. [x] 自行审阅差异，验证新首例、既有示例测试及盈亏测试，运行 Ruff、路径检查和差异检查。
5. [x] 记录结果并更新计划索引。

实施结果见 [PLAN-059 结果](PLAN-059-simple-examples-model-unknown-OUTCOME.md)，完成时间为 2026-10-12 14:38（Asia/Shanghai）。

后续授权记录：2026-10-12 14:45（Asia/Shanghai），用户要求“提交”；由 Codex 更新，实际模型 ID 未提供。提交范围为本计划的实施变更，具体提交编号以 Git 日志为准。

## 验证和完成标准

- 首例没有 CSV、数据文件依赖、步数状态、额外生命周期回调或运行包装函数；买入逻辑只有一行目标持仓调用。
- 首例实跑得到最终权益 1020、持仓 1、权益曲线 `[1000, 1020]`，只有一笔实际成交。
- `python -m pytest -q tests/test_examples.py tests/test_pnl.py` 通过；保留非交互绘图设置及 fake Binance Feed，CSV 和 iosql 的外部数据不作为本次验证前提。
- `ruff check examples tests/test_examples.py`、`git diff --check` 通过。
- 当前示例和维护中的文档、测试只引用现存的新路径；历史记录中的旧路径有明确历史语境。

## 自查、风险和回滚

- 使用现有 `order_target_size()` 表达持有一个单位，后续行情不会重复买入；权益包含未平仓的浮动盈亏，README 明确解释结果。
- 重命名会改变原示例命令，README 和使用指南必须同时更新；不保留重复示例作为旧名入口。
- 其他 16 个示例只改文件名，数据文件继续位于原目录。
- 必要时逐项逆向重命名并恢复本次首例及引用差异，不覆盖范围外改动。
