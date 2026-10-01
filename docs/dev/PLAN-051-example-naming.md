# PLAN-051 示例文件分级编号命名

## 目标

按 `/home/lsl/macbook/pai-studio/skills/specs/example-naming.spec/SKILL.md` 的分级编号命名法重命名仓库当前 `examples/` 中的可运行示例，并同步维护中的路径引用。

文件名格式为 `{大类编号}{序号}_{类别}_{名称}.py`。采用一位大类编号、两位类内序号，类别标识与大类编号固定对应。

## 命名映射

| 大类 | 类别 | 旧文件 | 新文件 |
|---|---|---|---|
| 0 | core | `00_pnl_sanity_check.py` | `000_core_pnl_sanity_check.py` |
| 0 | core | `01_demo_mini.py` | `001_core_demo_mini.py` |
| 0 | core | `02_single_symbol_sma.py` | `002_core_single_symbol_sma.py` |
| 0 | core | `03_multi_symbol_rotation.py` | `003_core_multi_symbol_rotation.py` |
| 1 | scenario | `04_scenario_exit_rules.py` | `100_scenario_exit_rules.py` |
| 1 | scenario | `05_scenario_limit_order.py` | `101_scenario_limit_order.py` |
| 1 | scenario | `06_scenario_single_breakout.py` | `102_scenario_single_breakout.py` |
| 1 | scenario | `07_scenario_multi_rotation.py` | `103_scenario_multi_rotation.py` |
| 1 | scenario | `08_scenario_pairs_mean_reversion.py` | `104_scenario_pairs_mean_reversion.py` |
| 1 | scenario | `10_scenario_cross_market.py` | `105_scenario_cross_market.py` |
| 2 | benchmark | `09_benchmark_100k_empty.py` | `200_benchmark_100k_empty.py` |
| 3 | feed | `11_crypto_binance_feed.py` | `300_feed_crypto_binance.py` |
| 3 | feed | `12_csv_feed.py` | `301_feed_csv.py` |
| 3 | feed | `13_iosql_feed.py` | `302_feed_iosql.py` |
| 4 | exchange | `14_exchange_replay_modes.py` | `400_exchange_replay_modes.py` |
| 4 | exchange | `15_generic_bar_storage.py` | `401_exchange_generic_bar_storage.py` |

## 实施范围

1. 重命名以上 16 个可运行示例；共用模块、数据文件和 v0 归档不改名。
2. 同步示例内生成的截图名称、测试中的文件路径与动态模块名。
3. 更新 README、本地 usage skill、示例绘图设计、CSV/iosql 设计和 HANDOFF 中仍有效的示例路径。
4. 保留 `docs/dev` 和 `docs/review` 中已完成工作的历史记录。

## 验收

- 新脚本名符合规范，类别标识与大类编号稳定对应，序号在各类别内从 `00` 递增。
- 维护中的文档和测试只引用现存的新路径。
- 代码差异 review 确认只调整路径/命名，不改示例行为。
