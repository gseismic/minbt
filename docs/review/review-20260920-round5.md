# 全量代码 Review 报告·第五轮（2026-09-20）

## 背景

上一轮全量 review 见 `docs/review/review-20260920-full-code.md`（第四轮），其建议的修复计划 `docs/dev/PLAN-042-review-fixes.md` 尚未立项实施。本轮基线为 main @ 750ed86：相对上轮 review 时的代码（ae3e7c5）仅有 docs 类提交，**核心源码零改动**。

因此本轮有两个目标：

1. **复测**上轮全部发现是否仍然成立（代码未变，预期全部仍在，关键行为类项目逐一重跑复现）；
2. 以全新视角通读代码，寻找**前四轮均未覆盖的新问题**。

本轮新发现编号采用 `R5-` 前缀，与上轮报告编号相互独立，避免 PLAN 引用时混淆。

## Review 范围与方法

- **范围**：`minbt/` 全部核心源码约 3900 行（broker 8 文件、exchange、strategy、data/feed、data/binance、plot、logger、各 `__init__`），`examples/example_utils.py`、`examples/plot_utils.py`，以及 `tests/` 12 个测试文件。
- **方法**：
  1. 逐文件独立通读源码（不依赖上轮报告结论）；
  2. 运行完整测试套件 `python -m pytest tests -q`；
  3. 对全部行为类疑点（含本轮新发现）编写独立运行时脚本复现验证；
  4. 对照上轮报告，确认新发现无重复。

## 结论摘要

架构质量评价与上轮一致：Broker/Portfolio/Position 分层清晰、输入校验充分、退出条件状态机与 T+1 锁仓设计完善。上轮全部发现（P1-1、P2-1/2/3、P3-1..7）**均未修复且仍可复现**（见下表）。

本轮新发现：

| 级别 | 编号 | 概述 |
| --- | --- | --- |
| P1 应修复 | R5-P1-1 | `close_portfolio` 移除子组合后，遗留 pending 限价单触发未捕获异常，回测事件循环崩溃 |
| P2 建议修复 | R5-P2-1 | pyta2 环境下 `get_hist_position_sizes` 对未交易 symbol 抛 KeyError（行为随可选依赖变化，与上轮 P1-1 同族） |
| P2 需决策 | R5-P2-2 | tz-aware 非 UTC 数据 + 带 `trading_sessions` 的市场（如 A_STOCK）：所有订单被静默拒绝 |
| P3 信息性 | R5-P3-1 | `_normalize_dt(None)` 静默返回 NaT，NaT 数据一路放行 |
| P3 信息性 | R5-P3-2 | `Portfolio.get_position` 默认创建空仓位对象，`Portfolio.close_position/close_all_positions`（门面未使用的公开 API）会在 `_positions` 留下空壳 |
| P3 信息性 | R5-P3-3 | Binance 层 `_interval_to_ms` 不支持 Binance 实际提供的 `1w`/`1M` 周期 |

## 上轮发现复测状态

| 上轮编号 | 状态 | 复测方式 |
| --- | --- | --- |
| P1-1 pyta2 下测试失败 | **仍在** | `pytest tests -q` → 1 failed, 174 passed（失败用例与上轮一致） |
| P2-1 `_is_multiple` 浮点容差 | **仍在** | `_is_multiple(60000.0, 0.00001)` 仍返回 `False` |
| P2-2 `get_positions()` 泄漏内部字典 | **仍在** | 对返回值 `d["HACK"]=...; d.pop("AAPL")` 后 broker 内部 `_positions` 同步被改 |
| P2-3 加仓静默替换退出条件 | **仍在** | 代码未变（上轮已运行时复现） |
| P3-1..P3-7 及三条备忘 | **均未修复** | 代码未变，逐项目测确认 |

## P1 应修复（本轮新增）

### R5-P1-1 `close_portfolio` 移除子组合后，遗留 pending 限价单使事件循环崩溃

