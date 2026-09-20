# 全量代码 Review 报告（2026-09-20）

## 背景

对本库核心源码进行第四轮全量 review（上一轮为 PLAN-041 二次 review）。本轮工作区为干净状态（main @ ae3e7c5），review 范围为当前已提交代码。

## Review 范围与方法

- **范围**：`minbt/` 全部核心源码约 3900 行（broker 8 文件、exchange、strategy、data/feed、data/binance、plot、logger、各 `__init__`），以及 `examples/example_utils.py`、`examples/plot_utils.py`、`tests/` 12 个测试文件。
- **方法**：
  1. 逐文件通读源码；
  2. 运行完整测试套件 `python -m pytest tests -q`；
  3. 对行为类疑点编写独立运行时脚本复现验证（非仅目测）；
  4. 对照 `docs/dev/PLAN-041-*-OUTCOME.md` 避免重复报告已修复项。

## 结论摘要

代码质量整体较高：Broker/Portfolio/Position 职责分层清晰，输入校验充分，退出条件状态机（每仓位一个 active exit order）设计合理，T+1 锁仓、原子平仓计划、Binance 覆盖区间缓存等细节完善，173+ 测试覆盖面广。PLAN-041 修复项无复发。

本轮发现：

| 级别 | 数量 | 概述 |
| --- | --- | --- |
| P1 应修复 | 1 | pyta2 环境下测试套件 1 例失败（环境相关的返回类型假设） |
| P2 建议修复 | 3 | tick 浮点误判拒单、get_positions 泄漏内部字典、加仓静默丢弃旧退出条件 |
| P3 信息性 | 7 | 死参数、报错消息拼接、sqlite 连接关闭、coverage 完整性等 |

## P1 应修复

### P1-1 pyta2 环境下测试失败：`get_hist_equity()` 返回类型依赖可选依赖

- **位置**：`tests/test_exchange.py:176`（同类写法 `tests/test_strategy.py:21-22`）
- **现象**：本机（已安装 pyta2）运行 `pytest` 结果为 **1 failed, 174 passed**。失败用例 `test_exchange_updates_full_bar_before_strategy_callbacks` 在断言 `strategy.get_hist_equity() == [1000, 1000]` 时抛出 `ValueError: The truth value of an array with more than one element is ambiguous`。
- **根因**：`Strategy._check_pyta()`（`minbt/strategy.py:69`）在 pyta2 可用时用 `NumpyVector` 记录历史，`get_hist_equity()` 返回 numpy 数组；数组与 list 的 `==` 产生数组，双元素数组转 bool 报歧义。单元素数组侥幸通过（`test_strategy.py` 5 例全绿即因此），属于环境相关的隐性失败。
- **修复建议**：
  1. 测试侧统一用 `list(strategy.get_hist_equity()) == [...]` 或 `np.testing.assert_array_equal`；
  2. 考虑让 `get_hist_equity()` 返回类型不随 pyta2 安装状态变化（如始终返回 list 或始终返回 ndarray），消除环境差异。

## P2 建议修复

### P2-1 `_is_multiple` 大比值浮点容差失效，会错误拒单

- **位置**：`minbt/broker/market.py:40-44`
- **问题**：容差 `abs(ratio - round(ratio)) < 1e-9` 加在"比值"上。当 `price / tick_size` 比值达 1e9 量级时，float64 除法误差（约 1e-6）超过容差，合法的 tick 倍数价格会被判为非法。
- **复现**（已运行时验证）：`_is_multiple(60000.0, 0.00001)` 返回 `False`——BTC 类高价标的配 1e-5 档 tick 时，`Market.validate_order` 会以 "price must be multiple of tick_size" 拒单。
- **修复建议**：容差必须按 `step` 的比例给出，不能按 `value` 比例（后者在大价格下容差会宽于半个 tick，导致非法价格放行）。已用 10 组用例（含比值 1e12 极端情况、半个 tick 偏离拒绝）验证：

  ```python
  def _is_multiple(value: float, step: Optional[float]) -> bool:
      if step is None or step == 0:
          return True
      nearest = round(value / step) * step
      return abs(value - nearest) <= step * 1e-4
  ```

  其中 `1e-4` 为噪声系数：float 噪声在比值 1e12 时约为 `step * 1e-4` 量级，而任何真实错误定价至少偏离半个 tick（`0.5 * step`），两者相差 3 个数量级以上，取值安全。也可改用 `Decimal` / 整数化方案彻底消除浮点问题。

