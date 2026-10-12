# 全量源码 Review（2026-10-13）

## 范围与方法

- 基线：`ba30b0636ea57d83c2b1caacf5cf55801ef4ef02`，以当前工作区内容为准。
- 逐文件阅读当前 `minbt/`、`examples/` 的全部 56 个 Python 文件，共 8,077 行，包含随包 skill 的最小脚本；同时检查 `pyproject.toml` 和发布工作流。
- 测试源码不在审查范围内，没有运行 pytest 或新增测试。`docs/versions/v0/` 是历史归档，不计入当前运行代码的评审范围。
- 方法：静态阅读、对照当前 README/协议契约，并在现有 Python 环境运行小型复现脚本。数据均为内联数据、临时文件或模拟下载响应，没有请求外部行情或使用个人数据库。
- 参考用户指定的 `api-design-zh`，分别评估策略调用者的公共 API 和模块之间的状态、错误、资源契约。
- 工作区原有 `examples/01_quickstart.py` 修改保持原样。本轮只新增本报告，没有修改实现或提交代码。

## 总体判断

模块划分方向合理：Exchange 调度、Broker 交易、Portfolio/Position 记账、Feed 读取、RunResult 保存快照。单一回放循环、完整时间批次、可注入 Feed、独立结果快照和不可变 Pnl 都值得保留。

主要问题集中在状态变化的先后顺序和边界：报价更新会隐式强平，成交又会覆盖估值，交易时间取自旧报价，退出配置挂在多个订单状态上。若干模块单独看似成立，组合后会产生错误结果。当前应先修复这些问题，再整理内部职责。

| 级别 | 数量 | 含义 |
| --- | ---: | --- |
| P1 | 6 | 优先修复，会破坏账本、交易意图、交易约束或行情可见时间 |
| P2 | 6 | 会造成条件丢失、数据污染、数据缺失、资源或性能问题 |
| P3 | 2 | 遗留模块和较少遇到的时间精度边界 |

下文区分已经复现的行为与建议采用的修复方式；建议本身不代表已经实施。

## R8-01 / P1：全仓强平依赖持仓顺序，并可能留下不一致的账本