- **位置**：`minbt/broker/broker.py:1020-1034`、`1079-1082`（`close_portfolio` 的两个移除组合分支）与 `minbt/broker/broker.py:749-752`（`process_pending_orders` 无组合存在性兜底）。
- **触发条件**：子组合中存在 **pending 限价单** 时调用 `close_portfolio`（无论该组合有无持仓：无持仓走"skipped"分支直接移除组合；有持仓走平仓后移除分支）。`close_portfolio` 只处理持仓，**完全不处理 pending 订单**，组合被 pop 后订单仍留在 `_pending_order_ids`。
- **现象**（已运行时复现）：价格随后触及限价，`process_pending_orders` 在 `get_position_size(portfolio=...)` 处抛出未捕获异常：

  ```
  File "minbt/broker/broker.py", line 749, in process_pending_orders
      expected_position_size = self.get_position_size(
  File "minbt/broker/broker.py", line 103, in _require_portfolio
      raise ValueError(f"portfolio not found: {portfolio}")
  ValueError: portfolio not found: p1
  ```

  即使绕过第 749 行（如 exit params 为空时仍会走到 `_execute_existing_order`），后续 `self.portfolios[order.portfolio].submit_order(...)`（`broker.py:443`）也会 KeyError。该异常发生在 `Exchange.run()` 事件循环内（`_process_brokers_before_callbacks`），**直接终止整个回测且无法恢复**。
- **已排除的相邻路径**：`close_portfolio` 平仓成交时 `_after_order_filled` 会正确清理 exit state（`new_size==0` → `_clear_position_exit`），因此 active exit 不会踩中此问题；`cancel_order` 也不访问组合。问题仅限 pending 限价单。
- **修复建议**（两层，建议都做）：
  1. **原子性**：`close_portfolio` 开始时若该组合存在 pending 订单（`any(o.portfolio == portfolio and o.status == "pending")`），要么整体拒绝（返回 rejected 订单说明原因，与现有"原子平仓计划"风格一致），要么先原子取消该组合全部 pending 订单再执行平仓/移除；
  2. **兜底**：`process_pending_orders` 遇到 `order.portfolio not in self.portfolios` 的订单时置为 rejected（reason 注明组合已移除）并从 pending 列表剔除，保证事件循环永不因陈旧订单崩溃。

## P2 建议修复（本轮新增）

### R5-P2-1 pyta2 环境下 `get_hist_position_sizes` 对未交易 symbol 抛 KeyError

- **位置**：`minbt/strategy.py:157-162`。
- **问题**（已运行时验证）：无 pyta2 时 `get_hist_position_sizes("NOPE")` 返回 `[0, 0, ...]`；pyta2 可用时走 `VectorTable.get_column` 分支，对从未出现过的 symbol 直接抛 `KeyError: 'Column NOPE does not exist'`。同一 API 的缺失列语义随可选依赖安装状态改变，属于上轮 P1-1（`get_hist_equity` 返回类型随环境变化）的同族问题，但症状是**异常**而非类型差异，更容易在用户代码中炸出。
- **修复建议**：与 P1-1 一并处理——统一返回语义（如 pyta2 分支对缺失列回退为全 0 向量），或统一显式抛错并写入文档；测试侧补一个"未交易 symbol"用例。

### R5-P2-2 tz-aware 非 UTC 数据 + 交易时段市场：全部订单被静默拒绝

- **位置**：`minbt/exchange.py:474-486`（`_normalize_dt` 统一转 UTC）与 `minbt/broker/market.py:78-88`（`is_trading_time` 按 `value.time()` 与 `trading_sessions` 比较）。
- **问题**（已运行时复现）：用 tz-aware 的 Asia/Shanghai A 股数据喂 `set_bars` + `A_STOCK` 市场，09:35（北京）被规范化为 01:35 UTC，落在 09:30–11:30 时段判定之外，**所有订单被拒**（`not in trading time`）。而 naive 数据因 `tz_localize("UTC")` 保留墙钟数字，反而能通过——即"错误标注（无时区）能用、正确标注（有时区）被拒"，语义自相矛盾。且 `logger.disable("minbt")`（`minbt/logger.py:4`）使默认日志全静默，用户只能得到一个零成交的回测结果，问题极难定位。
- **现状说明**：README:215 只写了「策略回调收到的 `dt` 会统一为 UTC」，未提及 `trading_sessions`/`weekdays_only` 的判定钟点语义；设计文档中的 UTC 约定仅针对 data-feed 存储层。
- **处置建议**（二选一）：
  1. **文档方案**：在 README 与 `Market.trading_sessions` docstring 中显著说明「时段按规范化后的 UTC 钟点判定，tz-aware 数据需自行换算或使用 naive 墙钟」，并给出示例；
  2. **代码方案**：`is_trading_time` 改用规范化前的原始钟点（或在 `Market` 上增加显式 `session_tz`，判定时先转换），使 tz-aware 与 naive 数据语义一致。
  无论选哪种，建议同时明确默认日志策略（拒单 warning 是否应默认可见）。