### P2-2 `get_positions()` 返回内部字典，外部可篡改组合状态

- **位置**：`minbt/broker/portfolio.py:313-314`（`Portfolio.get_positions`），经 `minbt/broker/broker.py:1353-1355` 透传给用户。
- **问题**：直接返回 `self._positions` 内部字典。已运行时验证：外部对返回值执行 `d['HACK'] = ...` / `d.pop(...)` 会直接破坏 broker 状态，且极难排查。与 `Exchange.get_last_prices()`（`minbt/exchange.py:606-607`）返回副本的防御式做法不一致。
- **修复建议**：返回浅拷贝 `dict(self._positions)`。Position 对象仍共享引用（满足读取场景），字典结构不可被外部增删。`Portfolio.get_position_sizes()` 已是拷贝，无需改动。

### P2-3 同方向加仓时，旧订单的退出条件被静默整体替换

- **位置**：`minbt/broker/broker.py:385-417`（`_after_order_filled` → `_activate_standard_exit` → `_activate_exit_state`）
- **问题**：同方向加仓且新订单带部分退出参数时，`_activate_exit_state` 将旧订单的 exit state 置为 `inactive`，新 state 只包含新订单提供的参数——未提供的维度被静默丢弃。
- **复现**（已运行时验证）：
  1. `o1 = submit_market_order('AAPL', 10, price=100, take_profit_price=110)` → o1 exit: `take_profit_price=110, active=True`；
  2. `o2 = submit_market_order('AAPL', 10, price=100, stop_loss_price=95)` → o1 exit: `take_profit_price=110, active=False`；`get_active_order('AAPL')` 指向 o2，其 state 只有 `stop_loss_price=95`。
  - 结果：**止盈条件静默失效**，即使新订单根本没有提供止盈参数。
- **处置建议**（二选一）：
  1. 若"最后一次设置的退出条件整体生效"是设计语义，需在 README 与 `docs/design` 中显著说明，并考虑在文档示例中演示；
  2. 若非预期，建议对同方向加仓做参数级合并：新订单未提供的维度沿用当前 active state 的值（`_activate_standard_exit` 中仅覆盖非 None 维度，替换为"合并后整体生效"）。

## P3 信息性

| # | 位置 | 问题与建议 |
| --- | --- | --- |
| P3-1 | `minbt/exchange.py:512` | `_update_market_prices(self, feed, dt, payload)` 的 `payload` 参数从未使用，建议删除。 |
| P3-2 | `minbt/broker/struct.py:60-61` | `Cash.change_cash` 报错消息缺分隔符：`f"Cannot change cash to negative: {new_free_cash}"` 与 `f"amount: ..."` 相邻拼接，报错会显示成 `...negative: -5.0amount: -5, ...`，补逗号或空格。 |
| P3-3 | `minbt/broker/portfolio.py:200` | fake 预检分支的 `exec_type` 赋值后未使用，可改为 `_, fake_released_margin, ...`。 |
| P3-4 | `minbt/data/binance.py:217-220` 等多处 | `with self._connect() as conn` 只管理事务提交/回滚，不关闭连接，当前依赖 CPython 引用计数兜底。建议 `with contextlib.closing(self._connect()) as conn` 或 try/finally close。 |
| P3-5 | `minbt/data/binance.py:296-320` | `_download_range` 即使 API 返回不完整（如退市符号、接口截断），也会把 `[start_ms, coverage_end_ms)` 整段记为已覆盖，后续不再补下载，存在静默数据缺口风险。依赖对 Binance 返回连续性的信任，可接受，但建议加注释说明该假设。 |
| P3-6 | `minbt/exchange.py:488-496` | `_infer_epoch_unit` 启发式：早于 **1973-03-03**（即数值 < 1e11，1e11 ms ≈ 1973-03-03）的毫秒/微秒/纳秒时间戳会被误判为低一级单位（ms→s 等，结果早约 1000 倍）。1973-03-03 之后的毫秒时间戳（如 2001 年 ≈ 1e12）能被正确判定。若约定输入以 datetime/ISO 字符串为主可接受，建议 docstring 标注数值时间戳的判定边界。 |
| P3-7 | `minbt/broker/__init__.py` | `__all__` 漏列已导入的 `Position`、`Cash`、`Portfolio`；`from minbt.broker import *` 时不可见。 |

