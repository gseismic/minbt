# 全量源码 Review：第九轮（2026-10-13）

## 范围与结论

- 基线：`88f50a88423f5cc573e9bc2c58f923cc7be3d3c8`，审查当前工作区。
- 逐文件阅读当前 `minbt/`、`examples/` 的全部 **56 个 Python 文件、8,261 行**，包含协议、插件和随包 skill 脚本；同时检查 `pyproject.toml`、发布工作流及当前接口文档。
- 测试源码不在审查范围内；只运行已有测试作为基线验证。`docs/versions/v0/` 是历史归档，不作为当前版本运行源码评审。
- 对照上一轮报告与 PLAN-067 的实际修复，以下是本轮新发现，未把已经修复的 R8 问题重复列为现存问题。
- 本轮仅新增本报告，没有修改实现、测试或提交代码。原有 `examples/01_quickstart.py` 的打印修改保留原样。

确认 **9 项问题：1 项 P1、6 项 P2、2 项 P3**。主要剩余缺陷是：交易预检没有完整覆盖数值计算结果；普通全平仍使用逐笔现金约束；行情时间与交易时间在内部退出路径再次混用；不同读取路径的数据完整性与时间单位规则不一致。

现有 **487 项测试全部通过**，说明新增复现覆盖的是现有测试尚未发现的行为，不能据此判定这些边界正确。

| 编号 | 级别 | 问题 | 验证方式 |
| --- | --- | --- | --- |
| R9-01 | P1 | 声明支持 Python 3.8，但模块中的注解在该版本执行时报错 | 在真实 Python 3.8.20 下执行原源码类定义 |
| R9-02 | P2 | 有效全仓平仓计划被拒，结果取决于持仓插入顺序 | Broker 公共接口与完整 TimeBatch |
| R9-03 | P2 | 100% 目标权重因浮点尾差被当成资金不足 | Broker 公共接口 |
| R9-04 | P2 | 有限输入的中间结果溢出，异常前已经破坏真实账户 | Broker 公共接口 |
| R9-05 | P2 | 均线示例仍在开盘时间暴露该分钟最终 close | 示例真实 CSV 首行及同样的数据装配路径 |
| R9-06 | P2 | Binance CSV 文件存在分钟缺口仍无提示完成读取 | 临时月度 CSV 与 Feed.events() |
| R9-07 | P2 | 函数退出把旧报价时间改成当前 News 时间，影响其他分仓 | 两个分仓、Bar/News 的真实 Exchange 回放 |
| R9-08 | P3 | 撤单丢失当前时间，原订单 updated_dt 被写成 None | Broker 公共接口 |
| R9-09 | P3 | 已约定毫秒的存储时间仍按数量级推断，早期时间被放大 | 共用行解析及注入模拟 Database 的 IosqlBarFeed |

## R9-01 / P1：声明支持的 Python 3.8 无法执行模块定义