## P3 信息性（本轮新增）

| # | 位置 | 问题与建议 |
| --- | --- | --- |
| R5-P3-1 | `minbt/exchange.py:474-486` | `_normalize_dt(None)` 静默返回 `NaT`（不报错）。含 None dt 的行会以 NaT 作为分组键参与排序（`_dt_sort_key` 中 NaT.value 极小，排最前）；`FeedEvent.dt=NaT` 也能通过 `isinstance(event.dt, datetime)` 校验（NaT 是 datetime 子类，`exchange.py:250`）；`is_trading_time(NaT)` 经 `_to_datetime` 视为"无 dt"。建议在 `_normalize_dt` 与 `_add_feed_event` 显式拒绝 None/NaT，将数据错误提前暴露。 |
| R5-P3-2 | `minbt/broker/portfolio.py:249、300-305` | `Portfolio.get_position` 默认 `create_if_missing=True`，`Portfolio.close_position` 对未知 symbol 会在 `_positions` 留下空壳 Position（进而出现在 `get_positions()` 输出中）。`close_position`/`close_all_positions` 是公开 API 但 Broker 门面从未调用。建议默认改为不创建，或在这两个入口改用 `create_if_missing=False`；与上轮 P2-2 的防御式拷贝一并处理。 |
| R5-P3-3 | `minbt/data/binance.py:446-453` | `_interval_to_ms` 仅支持 m/h/d，Binance 实际提供 `1w`/`1M` 周期，传入报 "interval must be like '1m', '5m', '1h', or '1d'"。建议要么补齐 w/M 换算，要么在报错消息中明确列出支持范围。 |

### 其他备忘（不计级）

- `Broker.orders` 与 `_exit_states` 只增不减，超长回测（百万级订单）下内存线性增长；可考虑提供归档/清理 API。
- `minbt/logger.py` 默认 `logger.disable("minbt")`：设计上避免库刷屏，但拒单/强平 warning 也一并静默（R5-P2-2 的定位困难部分源于此），可考虑仅 disable INFO/DEBUG。

## 验证记录

- `python -m pytest tests -q`：**1 failed, 174 passed**（失败项即上轮 P1-1）。
- R5-P1-1 复现脚本：`add_portfolio` → `submit_limit_order`（pending）→ `close_portfolio`（skipped，组合被移除）→ 新价格触及限价 → `process_pending_orders` 抛 `ValueError: portfolio not found: p1`（traceback 见上文）。
- R5-P1-1 排除性验证：同流程但持仓+止损退出条件，`close_portfolio` 平仓后 `check_exit_rules` 不报错（exit state 已被正确清理），确认问题仅限 pending 限价单路径。
- R5-P2-1 复现脚本：pyta2 环境下 `VectorTable().get_column("NOPE")` 抛 `KeyError`。
- R5-P2-2 复现脚本：Asia/Shanghai tz 的 A 股 bars + `A_STOCK` 市场，订单返回 `rejected / not in trading time: 2026-01-05 01:35:00+00:00`。
- R5-P3-1 复现脚本：`Exchange._normalize_dt(None)` 返回 NaT（`NaTType`）。
- 上轮 P2-1/P2-2 抽查复现脚本：结论不变（见"上轮发现复测状态"表）。

## 建议后续

上轮报告建议的 `docs/dev/PLAN-042-review-fixes.md` 仍未立项。建议将其范围扩大为：上轮 P1-1 + P2-1/2/3 + P3 全部 7 项 + 本轮 R5-P1-1 + R5-P2-1 + R5-P2-2 + R5-P3-1/2/3，一次立项、分批修复。其中需要先做语义决策的共三项：上轮 P2-3（加仓退出条件合并 vs 文档明示）、本轮 R5-P2-2（时段判定钟点语义）、以及默认日志可见性。
