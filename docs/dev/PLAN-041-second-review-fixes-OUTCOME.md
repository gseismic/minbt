# PLAN-041 二次 Review 修复 — 结果

## 概述

二次 review 发现 P1×2 + P2×4 + P3×3 共 9 项问题。全部修复完成，175 个测试通过（较修复前 145 → 175，+31 新退出测试 - 1 合并去重）。

## 执行摘要

- P1 代码修复 3 处：类型标注 2 处 + get_orders 过滤 1 处
- P2 测试补充 1 处：新建 `tests/test_exit_conditions.py`（31 个测试）
- P2 示例降级 1 处：11 个示例 matplotlib 优雅降级
- P3 异常捕获 1 处：3 个宽泛 `except Exception` 改为具体类型
- P3 测试合并 1 处：`test_portfolio.py` + `test_portfolio2.py` → 合并去重
- P3 sys.path 补全 1 处：示例 06/07/08 与其他示例一致
- 验证：`compileall` 通过，`pytest` 175 passed，`lsp_diagnostics` 0 error

## 变更文件

### P1 代码修复

- `minbt/broker/exit.py`
  - `ExitContext.state: Dict = None` → `state: Optional[Dict] = None`（修复 Pyright 类型错误）

- `minbt/data/feed.py`
  - `FeedEvent.prices: Mapping[str, float] = None` → `prices: Optional[Mapping[str, float]] = None`
  - 同步 import：`from typing import ... Optional ...`

- `minbt/broker/broker.py`
  - `get_orders()` 过滤 `source="cancel_order"` 的动作订单，避免用户看到重复 canceled 订单

### P2 测试补充

- `tests/test_exit_conditions.py`（新建，31 个测试）
  - 第一类：exit.py 4 个工厂函数单元测试（20 个）
    - `stop_loss_pct` / `take_profit_pct` / `stop_loss_price` / `take_profit_price`
    - 每个函数覆盖：多头触发、空头触发、零仓位、参数校验、命名
  - 第二类：空头退出条件集成测试（6 个）
    - 空头止损 / 空头止盈 / 空头追踪止损 pct + 未触发验证 + cash 断言
  - 第三类：trailing_stop_amount 集成测试（5 个）
    - 多头 trailing_stop_amount / 空头 trailing_stop_amount + anchor 连续移动验证

### P2+P3 示例降级 + sys.path

- `examples/01_demo_mini.py` ~ `examples/11_crypto_binance_feed.py`（11 个文件）
  - matplotlib 未安装时 `raise SystemExit` 提示 `pip install minbt[plot]`，不抛 ImportError traceback
- `examples/06_scenario_single_breakout.py` / `07_scenario_multi_rotation.py` / `08_scenario_pairs_mean_reversion.py`
  - 补充 `sys.path` 引导代码，与其他 8 个示例一致

### P3 异常捕获

- `minbt/exchange.py`
  - `_normalize_dt`: `except Exception` → `except (ValueError, TypeError, OverflowError)`
  - `_dt_sort_key`: `except Exception` → `except (ValueError, TypeError, OverflowError)`
- `minbt/broker/market.py`
  - `_to_datetime`: `except Exception` → `except (ValueError, TypeError, OverflowError)`

### P3 测试合并

- `tests/test_portfolio.py`（合并后 16 个测试）
  - 合并原 `test_portfolio.py`（9 个）+ `test_portfolio2.py`（8 个），去除 1 个重复（`test_margin_liquidation` 被 `test_isolated_margin_liquidation` 替代）
- `tests/test_portfolio2.py`（已删除）

## 验证结果

```bash
python -m compileall -q minbt tests examples
# 通过，无输出

python -m pytest -q
# 175 passed in 26.02s
```

`lsp_diagnostics` 检查 `exit.py` / `feed.py`：0 error（修复前各 1 个 `reportAssignmentType` 错误，已消除）。

## 修复对照

| # | 修复项 | 类型 | 严重度 | 状态 |
|---|---|---|---|---|
| 1 | exit.py `state: Dict = None` 类型标注 | P1 | 高 | ✅ |
| 2 | feed.py `prices: Mapping = None` 类型标注 | P1 | 高 | ✅ |
| 3 | get_orders 过滤 cancel_order 动作订单 | P1 | 高 | ✅ |
| 4 | exit.py 4 个工厂函数测试 | P2 | 中 | ✅ |
| 5 | 空头退出条件测试 | P2 | 中 | ✅ |
| 6 | trailing_stop_amount 测试 | P2 | 中 | ✅ |
| 7 | 示例 matplotlib 降级 | P2 | 中 | ✅ |
| 8 | 宽泛 except Exception 改为具体类型 | P3 | 低 | ✅ |
| 9 | 合并 test_portfolio 文件 | P3 | 低 | ✅ |
| 10 | 示例 06/07/08 sys.path 补全 | P3 | 低 | ✅ |

## 测试数量变化

| 阶段 | 测试数量 | 变化 |
|---|---|---|
| PLAN-040 后 | 145 | — |
| 合并 test_portfolio 去重 | 144 | -1 |
| 新增 test_exit_conditions | 175 | +31 |