位置：[portfolio.py:472](../../minbt/broker/portfolio.py#L472)、[portfolio.py:490](../../minbt/broker/portfolio.py#L490)。

全仓账户允许单个持仓权益为负，只要整个账户仍有正权益。当前强平逐仓调用 `_pure_close_position()`，要求每次释放现金后都非负；更严重的是，在做这个检查之前，`position.commit_close_all()` 已经清空了持仓。

复现：初始资金 1,000，杠杆 10，先后以 100 买入 A、B 各 50 单位，占满保证金。同一批次 A 跌到 89，B 跌到 92。此时 A 的权益为 -50，B 为 100，全账户权益为 50，应完成全仓强平并保留现金 50。

| 建仓顺序 | 实际结果 |
| --- | --- |
| A → B | 抛 `RuntimeError: Cannot close position A...`；A 已被清空，B 仍持有 50；权益变成 100，累计净盈亏却为 -400 |
| B → A | 正常全部平仓；现金/权益 50，净盈亏 -950 |

应把全仓风险结算作为一次账户操作，先计算全部现金和盈亏变化，再统一提交。单仓结算失败也不能先清空持仓再抛错。

## R8-02 / P1：平仓或目标归零可以反向开仓

位置：[broker.py:1213](../../minbt/broker/broker.py#L1213)、[broker.py:1080](../../minbt/broker/broker.py#L1080)、[broker.py:390](../../minbt/broker/broker.py#L390)。

`close_position()` 和 `order_target_size()` 先按旧仓位计算数量，随后 `_resolve_market_price()` 通过显式价格触发估值与强平。如果原仓位被清掉，之前计算出的减仓数量仍会执行，变成新开反向仓位。

已运行的最小复现：

```python
from minbt import Broker

broker = Broker(100)
broker.submit_market_order("A", 1, price=100)
order = broker.close_position("A", price=5)
print(order.status, broker.get_position_sizes())
# filled {'A': -1}
```

换成 `order_target_size("A", 0, price=5)` 得到相同结果。记账明细依次为买入 1、强平卖出 1、普通卖出 1。用户表达“清仓”，最终却持有空头。

应先完成必要的价格/风险推进，再根据最新仓位计算目标差额；全平入口还应保证不会增加反向敞口。

## R8-03 / P1：限价成交覆盖持仓估值，漏记当前浮亏

位置：[broker.py:1027](../../minbt/broker/broker.py#L1027)、[portfolio.py:359](../../minbt/broker/portfolio.py#L359)、[struct.py:164](../../minbt/broker/struct.py#L164)。

市场批次先按行情更新估值，随后限价成交把 `limit_price` 传给 `Portfolio.submit_order()`。后者再次用成交价更新行情和持仓，成交结束后没有恢复当前市场估值。Broker 的最新价与 Portfolio/Position 的最新价因此分叉。

复现：资金 1,000，最新价 100，挂买入 1 单位、限价 95；下一批行情为 80。

| 查询 | 实际值 | 按当前行情应有值 |
| --- | ---: | ---: |
| 成交均价 | 95 | 95，符合现有成交规则 |
| Broker 最新价 | 80 | 80 |
| Position 最新价 | 95 | 80 |
| 总权益 | 1,000 | 985 |
| 净盈亏 | 0 | -15 |

回测在该批结束时，错误会直接进入结果快照；继续运行时，下一次重估才补上损益。限价成交后的风险检查同样会滞后。

应让成交价格只决定成本、已实现盈亏和手续费，成交后的持仓继续按本批选定价格估值。这里不要求改变“限价成交不改善价格”的已文档化规则。

## R8-04 / P1：旧报价时间被当成成交时间，绕过休市和 T+1

位置：[broker.py:378](../../minbt/broker/broker.py#L378)、[broker.py:515](../../minbt/broker/broker.py#L515)、[market.py:245](../../minbt/broker/market.py#L245)。

不传 `price` 时，下单从 `get_last_price(..., return_dt=True)` 同时取出报价与报价时间，再把这个旧时间用于 `Market.validate_order()`、成交记录和 T+1 锁仓。多市场回放中，Exchange 已推进到较晚时间，某个标的仍沿用旧报价是正常可配置的情况，但旧报价时间不能代表现在的交易时间。

已复现两种结果：

1. A 使用 `markets.A_STOCK`，最后报价为周五 `2026-01-09`。周六 `2026-01-10` 仅有 BTC 行情；策略此时买 A，订单 `filled`，成交时间写成周五。相同 Market 对当前周六时间的 `is_trading_time()` 返回 False。
2. A 最后报价为周一。周二 09:30 上海时间在 BTC 回调中买 A，新仓按周一锁定；周二 09:31 的下一批解锁该仓，随后当天平仓成功，绕过 T+1。

应分别保存回放时间与报价时间，按当前交易时间执行市场规则和锁仓。若允许旧价成交，应明确其策略；若不允许，应拒绝旧价，而不是通过回退成交时间获得合法性。

## R8-05 / P1：内置 Kline Feed 在开盘时刻发布完整区间数据

位置：[kline.py:98](../../minbt/plugins/binance/kline.py#L98)、[cache.py:187](../../minbt/plugins/binance/cache.py#L187)。CSV/iosql 路径分别把 `open_time` 写入 `dt_ms`，复用相同转换。

这是数据可见时间的设计缺陷。Feed 以 `open_time` 作为事件 `dt`，但载荷包含该根 K 线最终的 close/high/low/volume。对于单一周期，这可能被当成一种时间标签约定；与分钟数据、其他周期或 News 合并后，这个标签会直接参与实际调度，提前暴露未来信息。

复现输入为一根 `00:00–00:59:59.999` 的小时 K 线，最终 close=200。实际产出的 Bar 为：

```text
event.dt = 2026-01-01 00:00:00+00:00
data.close_time = 2026-01-01 00:59:59.999+00:00
data.close = 200.0
```

所以策略在 00:00 就能读取整小时最终结果，并在 00:01 的分钟行情中使用它。`closed_only=True` 检查的是下载时是否已经收盘，不能修复历史回放中的提前可见。

应在读取器中明确 Kline 的可见时间，保留 `open_time` 为数据字段，用完成时间调度完整 Kline；若需保留开盘标签模式，应显式说明并限制其混合回放语义。此责任属于具体读取器，无需让 Exchange 猜测所有自定义 Bar 的含义。当前数据协议也要求 reader 保证真实可见时间。

## R8-06 / P1：非法数值在拒单之前已修改账户

位置：[broker.py:386](../../minbt/broker/broker.py#L386)、[broker.py:752](../../minbt/broker/broker.py#L752)、[broker.py:333](../../minbt/broker/broker.py#L333)。

显式价格只检查正数，没有先检查有限性。`inf` 会先写入最新价并触发风险结算，之后 `Market.validate_order()` 才拒绝。拒单不再是未成交的请求，而是已经改变了账户。

已运行的复现：

```python
from minbt import Broker

broker = Broker(1_000)
broker.submit_market_order("A", -1, price=100)
order = broker.submit_market_order("A", 1, price=float("inf"))
# order.status == 'rejected', reason == 'price must be finite'
# 原空头已清空，总权益由 1,000 变成 0，last_prices['A'] 为 inf。
```

同类入口校验缺口还包括止损/止盈绝对价格和追踪金额接受 NaN。`stop_loss_price=float("nan")` 可以随开仓成功注册，价格从 100 跌到 80 后仍保持活动状态，但永远不会触发。初始资金和杠杆也没有完整的有限性约束。

应在任何行情、资金、持仓副作用之前统一校验有限性、范围和类型，再进入业务拒单与记账流程；不同入口应使用相同规则。

## R8-07 / P2：退出配置只在部分入口继承，增加条件会移除已有保护

位置：[broker.py:440](../../minbt/broker/broker.py#L440)、[broker.py:1380](../../minbt/broker/broker.py#L1380)、[broker.py:412](../../minbt/broker/broker.py#L412)。

新成交附带标准退出参数时，仅复制旧状态的五个标准字段，没有复制函数规则及其 state。`set_exit()` 切换到同一持仓的另一张有效订单时，甚至不执行标准字段继承。两条路径最终都会把旧状态停用。

已复现：

- 买入 1 单位，在第一张订单上注册恒为 True 的函数退出；再加仓 1 单位并附带止损 90。新活动配置的 `custom_rules` 变为空，执行退出检查后仍持仓 2。
- 第一张订单带止损 90，第二张同方向订单不带退出参数；调用 `set_exit(第二张订单.id, take_profit_price=120)` 后，原止损停用，价格降到 85 仍持仓 2。

这与“在同一净持仓生命周期内按字段修改，显式 clear 才清除”的使用模型不一致。应统一退出配置的归属和合并规则：同一持仓只有一份有效配置，订单 ID 可作为访问句柄；标准条件、函数规则和函数状态都应有明确的保留或替换语义。

## R8-08 / P2：多个策略共享可变的回调容器

位置：[exchange.py:689](../../minbt/exchange.py#L689)、[exchange.py:698](../../minbt/exchange.py#L698)。

Bar 的常见载荷容器虽然已冻结，投影出的 `on_bars`/`on_books` 外层 OrderedDict，以及 `on_trades` 的外层字典和每个 symbol 的列表仍可变。`_dispatch_batch()` 将同一个容器依次传给全部策略。

复现：第一个策略在 `on_bars()` 中执行 `bars.pop("A")`，第二个策略收到空字典。策略各用独立 Broker 也不能避免这个问题；过滤、删除或替换行情的本地处理会影响其他策略。

应给回调提供只读映射，Trade 序列也应只读；或者为每个策略复制投影容器。已有冻结的行载荷可以共享，不需要对全部数据做深拷贝。

## R8-09 / P2：symbol 在数据、交易和市场路由中采用不同的身份规则

位置：[model.py:103](../../minbt/data/model.py#L103)、[broker.py:588](../../minbt/broker/broker.py#L588)、[broker.py:378](../../minbt/broker/broker.py#L378)。

Bar/Feed 会对 symbol 去空白并转大写，Broker 下单、查询和 `add_market()` 则原样保存。使用相同原始字符串装配数据和路由，最终也可能不是同一个标的。

已复现：

1. 输入数据 symbol 为 `abc`，行情从 100 涨到 120；策略执行 `order_target_size("abc", 1, price=bars["ABC"]["close"])`。实际持仓键为 `abc`，行情键为 `ABC`；第二次目标不变直接跳过，持仓价格留在 100，权益曲线为 `[1000, 1000]`，应有的 20 浮盈没有记录。
2. `add_market("stock", markets.A_STOCK, symbols=["abc"])`，随后按回调键 `ABC` 卖空 1 单位。订单使用 Default 市场并成交，预期配置的禁止做空、100 股交易单位等约束全部未应用。

应在公共入口统一标的身份规则，或统一保留原始标识并显式拒绝不一致。不能只在数据侧静默归一化。

## R8-10 / P2：常用目标仓位策略存在历史订单二次扫描

位置：[broker.py:184](../../minbt/broker/broker.py#L184)、[broker.py:214](../../minbt/broker/broker.py#L214)、[broker.py:1082](../../minbt/broker/broker.py#L1082)。

每个新时间点都会调用 `_default_market_symbols()`，进而遍历所有历史订单。即使默认市场为 T+0、不需要解锁，函数参数也已提前计算。与此同时，每根行情调用 `order_target_size()`、即使仓位未变，仍会保存一张 skipped 订单。

用与入门示例相同的“每根行情保持 1 单位”策略，对扫描量计数：

| 行情数 | 历史订单数 | 累计访问历史订单数 |
| ---: | ---: | ---: |
| 200 | 200 | 19,900 |
| 400 | 400 | 79,800 |

因此这一普通用法的该部分开销为 O(N²)。10 万个时间点约对应 50 亿次历史订单访问；这是由循环推导的数量，并非已运行 10 万次的性能测量。现有空策略基准没有 Broker，也不创建订单，无法代表该场景。

应从当前持仓、报价和待成交订单维护必要的标的集合，避免在每批中重扫完整历史；T+0 也不需要为解锁构造这份集合。是否保留 skipped 订单可独立决定，不必以删除审计记录来修复扫描问题。

## R8-11 / P2：Binance 首段缺失仍会登记成完整缓存

位置：[cache.py:389](../../minbt/plugins/binance/cache.py#L389)、[cache.py:403](../../minbt/plugins/binance/cache.py#L403)、[cache.py:538](../../minbt/plugins/binance/cache.py#L538)。

下载与缓存读取检查了相邻行连续性、末尾完整性和空结果，没有验证请求区间的首部。只要返回连续的尾部，整个 `[start, end)` 都会写入 coverage，后续也不会补取缺失首段。

模拟一次被截断的响应：请求 `00:00–00:03` 的 1m 数据，只返回 00:02 一根。`prepare()` 成功，`_missing_ranges()` 返回空列表；随后相同区间的 `cache_only=True` 也成功，只有 1 行。

应区分“请求过的范围”和“确认完整的范围”，验证首端或仅记录可证明的覆盖。如果要允许上市前无数据，需要明确的上市边界或缺失状态；不能把无法区分的响应前缀缺失直接判为完整。

## R8-12 / P2：SQLite 连接依赖垃圾回收，Feed.close 不释放它们

位置：[cache.py:229](../../minbt/plugins/binance/cache.py#L229)、[cache.py:303](../../minbt/plugins/binance/cache.py#L303)、[cache.py:205](../../minbt/plugins/binance/cache.py#L205)。

缓存方法反复使用 `with self._connect() as conn:`。sqlite3 Connection 的上下文退出处理事务，不等于调用 `close()`。Feed 的 `close()` 又是空操作，连接只能等待对象回收。

为把这种依赖显式展示出来，复现进程暂时关闭自动 GC：建表后执行 30 次 coverage 查询，文件描述符由 4 增至 35；调用 `feed.close()` 后仍为 35；恢复并执行 GC 后回到 4。这不表示正常 GC 下永远不会回收，而是正常返回和退出时没有确定性释放。

应在事务上下文外使用 `contextlib.closing()`，或实现负责关闭的连接上下文；异常路径同样释放连接。多标的和反复准备缓存时尤其需要避免积累数据库资源。

## R8-13 / P3：包内残留一个无法导入的旧数据模块

位置：[data/bars.py:7](../../minbt/data/bars.py#L7)。

`minbt.data.bars` 仍从 `.bar_feed` 导入 `CsvBarFeed/IosqlBarFeed`，但该模块已经迁移至 `minbt.plugins.storage`。实际运行 `import minbt.data.bars` 抛出 `ModuleNotFoundError: No module named 'minbt.data.bar_feed'`。

新文档已使用正确插件入口，所以当前主流程不受影响。不过旧文件仍随包分发，与“删除旧转发入口”的设计不一致。按当前明确不保留兼容层的方向，建议删除残留模块，而不是再添加转发别名。

## R8-14 / P3：浮点时间键会把相邻毫秒合并

位置：[model.py:67](../../minbt/data/model.py#L67)。`kline.datetime_to_ms()` 和缓存内部转换也使用类似计算。

`int(datetime.timestamp() * 1000)` 经过浮点再截断，不能保证得到原本的整数毫秒。

已复现 `2039-01-01T00:00:00.002Z` 应为 `2177452800002`，实际键为 `2177452800001`。它与前一毫秒冲突：同一 symbol 会误报重复；不同 symbol 被归入同一批，随后 `TimeBatch` 因原始 datetime 不同而报错。

这个日期较远，故列为 P3；问题本身来自整数时间键的实现。建议统一使用 UTC epoch 差值的整数天/秒/微秒运算，并让各 Feed 复用同一个转换函数。

## API 设计评估

以下频率是根据库目标和当前示例作出的设计判断，没有用户使用统计支撑。

| 代表场景 | 预计频率 | 当前接口评价 |
| --- | --- | --- |
| 内存行情、单标的买入持有 | 高 | `set_bars`、`on_bars`、`order_target_size` 路径短，默认配置合理 |
| 动量轮动、按权益比例调仓 | 高 | 三种目标接口表达业务意图清楚；R8-02/R8-10 表明最常用路径仍有状态和性能问题 |
| 限价下单、查看结果、撤单 | 高 | Order 状态统一；成交成本与持仓估值应分别处理，见 R8-03 |
| 给持仓设置和修改退出条件 | 高 | 用户关注的是净持仓的保护条件；当前按 order ID 保存多个配置，增加了维护难度并产生 R8-07 |
| 读取权益、持仓和盈亏 | 高 | `Pnl`、`PnlRecord`、`RunResult` 快照边界较好；权益覆盖全账户而持仓曲线仅 main，使用时仍需记住口径差异 |
| 自定义行情或按需读取 | 中 | `name + events()` 易于实现；可见时间、symbol 和缺数据契约应由各读取器一致落实 |
| 多市场、多分仓、多个策略 | 中 | 路由和共享账户具有可用基础；时间、标识和回调隔离问题需优先修复 |
| 自定义 Broker 或外部引擎 | 较低 | 工厂注入和标准结果避免全局注册；Protocol 的类型及能力边界仍可完善 |

公共 API 的主要改进方向：

- **把退出条件的修改对象与用户意图对齐。** 净持仓只有一套有效退出状态，就应有统一的合并、清除和生命周期规则。保留订单句柄也应保证不同修改入口等价。
- **提供明确的错误类别。** `status="rejected"` 是可程序判断的，但资金不足、交易时段、交易单位、仓位锁定等原因目前只有人读字符串；需要自动恢复的策略无法稳定分类。可增加稳定的拒绝原因枚举，同时保留说明文本。
- **统一结果的分仓口径。** README 已说明持仓曲线只记录 main，所以这不是未文档化的实现错误；但多分仓用户无法从 RunResult 查询其他分仓的历史持仓。后续可按实际需求增加 `portfolio=`，保持默认用法简短。
- **明确读取器的缺数据策略。** 已复现通用 `CsvBarFeed(symbols=["A", "MISSING"])` 只有 A 时仍返回 completed；通用 IosqlBarFeed 也只预检总体是否有行，而 Binance CSV/iosql 会检查每个请求标的。若 `symbols` 只是筛选条件，允许部分命中可以成立；若表示实验所需标的，就应明确失败。当前应统一说明这两种语义，避免用户靠更换读取器获得不同的数据完整性保证。
- **把已知参数写入类型契约。** `BrokerProtocol` 对交易选项大量使用 `**kwargs`，部分查询没有返回类型；Strategy 构造注解仍指向具体 Broker，运行时却接受 Protocol。参数拼写、退出配置、portfolio、返回对象的静态检查不完整。先完善现有签名即可，不必增加转发 API。

## 内部结构评估

建议保留当前模块布局，重点调整以下内部契约。

1. **建立明确的订单处理顺序。** 参数合法性检查、获取报价、推进必要风险、按当前仓位生成交易计划、市场/资金预检、提交记账、更新退出状态应有明确顺序。当前 `_resolve_market_price()` 名称像读取，实际可以改变价格、解锁和清仓，导致 R8-02/R8-06；Portfolio.submit_order 又重复估值，导致 R8-03。
2. **统一账本提交边界。** Portfolio 管理现金，Position 管理数量/成本，Broker 管理订单/退出，跨对象操作缺少明确的提交点。优先为强平和平仓计划建立局部原子提交，避免每个方法分别假定其他状态已经正确。可用内部数据结构描述结算结果，不需要通用命令总线。
3. **集中标识、时间和数值校验。** `data.model`、Binance kline/cache、通用 storage 各有时间/标的转换；Broker 又采用不同规则。共用纯函数可以减少这类偏差，并让单位和输入契约更明确。
4. **控制核心类的职责。** Broker 有 1,666 行，长度本身不是缺陷；实际难点是账户路由、价格选择、撮合、退出条件、运行保护和盈亏归档集中在同一状态对象中。可先抽离纯价格解析、订单预检和退出配置合并，围绕真实状态边界拆分。
5. **减少跨模块私有状态耦合。** Exchange 直接设置 Broker 的 `_run_*` 字段，run 入口读取 Exchange 的 `_run_state` 并调用 `_close_resources`；相同生命周期规则散布于三个模块。可以集中内置对象的生命周期处理，同时继续让插件协议保持较小范围。
6. **明确可变对象所有权。** 当前文档已明确 `get_position/get_positions` 返回活 Position，因此这里没有作为新 bug 重报。但 Broker 的 portfolios/orders、活 Order、Position 允许绕过交易方法修改状态，控制/结束阶段的只读保护只能约束方法调用。需要更强保护时，应提供只读查询视图或快照，并让内部修改使用明确入口。
7. **共享账户历史避免重复保存。** Exchange 保存每个 Broker 的历史，Strategy 也为每个策略保存历史；多策略共享一个 Broker 时会重复采样和存储相同账户数据。可让 Strategy 历史查询读同一个内部记录器，保留现有查询 API。

这些结构改进应服务具体问题，优先修复价格、时间、结算和退出条件的不变式。

## 覆盖与验证记录

| 范围 | 静态审阅 | 本轮运行的针对性验证 |
| --- | --- | --- |
| Broker / Portfolio / Position / Cash / Market | 全部 | 全仓强平顺序、平仓反向开仓、限价估值、无穷价格、NaN 退出条件、休市成交和 T+1、symbol 路由、退出条件合并、订单扫描次数 |
| Exchange / Strategy / Result / run / protocols | 全部 | 两策略回调容器污染；上述回测中的状态、曲线、结果快照；毫秒键冲突 |
| data / MemoryFeed / replay | 全部 | 事件构造、Kline 时间标签、相邻毫秒批次碰撞、残留模块导入 |
| Binance plugins | 全部 | 模拟下载响应的首段缺失、cache-only 复用、SQLite 连接释放；没有请求真实 Binance 服务 |
| storage plugins | 全部 | 临时通用 CSV 的部分 symbol 缺失；iosql 实现作静态审阅，没有连接外部数据库 |
| plot / logger / utils / skills 入口 | 全部 | 本轮没有额外执行图形界面或重新构建安装包 |
| 18 个 examples | 全部 | 核对调用链和状态处理；没有把示例策略当作真实市场收益验证，也没有批量运行绘图脚本 |
| packaging / release workflow | 静态审阅 | 没有安装依赖、构建或发布 |

复现全部使用当前源码。报告中的行为观察不是既有测试套件的运行结果；本轮没有重新评价测试覆盖率，也不据此声称不存在其他缺陷。

## 建议处理顺序

1. 先修 R8-01/02/03/04/06：统一合法性检查、时间来源、估值与成交、风险结算顺序，保证账本和交易意图正确。
2. 明确并修正 R8-05 的 Kline 可见时间，再验证多周期与 News 混合回放。
3. 修复 R8-07/08/09 的配置、数据和标识一致性。
4. 处理 R8-10/11/12 的性能、覆盖范围和资源释放。
5. 清理 R8-13/14，随后按实际使用场景完善类型、结果查询和错误类别。

实施时建议为每个已复现问题增加能够断言预期行为的回归用例；本次审查没有修改这些实现。
