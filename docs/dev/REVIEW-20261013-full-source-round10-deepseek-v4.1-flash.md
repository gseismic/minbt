# 全量源码 Review：第十轮（2026-10-13）

## 文档信息

- 创建时间：2026-10-13 02:58（Asia/Shanghai）。
- 模型：DeepSeek V4.1 Flash（provider `opencode-go`，模型 ID `deepseek-v4.1-flash`）。
- 基准提交：`88f50a88423f5cc573e9bc2c58f923cc7be3d3c8`。阅读开始时 HEAD 为 `17623c8ecee2c3301c666271896d0af1775fb21d`，审查期间该提交前移到 `88f50a8`（仅调整 `Portfolio.submit_order` 零数量检查的位置）；本报告全部结论已按 `88f50a8` 复验。
- 分析范围包含未提交/未跟踪内容（`WORKTREE`）：`examples/01_quickstart.py` 的 `print(dt, bars)` 调试语句，以及并行产生的未跟踪文件 `docs/dev/REVIEW-20261013-full-source-round9.md`。以上内容尚未固定为提交。
- 审查范围：`minbt/` 全部运行源码 38 个文件、6,769 行（含 `protocols`、`plugins`、`skills` 入口与随包脚本），`examples/` 全部 19 个脚本、1,492 行；共 57 个文件、8,261 行。测试源码按用户要求不在范围内；`docs/versions/v0/` 为历史归档，不作为当前运行代码评审。
- 方法：逐文件静态阅读；使用内联数据、公共 API 与真实 `TimeBatch`/完整 `Exchange` 回放做针对性复现；运行现有测试作为基线。没有请求外部行情、没有访问个人数据库、没有修改任何实现或测试。
- 与并行 round9 报告的关系：本报告独立完成；重叠项已逐条独立复现或按代码路径核验（见“与并行 round9 的关系”），另有 round9 未覆盖的补充发现。

## 总体判断

账本一致性和上一轮 R8 修复在抽查中成立：全仓强平聚合结算与持仓顺序无关、平仓不会反向开仓、限价成交不污染估值、随机交易下 `权益 − 初始资金 ≡ net_pnl`、穿仓恒等式成立。模块划分（Exchange 调度、Broker 交易、Portfolio 记账、Feed 读取、RunResult 快照）方向合理。

剩余缺陷集中在两类：**账户级现金约束被用于 reduce-only 操作**（平仓、减仓、止损、分仓全平被拒或静默失效），以及**预检与中间计算不完整**（浮点尾差、溢出、报价时间被内部交易污染、读取器完整性、结果查询口径不一致）。

| 级别 | 数量 | 含义 |
| --- | ---: | --- |
| P1 | 2 | 破坏交易意图/风控语义，或声明支持的环境无法导入 |
| P2 | 7 | 有效请求被拒、账户原子性受损、时间/数据语义错误 |
| P3 | 8 | 契约、校验、死代码与建模噪音 |

## R10-01 / P1：全仓账户的平仓、减仓与止损被自由现金约束拒绝