位置：[exchange.py:65](../../minbt/exchange.py#L65)、[bar_feed.py:57](../../minbt/plugins/storage/bar_feed.py#L57)、[pyproject.toml:10](../../pyproject.toml#L10)。

`pyproject.toml` 声明 `requires-python = ">=3.8"`。但是 Exchange 从 `collections.abc` 导入 `Iterable`，并直接求值 `Iterable[MarketEvent]`；通用存储读取器同样对 `collections.abc.Iterable/Iterator` 使用泛型下标。这些 ABC 在 Python 3.8 不支持该操作，文件也没有延迟注解求值。

已用真实 Python 3.8.20 执行从源码 AST 提取、未改写的 `_Cursor` 和 `_BarRowFeed` 类定义，两者均抛出：

```text
TypeError: 'ABCMeta' object is not subscriptable
```

顶层 `minbt` 会导入 Exchange，因此在满足依赖的 Python 3.8 环境中，模块定义本身就会阻止正常导入。这不是 AST 语法检查能发现的问题；本轮没有在 Python 3.8 安装全套项目依赖或运行全套测试。

建议：保留 3.8 支持时从 `typing` 导入用于注解的 `Iterable/Iterator`，或延迟注解求值并核对其他求值入口；否则应明确提高最低 Python 版本。发布验证应至少执行一次最低支持版本的实际导入。

## R9-02 / P2：全仓账户的有效全平目标仍依赖持仓顺序

位置：[broker.py:1399](../../minbt/broker/broker.py#L1399)、[portfolio.py:446](../../minbt/broker/portfolio.py#L446)、[portfolio.py:395](../../minbt/broker/portfolio.py#L395)。

上一轮修正了系统全仓强平的整体结算，但 `close_portfolio()` 的普通原子全平仍在预检副本上逐笔调用 `submit_order()`，要求每一笔交易的中间可用现金都非负。

复现：初始资金 1,000，杠杆 10，A、B 各以 100 买入 50 单位，占用全部现金。下一完整行情批次 A=89、B=94。此时 A 持仓权益=-50，B=200，全账户权益=150，保证金水平=0.15，大于强平线 0.1。按现有免手续费配置，全部平仓的最终现金应为 150。

| 建仓顺序 | close_portfolio('main') | 最终状态 |
| --- | --- | --- |
| A → B | rejected，`portfolio rejected atomic close plan` | 仍持有 A、B 各 50 |
| B → A | 两笔 filled | 零仓位、现金 150 |

两种账户具有相同资金、仓位和行情，只是字典顺序不同。第一种却无法实现数学上有效的全平目标。拒绝发生在副本预检阶段，因此本轮未观察到账本部分提交。

建议：原子全平需要先汇总全部平仓现金与手续费，验证最终账户状态后整体结算。不能把正常逐笔下单的现金前置条件直接当成整个账户全平计划的有效性条件。

## R9-03 / P2：零手续费的满仓目标被浮点尾差拒绝

位置：[portfolio.py:395](../../minbt/broker/portfolio.py#L395)、[struct.py:65](../../minbt/broker/struct.py#L65)。

保证金预检使用严格的 `should_remaining_cash < 0`，现金提交也使用严格的非负比较，没有处理正常浮点运算产生的尾差。

```python
from minbt import Broker

broker = Broker(1_000)  # 零手续费、默认市场、无交易单位限制。
order = broker.order_target_percent("A", 1, price=29)
print(order.qty, order.status, broker.get_cash())
# 34.48275862068966 rejected 1000.0
```

所需保证金 `order.qty * 29` 为 `1000.0000000000001`，比可用现金仅多 `1.1368683772161603e-13`。同样调用在价格 3、7、11、13、100 下成功。默认接口表达的 100% 目标因此会随价格出现偶发拒单。

建议：在预检与现金提交两处采用一致、与金额精度相关的尾差规则，对容差内的零余额统一归零。只放宽预检会使后面的 Cash.change_cash() 再次失败；容差也不能掩盖实际资金不足。

## R9-04 / P2：中间计算溢出绕过预检，异常留下损坏的账户

位置：[portfolio.py:390](../../minbt/broker/portfolio.py#L390)、[portfolio.py:405](../../minbt/broker/portfolio.py#L405)、[portfolio.py:414](../../minbt/broker/portfolio.py#L414)、[struct.py:174](../../minbt/broker/struct.py#L174)。

入口检查了输入有限性，但没有检查数量乘价格、手续费、成本、保证金、盈亏和候选现金的计算结果。有限输入也能产生 inf/NaN；而 NaN 与零比较时，`should_remaining_cash < 0` 为 False，错误计划被放行。

```python
from minbt import Broker

broker = Broker(1_000)
try:
    broker.submit_market_order("A", 1e308, price=100)
except ValueError as exc:
    print(exc)  # amount must be finite

print(broker.get_position_size("A"))  # 1e+308
print(broker.get_cash())              # 1000.0
print(broker.get_total_equity())       # nan
print(broker.get_orders()[0].status)   # pending
```

真实持仓已在 `change_cash()` 抛错前提交，现金没有扣除，成交账本没有完成，市价单停在 pending。`price=1e10, qty=1e300` 也得到相同类型的损坏。

触发条件是极大的有限数值，普通行情规模下未复现，因此定为 P2。问题在于失败原子性与中间值验证，不在于应允许这种数量成交。

建议：在副本预检中验证所有派生金额及候选持仓为有限值，确认现金提交可完成后再写真实状态；异常不能把真实持仓、现金和订单留在不同提交阶段。

## R9-05 / P2：均线示例遗漏了 Kline 可见时间修正

位置：[02_moving_average.py:61](../../examples/02_moving_average.py#L61)、[02_moving_average.py:68](../../examples/02_moving_average.py#L68)。

三个 Binance Feed 已改为以 close_time 发布完整 Kline，但均线示例仍读取最终 close，并用 `date_key="open_time"` 调度，忽略同一 CSV 中已有的 close_time。

使用示例实际 `data.csv` 第一行及相同 set_bars 路径，观察到：

```text
回调时间：2020-11-26 00:00:00 UTC
该行真实收盘时间：2020-11-26 00:00:59.999 UTC
```

该分钟最终 close 提前近一分钟可见。这与当前 README 对自备完整 K 线使用完成时间的约定相冲突；将示例模式用于混合分钟、News 或其他周期回放时会引入未来数据。单独运行该示例可能只是时间标签提前，不能据此声称已经测得其收益被放大。

建议：用 close_time 构造可见时间，保留 open_time 为载荷字段，或通过合适的 Kline reader 读取。随包最小 quickstart 的自备时间点样本不属于这个问题。

## R9-06 / P2：Binance CSV 完整性检查停留在月份和至少一行

位置：[csv.py:152](../../minbt/plugins/binance/csv.py#L152)、[csv.py:237](../../minbt/plugins/binance/csv.py#L237)。

这是读取器的设计缺口：已经有 interval 与明确请求窗口，并检查月份文件缺失，却没有检查月份文件内部的首尾覆盖和相邻 Kline 连续性。只要每个 symbol 有一行且时间递增，缺行的月文件就被接受。

已用临时 `A-1m-2026-01.csv` 复现：请求 `[00:00, 00:03)`，文件只含开盘时间 00:00 和 00:02 的两行。Feed 正常准备并产出两个事件，没有报告缺少 00:01；首端或末端截断但仍保留一行的文件也没有对应的覆盖校验。

相比下载缓存路径的首端、中间和末端检查，切换到 CSV 就失去了相同类别的数据缺失提示。缺少行情可能跳过本应处理的信号、限价或退出检查。iosql Kline 路径从静态代码看同样只检查请求标的有行；本轮没有动态验证其分钟缺口。

建议：Kline 专用读取器提供明确的完整区间校验，按 interval 检查首尾和连续性；上市边界或允许稀疏数据的需求应有显式规则。通用 Bar 可以天然稀疏，不应对所有通用 Feed 强加这项约束，也不应自动补造行情。

## R9-07 / P2：内部退出交易把旧报价伪装成新报价

位置：[broker.py:1567](../../minbt/broker/broker.py#L1567)、[broker.py:427](../../minbt/broker/broker.py#L427)、[broker.py:805](../../minbt/broker/broker.py#L805)。

`check_exit_rules()` 取出已有报价，再把它作为显式 price、以当前 dt 传入 close_position。显式报价入口会更新整个 Broker 的报价与所有分仓估值时间。内部沿用旧报价的交易因此产生了并不存在的新行情时间。

已运行完整回放：

1. 1 月 1 日只有 A=100 的行情，alpha、beta 分仓分别买入 A 各 1 单位。
2. alpha 注册一个在 1 月 2 日触发的函数退出。
3. 1 月 2 日只有一条无关联标的的 News，没有任何 A 行情。
4. alpha 正常平仓，但 beta 仍持有 A，其 Position._last_dt 与 Broker.get_last_price('A', return_dt=True) 都变成了 1 月 2 日。

实际报价时间应仍为 1 月 1 日；1 月 2 日是 alpha 的交易时间。此问题没有改变复现中 beta 的浮盈数值，但会误导依赖报价时间判断数据是否过期的策略，而且不同分仓之间会互相影响行情新鲜度。

建议：内部退出沿用已有报价时使用省略价格的交易入口，或明确分别传递报价时间与成交时间。不能通过重发旧值来推进报价时间。

## R9-08 / P3：撤单没有保留实际状态变化时间

位置：[broker.py:1036](../../minbt/broker/broker.py#L1036)、[broker.py:1027](../../minbt/broker/broker.py#L1027)。

`_cancel_pending_order()` 调用 `_update_order()` 时没有传 updated_dt，后者直接把该字段赋为 None。返回的撤单审计对象也从这个 None 取时间，并且未设置 created_dt。

复现：1 月 1 日挂单，1 月 2 日推进报价后 cancel_order。Broker 的当前时钟已为 1 月 2 日，但原订单 updated_dt、撤单对象 created_dt/updated_dt 均为 None。RunResult 也只会忠实保存这些缺失的值。关闭分仓取消挂单复用相同路径。

建议：取消状态和审计事件统一使用当前交易时钟；手工账户没有可用时钟时才保留 None。

## R9-09 / P3：明确的毫秒字段被当成自动推断单位的输入

位置：[bar_feed.py:90](../../minbt/plugins/storage/bar_feed.py#L90)、[bar_feed.py:45](../../minbt/plugins/storage/bar_feed.py#L45)、[bar_feed.py:190](../../minbt/plugins/storage/bar_feed.py#L190)。

通用 iosql Bar 表明确定义 dt 为 UTC 毫秒时间戳，共用行解析也接受名为 dt_ms 的字段，却统一交给按数量级推断单位的 normalize_datetime()。

已验证共用解析路径，并用模拟 Database 驱动真实 IosqlBarFeed.events()：存储 dt=1000 产出 `1970-01-01 00:16:40 UTC`，正确的毫秒时间应为 `1970-01-01 00:00:01 UTC`。dt_ms=60000 同样被解释为 16:40:00，而不是 00:01:00；现代大数量级时间戳通常不会触发这个问题。

建议：已约定单位的存储字段明确使用 unit='ms'；CSV 中允许自动推断的普通 dt 文本继续保留自己的规则，不能覆盖已知单位的语义。

## 验证与边界

- 现有环境：Python 3.12.8。`uv run --no-project python -m pytest -q --tb=short`：**487 passed in 43.31s**。没有阅读、修改或新增测试源码。
- Python 3.8.20 仅用于执行源码类定义并复现注解求值错误，未把 AST 语法成功当作运行兼容证据。
- 交易问题使用内联价格、公共 Broker 接口及完整批次；时间问题使用实际 Exchange 回放。
- CSV 使用临时目录；iosql 时间单位验证注入模拟 Database，不访问个人数据库。
- Binance 未发起真实行情请求；没有改动缓存、原始数据或线上服务。
- 最终检查原工作区修改保持原样。审查结论只覆盖本轮实际静态阅读和已描述的运行证据，不表示所有可能场景都已经验证。

## 建议修复顺序

先处理最低 Python 版本的导入失败；随后处理交易派生值预检、现金尾差和原子全平，避免错误账户或有效交易被拒。再统一内部退出的报价时间、Kline 示例与专用 reader 的完整性规则。撤单时间和已知毫秒单位可以作为独立小修复。