### 其他备忘（不计级）

- `minbt/exchange.py:440-443` `_group_rows` 排序使用原始 `date_key` 值，混合类型（如非 ISO 格式字符串）时排序结果可能与时间顺序不一致；当前约定 datetime/ISO 字符串输入下无影响。
- `minbt/broker/market.py:30-37` `_to_time` 对 `"10"` 这类不完整时间字符串会抛 unpacking 异常而非友好报错。
- `minbt/broker/struct.py:309-317` `Position.unlock_before` 会把 `opened_day=None` 的锁定批次直接解锁（视为"无 T+1 标记"）；当前 `Market.on_order_filled` 始终传 `trading_day(dt)`，仅 `dt=None` 时产生 None 批次，行为可接受但语义未在 docstring 说明。

## 亮点（保持项）

- 退出条件状态机：`_active_exit_order_by_position` + `_position_order_ids` 保证每仓位至多一个 active exit，反转/平仓/加仓的边界处理完备。
- `close_portfolio` 的原子平仓计划：先 `can_submit_orders` 全量预检，再逐笔执行，失败即整体拒绝。
- T+1 锁仓按"新增多头数量"精确锁定（`on_order_filled` 中 `opened_size = new_long - old_long`），反转开多的处理正确。
- Binance 数据层：coverage 区间缓存 + `closed_only` 剔除未收盘 K 线 + 断点续传设计合理。
- `Exchange.run()` 每次运行前整体拷贝 feed 数据（逐行 `dict(row)` 浅拷贝，行值为标量时等价于深拷贝），保证可重复运行不污染原始数据。

## 验证记录

- `python -m pytest tests -q`：**1 failed, 174 passed**（失败项即 P1-1）。
- P2-1 复现脚本：`_is_multiple(60000.0, 0.00001) == False`。
- P2-2 复现脚本：对 `get_positions()` 返回值插入/删除 key 后，broker 内部状态同步被改。
- P2-3 复现脚本：两笔加仓订单的 exit config 变化（详见 P2-3 描述）。

## 校验记录（2026-09-20 报告自查）

对上表全部发现逐项复核（行号核对 + 复现脚本重跑 + 论断数值验证），修正以下三处：

1. **P2-1 修复公式更正**：初版建议 `abs(value - nearest) <= 1e-9 * max(1.0, abs(value))` 有缺陷——按 `value` 比例给容差，在 price=60000、tick=1e-5 时容差（6e-5）宽于半个 tick（5e-6），会把非法价格放行。已更正为按 `step` 比例给容差（`step * 1e-4`），并用 10 组用例（含比值 1e12、半个 tick 偏离）验证通过。P2-1 问题本身的结论不变。
2. **P3-6 日期范围更正**：误判窗口为早于 1973-03-03（数值 < 1e11）；初版写的"1970-03 至 2001 年间"有误——2001 年的毫秒时间戳（≈1e12）实际会被正确判定。
3. **行号/措辞修正**：P3-2 定位 57-62 → 60-61；"亮点"中"深拷贝 feed 数据"更正为"逐行 `dict(row)` 浅拷贝（行值为标量时等价）"。

复核确认无误的项：P1-1（pytest 实跑复现）、P2-2、P2-3（运行时复现）、P3-1（`inspect.getsource` 确认 `payload` 仅出现在签名）、P3-3、P3-4（运行时确认 `with conn` 块外连接仍打开）、P3-5、P3-7、三条备忘（含 `_to_time("10")` 实测抛 `ValueError: not enough values to unpack`）。

## 建议后续

按仓库惯例将 P1-1 + P2-1/2/3 + P3 全部整理为 `docs/dev/PLAN-042-review-fixes.md` 并逐项修复；P2-3 需先决策语义（文档明示 vs 参数合并）再实施。