位置：[portfolio.py:395](../../minbt/broker/portfolio.py#L395)（`should_remaining_cash` 预检）、[portfolio.py:433](../../minbt/broker/portfolio.py#L433)（`can_submit_orders` 逐笔预检）、[broker.py:1542](../../minbt/broker/broker.py#L1542)（`check_exit_rules`）、[broker.py:1399](../../minbt/broker/broker.py#L1399)（`close_portfolio` 原子预检）。

**触发条件**：全仓（cross）账户现金全部占用后，某条持仓亏损超过其保证金（账户整体权益仍为正）。

**表现 1：普通平仓/减仓被拒。** 资金 200、杠杆 10，A、B 各买 10@100（保证金各 100）；A 跌 15%、B 涨 12% 后：

```python
from minbt import Broker

b = Broker(200, leverage=10, margin_mode='cross')
b.submit_market_order('A', 10, price=100)
b.submit_market_order('B', 10, price=100)
b.on_new_price('A', 85)
b.on_new_price('B', 112)
print(b.get_total_equity(), b.get_cash())      # 170.0 0.0
print(b.close_position('A').status)            # rejected
print(b.get_position_sizes())                  # {'A': 10.0, 'B': 10.0}
```

平仓释放 `保证金 100 + 已实现 −150 = −50`，`free_cash(0) + (−50) < 0` 即整单被拒。数学上平仓后账户权益不变（170），但库内 `Cash` 不允许自由现金为负；`order_target_size` 的部分减仓同样被拒。

**表现 2：附带止损静默失效（影响最大）。** 同一场景给 A 挂 `stop_loss_price=95`，完整回放下 A 跌到 85 后：

```text
final positions: {'A': 10.0, 'B': 10.0} equity: 170.0
order-3 A close_position rejected  'portfolio rejected order'
active exit handle: order-1 (仍为 filled，退出配置仍 active)
```

止损触发时 `close_position` 被拒，`check_exit_rules` 只保留 `state.active` 在后续批次重试；若价格此后不再满足条件，止损永久失效。另外 [logger.py:4](../../minbt/logger.py#L4) 用 `logger.disable("minbt")` 默认关闭库内日志，"Exit rejected" 警告默认不可见，用户只能从 rejected 订单记录察觉。这与 README 承诺的“订单级止损、止盈、追踪止损”保护相冲突。

**表现 3：`close_portfolio` 结果依赖持仓插入顺序。** 同一分仓（权益 170、自由现金 0）下：

```text
order=['A','B'] -> [('A','rejected','portfolio rejected atomic close plan')]
order=['B','A'] -> [('B','filled'), ('A','filled')]
```

逐笔预检让先平盈利腿所得现金去覆盖亏损腿，顺序一变结论相反。系统强平 [_pure_close_all_positions](../../minbt/broker/portfolio.py#L528) 已采用账户级聚合结算，普通平仓计划却没有。

**建议方向**：reduce-only（`close_position`、目标减仓、退出条件、`close_portfolio` 的整组计划）改为账户级结算——先汇总整组释放现金与手续费，再按账户权益校验（`_pure_close_all_positions` 的聚合方式可复用），或允许平仓结算令自由现金变负、由权益与穿仓边界兜底。同时让拒绝原因可区分：当前一律 `portfolio rejected order`，无法区分“平仓资金约束”。

**与 round9 的关系**：与 R9-02 同根因；本报告补充了更常用的单笔平仓与订单止损两个入口。

## R10-02 / P1：声明支持的 Python 3.8 无法导入模块

位置：[exchange.py:65](../../minbt/exchange.py#L65)（`Iterable[MarketEvent]`）、[bar_feed.py:57](../../minbt/plugins/storage/bar_feed.py#L57)、[bar_feed.py:157](../../minbt/plugins/storage/bar_feed.py#L157)、[bar_feed.py:278](../../minbt/plugins/storage/bar_feed.py#L278)（`Iterable[Bar]`、`Iterator[dict]`），以及 [pyproject.toml:10](../../pyproject.toml#L10) 的 `requires-python = ">=3.8"`。

这些注解使用 `collections.abc` 的泛型下标；Python 3.8 的 `collections.abc.Iterable/Iterator` 不支持 `[]`，且相关文件没有 `from __future__ import annotations`。函数注解在定义时求值，会产生 `TypeError: 'ABCMeta' object is not subscriptable`；`minbt/__init__.py` 顶层导入 Exchange，因此 **Python 3.8 下模块定义即失败，无法 `import minbt`**。

本机没有 Python 3.8 可执行文件，未直接运行；该结论由注解求值规则确定，并行 round9 报告在真实 Python 3.8.20 下复现了同样的错误。**建议**：把注解改用 `typing` 的对应泛型或延迟注解求值，或将 `requires-python` 提高到 `>=3.9` 并同步 README/发布说明；发布验证至少执行一次最低支持版本的实际导入。

## R10-03 / P2：浮点尾差把有效满仓目标判为资金不足

位置：[portfolio.py:395](../../minbt/broker/portfolio.py#L395)（严格 `< 0`）、[struct.py:51](../../minbt/broker/struct.py#L51)（严格非负比较）。

```python
from minbt import Broker

broker = Broker(1_000)
order = broker.order_target_percent("A", 1, price=29)
print(order.qty, order.status, broker.get_cash())
# 34.48275862068966 rejected 1000.0
```

所需保证金 `1000.0000000000001`，仅超出可用 `1.1368683772161603e-13`；同一调用在价格 3、7、11、13、100 下成功。默认接口表达的 100% 目标因此会随价格偶发拒单。**建议**：预检与现金提交采用一致的金额精度容差，对容差内的零余额统一归零；容差不能掩盖实际资金不足。

（与 round9 R9-03 重叠，已独立复现。）

## R10-04 / P2：中间计算溢出绕过预检，异常留下损坏的账户

位置：[portfolio.py:390-424](../../minbt/broker/portfolio.py#L390)（副本预检与提交）、[struct.py:176](../../minbt/broker/struct.py#L176)（保证金计算）。

```python
from minbt import Broker

broker = Broker(1_000)
try:
    broker.submit_market_order("A", 1e308, price=100)
except ValueError as exc:
    print(exc)                            # amount must be finite
print(broker.get_position_size("A"))      # 1e+308
print(broker.get_cash())                  # 1000.0
print(broker.get_total_equity())          # nan
print(broker.get_orders()[0].status)      # pending
```

真实持仓已在 `change_cash()` 抛错前写入，现金未扣、订单停在 pending、权益 NaN。入口只校验输入有限，未校验派生金额（数量×价格、手续费、保证金、盈亏、候选现金）是否有限。**建议**：副本预检覆盖全部派生金额与候选持仓；确认现金提交可完成后再写真实状态，异常不得把持仓、现金和订单留在不同提交阶段。

（与 round9 R9-04 重叠，已独立复现。）

## R10-05 / P2：内部退出沿用旧报价却推进全局报价时间

位置：[broker.py:1567](../../minbt/broker/broker.py#L1567)（`check_exit_rules` 以显式 price 调用 `close_position`）、[broker.py:802-808](../../minbt/broker/broker.py#L802)（`_apply_price` 写 `last_price_dates`）。

`check_exit_rules` 取出已有报价，再把它作为显式 `price`、以当前批次 `dt` 传入 `close_position`；显式报价入口会经 `_prepare_market_price` → `_apply_price` 把该 symbol 的 `last_price_dates` 写成当前批次时间。于是“沿用旧报价的内部平仓”制造了一个并不存在的行情时间，且影响同一 Broker 下所有分仓的行情新鲜度判断。**建议**：内部退出改走省略价格的交易入口，或明确分开传递“报价时间”与“成交时间”，不能通过重发旧值推进报价时间。

（与 round9 R9-07 重叠，已按代码路径核验。）

## R10-06 / P2：挂单不预占资金，提交预检未计入其他挂单

位置：[broker.py:981-1009](../../minbt/broker/broker.py#L981)（提交预检）、[broker.py:1046-1096](../../minbt/broker/broker.py#L1046)（批量撮合）。

资金 100 下两张各需 80 的限价单都能通过提交预检；下一批次撮合时第一张成交、第二张 `rejected 'portfolio rejected order'`：

```text
after batch: filled None | rejected portfolio rejected order
positions: {'A': 0.8} cash: 20.0
```

预检逐笔模拟当前账户状态，不累计其他 pending 单，因此“提交预检通过”不代表能成交。若这是有意模拟交易所余额校验，应在文档中明确；否则需要预占资金或在提交时累计预检。

## R10-07 / P2：Binance CSV/iosql 的 Kline 完整性检查停留在“月份齐全 + 每标的至少一行”

位置：[csv.py:152-207](../../minbt/plugins/binance/csv.py#L152)（`_validate_matching_rows`/`_validate_month_files`）、[csv.py:223-264](../../minbt/plugins/binance/csv.py#L223)；[iosql.py:92-111](../../minbt/plugins/binance/iosql.py#L92)。

带 interval 与明确请求窗口的专用读取器没有检查月内首尾覆盖和相邻 Kline 连续性：只要每 symbol 有一行且按 open_time 递增，缺行的月文件就被接受。对比 [cache.py:348-411](../../minbt/plugins/binance/cache.py#L348) 的下载路径有首端/中间/末端连续性校验，切换读取器就失去同类数据缺失保证。缺少行情会跳过本应触发的信号、限价或退出检查。**建议**：Kline 专用 reader 统一提供明确区间的首尾与连续性校验；上市边界或允许稀疏的数据需求应有显式规则，通用 Bar 可保持天然稀疏。

（与 round9 R9-06 重叠，已按代码路径核验。）

## R10-08 / P2：均线示例用开盘时间调度最终 close

位置：[02_moving_average.py:61-68](../../examples/02_moving_average.py#L61)。

三个 Binance 读取器已改为以 `close_time` 发布完整 Kline，但示例仍读取该分钟最终 `close` 并用 `date_key="open_time"` 作为事件时间，相当于在开盘时刻暴露整根 Kline。单独运行该示例只是时间标签提前；若把这种模式用于分钟、News 或其他周期混合回放会引入未来数据，与当前 README 的可见时间约定冲突。**建议**：用 `close_time` 构造可见时间（保留 `open_time` 为载荷字段），或直接使用 Kline reader。

（与 round9 R9-05 重叠，已按代码路径核验。）

## R10-09 / P2：已关闭分仓的结果查询口径不一致

位置：[result.py:132-139](../../minbt/result.py#L132)（`RunResult.get_position_sizes`）、[exchange.py:341-357](../../minbt/exchange.py#L341)（快照只含活动分仓）、[broker.py:1677-1692](../../minbt/broker/broker.py#L1677)（`get_pnl` 支持归档分仓）。

```text
position_sizes(sub) -> ValueError portfolio not found: sub
pnl sub (archived): 0.0
```

`Broker.get_pnl(portfolio=closed)` 与 `get_pnl_records(portfolio=closed)` 支持已关闭分仓，但 `RunResult.get_position_sizes(portfolio=closed)` 直接报“不存在”。分仓归档语义应在结果查询层保持一致（保留最终持仓或统一报 NotImplementedError）。**建议**：明确已关闭分仓在结果快照中的查询契约，并补充对应测试。

## P3：契约、校验与死代码

| 编号 | 问题 | 位置与证据 |
| --- | --- | --- |
| R10-10 | `cancel_order` 返回新的标记订单（新 id、qty=0、`created_dt/updated_dt` 为 None），且被 `get_orders()` 过滤隐藏；原订单已就地改为 canceled，返回值与传入 id 不一致 | [broker.py:1011-1036](../../minbt/broker/broker.py#L1011)、[broker.py:1648](../../minbt/broker/broker.py#L1648)；已复现。时间部分与 R9-08 重叠 |
| R10-11 | `Portfolio.close_position`/`close_all_positions` 以 `dt=None` 调 `on_new_price`，把 `last_prices_dt[symbol]` 覆盖为 None，与“报价时间独立保存”规则不一致 | [portfolio.py:464-499](../../minbt/broker/portfolio.py#L464)；已复现：关闭前 `{A: 2026-01-01}`、关闭后 `{A: None}` |
| R10-12 | `add_portfolio` 不校验 name：`add_portfolio(123, 100)` 通过，公开查询键变成非字符串 | [broker.py:600-612](../../minbt/broker/broker.py#L600)；已复现 |
| R10-13 | `Portfolio` 的 `locked_cash` 恒为 0，`get_cash(include_locked=True)` 与 False 等价；接口暗示的锁定现金从未实现 | [portfolio.py:578-589](../../minbt/broker/portfolio.py#L578)、[struct.py:74-96](../../minbt/broker/struct.py#L74) |
| R10-14 | `replayable` 能力被声明、校验、读入 `_Cursor` 后从未使用；`_Cursor.supports_preload/supports_incremental` 同样未使用 | [exchange.py:54-57](../../minbt/exchange.py#L54)、[replay.py:19](../../minbt/data/replay.py#L19) |
| R10-15 | `get_orders`/`get_order` 返回内部可变 `Order` 活对象，外部可直接改 `status/qty` 破坏账本；`RunResult` 已有冻结快照 | [broker.py:1630-1649](../../minbt/broker/broker.py#L1630)、[order.py](../../minbt/broker/order.py) |
| R10-16 | A 股整手规则只对买入（qty>0）做归一化，卖出非整手在 `validate_order` 直接 rejected，无法模拟零股卖出 | [market.py:170-190](../../minbt/broker/market.py#L170)、[market.py:208-209](../../minbt/broker/market.py#L208) |
| R10-17 | `Position._last_dt` 只写不读（死字段）；`Cash.spend_cash`、`Order.is_done` 仅供外部使用 | [struct.py:113/136](../../minbt/broker/struct.py#L113) |

另有工作区观察（未修改）：`examples/01_quickstart.py` 留有未提交的 `print(dt, bars)` 调试语句；随包 skill 脚本版本没有该语句。

## 与并行 round9 的关系

本报告与 `REVIEW-20261013-full-source-round9.md`（并行产生、同一基准）独立完成。重叠项的核验情况：

| round9 | 本报告 | 核验方式 |
| --- | --- | --- |
| R9-01 Python 3.8 | R10-02 | 注解求值规则确认；本机无 3.8，round9 在 3.8.20 实测 |
| R9-02 close_portfolio 顺序依赖 | R10-01（表现 3） | 已独立复现，并补充单笔平仓/止损入口 |
| R9-03 浮点尾差 | R10-03 | 已独立复现（price=29） |
| R9-04 中间值溢出 | R10-04 | 已独立复现（qty=1e308） |
| R9-05 均线示例可见时间 | R10-08 | 代码路径核验 |
| R9-06 CSV 缺行 | R10-07 | 代码路径核验 |
| R9-07 退出推进报价时间 | R10-05 | 代码路径核验 |
| R9-08 撤单时间缺失 | R10-10 | 已复现，并补充返回值/隐藏记录问题 |
| R9-09 dt_ms 单位推断 | 未列入 | 接受 round9 结论；与 R10-15 相邻主题但结论独立 |

round9 未覆盖、本报告补充的发现：R10-01 的单笔平仓与止损表现、R10-06、R10-09、R10-11、R10-12、R10-13、R10-14、R10-15、R10-16、R10-17。

## 修复抽查与基线验证

- 现有测试基线：Python 3.12.8 下 `pytest -q` **487 passed in 44.39s**。
- R8-01：初始 1,000、杠杆 10，A/B 各 50@100，A→89、B→92。两种建仓顺序均得到现金/权益 50、净盈亏 −950、零持仓。
- R8-02：1,000→100→price=5 场景下 `close_position` 与目标归零均返回 `skipped`、零持仓，无反向开仓。
- R8-03：限价 95 在市价 80 成交，成交均价 95、Position 最新价 80、权益 985、净盈亏 −15。
- 随机一致性：120 批次随机下单（含手续费、部分平仓、退出配置）后 `equity − initial_cash − net_pnl ≈ 5.8e-13`；`get_total_pnl()` 与持仓/明细口径一致。
- 穿仓恒等式：全仓与逐仓穿仓后 `equity − initial_cash = net_pnl` 精确成立。

## 覆盖与边界

- 未执行：真实 Binance 网络请求、真实 iosql 数据、pyta2 分支、绘图脚本、打包发布流程、Python 3.8 实机运行。
- 测试源码未阅读（用户要求）；所有复现使用公共 API 与内联数据，未触碰用户数据库与线上服务。
- 本报告结论只覆盖实际静态阅读与上述运行证据；不表示所有可能场景都已验证。

## 建议处理顺序

1. **R10-01**：reduce-only 的账户级结算（同时修复单笔平仓、止损静默失效、`close_portfolio` 顺序依赖），对回测可信度与风控语义影响最大。
2. **R10-02**：Python 版本声明与实现对齐。
3. **R10-03/04**：预检的浮点尾差与派生值/原子性（有效交易被拒与账户损坏两类）。
4. **R10-05/07/08**：内部退出报价时间、Kline 读取器与示例的可见时间/完整性一致性。
5. **R10-06/09 与 P3 清理**：挂单资金语义、关闭分仓查询口径、撤单契约与死代码。

实施时建议为每个已复现问题补充能断言预期行为的回归用例；本报告没有修改实现或测试。
