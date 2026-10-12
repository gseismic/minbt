# Exchange 单次运行与控制回调设计

状态：历史回测部分已实施。未来 live 的接入与等待轮询尚未实施。

一个 Exchange 对应一次有状态运行，`run()` 只启动一次。运行期间，通过一个可选控制回调统一决定所有策略继续、暂停或中途退出。暂停时，行情、Broker 和账户历史持续推进；退出时，整次回测结束，返回退出前的结果和明确的结束状态。

本文定义当前历史回测的单次生命周期、控制回调、时间窗口与结果快照，并保留未来 live 所需的控制语义。下文历史回测接口与示例对应当前实现。

## 1. 用户场景与核心接口

| 场景 | 使用方式 |
| --- | --- |
| 普通回测 | 注册数据与策略实例，调用一次 `run()` |
| 暂停自动策略执行 | 控制回调返回 `pause`，账户继续接收行情 |
| 继续策略执行 | 控制回调返回 `continue`，从当前行情恢复回调 |
| 中途退出并检查结果 | 控制回调返回 `exit`，获取已处理区间的快照 |
| 追加历史数据验证后续表现 | 用新 Exchange、Strategy、Broker 从原起点完整重放，评估新增区间 |
| 独立窗口或不同参数实验 | 每次实验独立构造运行对象 |

普通回测保持最短路径：

```python
from minbt import Broker, Exchange


broker = Broker(initial_cash=10_000)
strategy = MyStrategy("sma", broker=broker)
exchange = Exchange()
exchange.set_bars(data)
exchange.add_strategy(strategy)
result = exchange.run()
```

`MyStrategy` 与 `data` 是使用者提供的策略类和历史数据。保留 `add_strategy(strategy)` 的实例注册方式。

运行入口：

```python
from datetime import datetime
from typing import Callable, Optional, Union


class Exchange:
    def run(
        self,
        *,
        start: Optional[Union[str, datetime]] = None,
        end: Optional[Union[str, datetime]] = None,
        control: Optional[Callable[[], str]] = None,
        load_mode: str = "auto",
    ) -> "RunResult": ...
```

`load_mode` 沿用当前实现的读取方式选择。各种读取方式必须遵守相同的窗口、控制和结果契约；后续统一回放内核按已有[用户接口与内核重构设计](minbt-20260921-api-refactor.md)实施。

`run()` 是阻塞入口，表示启动并持有本次执行循环，不保证策略始终执行。未提供 `control` 时，按 `continue` 运行至窗口结束。控制作用于本次运行中的所有策略，Strategy 保持现有生命周期与行情回调接口。

## 2. 控制回调契约

控制回调不接收参数，只读取调用方的控制状态，返回以下三个字符串之一：

| 返回值 | 策略行情回调 | 行情、Broker 与历史记录 | 是否返回结果 |
| --- | --- | --- | --- |
| `continue` | 执行 | 持续推进 | 否，继续循环 |
| `pause` | 全部停止 | 持续推进 | 否，继续循环 |
| `exit` | 不再执行 | 停止处理后续批次 | 是，结束整次回测 |

回调返回当前期望状态，不是一次性命令。重复返回同一值不重复记录状态变化；从 `pause` 返回 `continue` 即恢复行情回调。返回 `None`、布尔值或其他字符串抛 `ValueError`，回调自身的异常原样传播。非可调用的 `control` 在启动前抛 `TypeError`。

控制回调由运行线程同步调用，暂停期间仍然调用。它负责读取控制意图，不承担交易或账户修改；需要重建策略业务状态时，可以在同一线程检测转换后准备。使用者自行管理状态来源，框架不负责创建线程或接收外部指令。

外部控制可以使用标准线程同步对象：

```python
from threading import Event


pause_requested = Event()
exit_requested = Event()


def control():
    if exit_requested.is_set():
        return "exit"
    if pause_requested.is_set():
        return "pause"
    return "continue"


# 界面或其他控制线程通过 Event.set()/clear() 改变状态。
result = exchange.run(control=control)
```

需要同时响应界面、Agent 或其他外部输入时，调用方将 `run()` 放在工作线程中。外部线程只更新自己的控制状态，不直接修改运行中的 Strategy 或 Broker；账户处理仍由运行线程完成。

### 2.1 暂停与继续

暂停关闭所有策略的 `on_bars/on_books/on_trades/on_news` 行情回调，兼容期的 `on_bar` 同样关闭。指标、信号和业务计数不因行情推进而更新。

Broker 继续更新价格、估值和市场日切，处理已提交挂单、已有退出规则与风控。账户权益和持仓历史照常采样。暂停不自动撤单或平仓，因此暂停期间仍可能成交、强平和产生盈亏。Broker 管理的退出条件，包括用户配置的条件函数，属于已有账户规则，继续执行。

继续时保留策略与账户的当前状态，不补发暂停期间的数据，不重复初始化。指标重建或重新预热由使用者的业务逻辑处理；框架不保证恢复后指标已经就绪。依赖策略指标的账户退出条件，也需要由使用者保证其输入在暂停期间仍然适用。

`on_init()` 与 `on_finish()` 是生命周期通知，不作为暂停期间的行情回调被跳过。

### 2.2 中途退出与 soft 语义

控制回调返回 `exit` 时，结束整个执行循环，关闭读取资源并返回退出前的结果。退出后不继续处理行情，不补造后续曲线点，不自动撤单或清仓；最终持仓和 pending 订单保留在快照中。

这里的 soft 语义是受控退出正常返回已有结果。所有回测共用这一行为，无需另设模式开关。返回对象不代表正常完成：主动退出必须标记为 `exited`。程序异常仍然抛出，不能转换成看似完成的结果。

退出是本次运行的终态。暂停和继续发生在同一次 `run()` 内；已经退出的 Exchange 不能重新启动。

## 3. 时间批次与控制生效边界

历史回放在每个完整时间批次开始前调用一次控制回调。同一时间点的所有 symbol 和数据类型共用本次返回值，不逐标的或逐回调重新检查。

每个窗口内批次的处理顺序为：

```text
读取并收齐同一时间点的数据
  → 调用 control()，检查返回值并记录状态变化
  → 如果是 exit，结束循环，不处理该批次
  → 设置当前行情时间
  → 所有 Broker 完成市场更新、挂单和退出规则处理
  → 如果是 continue，执行全部策略行情回调
  → 记录账户权益与持仓历史
  → 更新最后完整处理时间和步数
```

控制回调执行时，`exchange.get_current_dt()` 表示上一批已处理的行情时间，初始为 `None`。退出时，已经读入但尚未处理的下一批数据不进入曲线、订单或进度统计。数据读取可能预读，已读取不等于已执行。

开始处理一个批次后，不在其中途切换控制状态。批次执行期间收到的外部变化，在下一次检查时生效；当前回调与账户操作不会被强行打断。`step_count` 统计完整处理的时间批次数，暂停批次也计入，不等于行情行数。

如果第一批处理前返回 `exit`，可以返回零进度快照，`first_dt/last_dt` 为 `None`、`step_count=0`。启动后的初始化与结束通知仍各执行一次。

控制响应依赖同步操作返回。当前 Feed 准备、预加载、数据读取和用户回调可能阻塞，不能承诺在这些操作内部即时退出。

## 4. 单次生命周期与对象隔离

内部生命周期为 `ready → running → completed / exited / failed`。暂停是行情回调的执行状态，运行循环仍处于 `running`。

配置、参数与读取模式校验通过后，在任何读取或策略回调之前占用本次生命周期。启动前的校验失败可以修正后重试；一旦开始读取或初始化，正常完成、主动退出和执行失败都不能再次启动。递归或并发调用同一 Exchange 的 `run()` 抛 `RuntimeError`。

启动调用一次 `on_init()`。自然结束和主动退出都调用一次 `on_finish()`，即使最终控制状态仍为 `pause`。结束通知只用于报告和本地清理，不能作为追加交易或修改账户的入口。执行失败不补调结束通知，已经调用过的通知也不重试；结束通知自身失败时不返回结果。

正常完成或受控退出时，先冻结最后实际处理点的账户数据、历史与控制记录，再执行结束通知并关闭资源；所有收尾步骤完成后才返回结果。初始资金在初始化前保存，不从第一条曲线观测推算。收尾异常按失败传播，不把已经准备的快照当作正常结果返回。

每次独立实验使用新的 Exchange、Strategy、Broker 和独立的数据读取游标。只创建新 Exchange 不会清除旧账户状态。内置 Strategy 和 Broker 使用轻量归属及已使用标记拒绝跨实验复用；同一实验内允许多个策略共享一个 Broker，并保证每个批次只推进该 Broker 一次。自定义 Broker 的状态隔离由调用方负责，不扩充其强制协议。

启动后固定数据源、策略和账户关联，禁止增删策略、替换数据源或切换 Broker。控制回调不能借此重入或修改注册关系。

## 5. 历史时间窗口与后续验证

回放区间为 `[start, end)`。`None` 表示不额外限制对应一侧，实际边界由数据源决定；`end=None` 包含来源最后一个有效时间点。Exchange 不要求 Feed 提供起止属性，也不从多个来源中推导共同起止时间。

时间输入标准化为 UTC，无时区输入按 UTC 解释。窗口依据公开事件时间 `dt` 过滤，保持数据源原有的时间含义。过滤在 Broker 处理和策略回调之前完成，窗口外数据不推进行情、账户或历史记录。

`start >= end`、无数据源或无策略抛 `ValueError`。自然读取后发现窗口内没有数据也抛 `ValueError`，与主动退出的零进度结果区分。请求范围可以超过数据实际范围，结果记录实际第一、最后处理时间。统一过滤不修改 Feed 的原始配置，也不保证降低预加载或下载成本。

从指定 `start` 运行是一个新实验，不会自动重建之前的指标、持仓和账户。验证原策略在新增数据上的后续表现，应从原起点完整重放：

```python
def backtest(data):
    broker = Broker(initial_cash=10_000)
    strategy = MyStrategy("sma", broker=broker)
    exchange = Exchange()
    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    return exchange.run()


june_result = backtest(data_to_june)
october_result = backtest(data_to_october)
```

旧段一致性依赖旧数据、配置、随机输入与暂停/继续过程相同，策略只使用当时可见的数据，运行终点不改变旧段决策，结束通知不改变账户。完整重放不是对任意策略都无条件等价。

没有外部资金流入流出时，新增区间净盈亏等于新增段结束权益减去新增段开始前最后一次权益。不能仅筛出新段订单来计算延续收益。例如单份持仓、不计手续费时，买入价 100、切点价格 110、新段卖出价 115，新增收益为 5，平仓已实现盈亏为 15。暂停期间的账户变化同样计入收益。

## 6. 结果快照与曲线

`run()` 返回独立 `RunResult`，只保存数据，不持有活的 Strategy、Broker、Portfolio、Order 或读取游标。常用查询保持简短：

```python
from datetime import datetime
from typing import Any, Dict, List, Mapping, Tuple

from minbt import Pnl


class RunResult:
    meta: Mapping[str, Any]

    def get_initial_cash(self, *, strategy_id=None) -> float: ...
    def get_equity_curve(self, *, strategy_id=None) -> List[Tuple[datetime, float]]: ...
    def get_position_curve(self, symbol: str, *, strategy_id=None) -> List[Tuple[datetime, float]]: ...
    def get_orders(self, *, strategy_id=None) -> List["OrderSnapshot"]: ...
    def get_total_pnl(self, *, strategy_id=None) -> Pnl: ...
    def get_position_sizes(self, *, strategy_id=None, portfolio=None) -> Dict[str, float]: ...
```

权益曲线覆盖整个 Broker；持仓曲线记录默认 `main` 分仓，与现有持仓历史口径一致。所有曲线使用实际处理时间，暂停期间持续记录，退出后止于 `last_dt`。持仓曲线与权益曲线时间点对齐，无持仓时记录零，从未持有的标的返回同样时间点的零曲线。最终持仓查询默认也是 `main`，可通过 `portfolio` 指定分仓，未知分仓抛 `ValueError`。初始资金单独查询，第一条权益观测可能已经包含交易手续费。

单策略时可省略 `strategy_id`，多策略时必须指定；未知 ID 抛 `ValueError`。共享 Broker 的策略 ID 查询同一账户，账户结果不能自动归因到某个策略，也不能把别名结果相加。无 Broker 的策略仍有运行元数据，账户查询抛 `ValueError`。

最终持仓、订单和盈亏按实际退出点冻结。订单使用不可变 `OrderSnapshot`，复制现有 `Order` 数据字段，不保留修改订单或执行退出条件的能力。`Pnl` 沿用现有不可变类型与[库级盈亏查询设计](pnl-20261011-library-api.md)。查询返回新的列表或字典，外部修改不影响快照；原运行对象后续变化也不影响旧结果。

完整查询由内置 Broker 支持。自定义 Broker 已有协议支持的账户观测照常记录；只支持默认分仓时，采样和快照都使用默认查询，不强制具名分仓能力。缺少初始资金、订单或盈亏等数据能力，或可选查询明确声明 `NotImplementedError` 时，仅相关结果查询报未实现，不返回伪造的零结果；其他查询异常仍使运行失败。

绘图直接读取结果数据，主动退出的结果同样可用：

```python
import matplotlib.pyplot as plt


curve = result.get_equity_curve()
if curve:
    dates, equity = zip(*curve)
    plt.plot(dates, equity)
plt.title(f"回测权益：{result.meta['status']}")
plt.show()
```

这里的完整结果指实际处理区间的信息完整，不表示提前退出后仍覆盖原计划的全部区间。

## 7. 返回元信息

`result.meta` 是只读映射；其中的控制记录也不可变。

| 字段 | 含义 |
| --- | --- |
| `status` | `completed` 或 `exited`，由实际结束路径确定 |
| `reason` | `feed_exhausted`、`end_reached` 或 `control_exit` |
| `control_state` | 最后生效的 `continue/pause/exit` |
| `start/end` | 标准化后的请求边界，未指定时为 `None` |
| `first_dt/last_dt` | 第一、最后完整处理的时间，零进度时为 `None` |
| `step_count` | 完整处理的时间批次数，包含暂停批次 |
| `strategy_ids` | 本次运行的策略 ID 元组 |
| `control_events` | 实际控制状态变化的记录元组 |

自然读完来源时为 `completed/feed_exhausted`；遇到第一个 `dt >= end` 的批次而结束时为 `completed/end_reached`，该批次不调用控制回调、不处理账户。主动退出为 `exited/control_exit`。指定了 `end` 但来源提前读完，原因仍为 `feed_exhausted`。`completed` 只表示可用数据按窗口处理完毕，不表示策略全程执行、盈利或通过验证；暂停状态下也可能自然结束，此时 `control_state="pause"`。

`control_events` 每项为 `(after_dt, step_count, action)`。`after_dt` 是控制变化生效前最后完整处理的时间，尚无进度时为 `None`；`step_count` 是当时已完成批次数；`action` 为 `pause/continue/exit`。初始期望状态为 `continue`，未变化时不记录；第一次就返回 `pause` 或 `exit` 时记录零进度变化。

记录的状态从第 `step_count + 1` 个批次开始适用；`exit` 记录之后没有下一批次。相同状态的重复检查不增加记录。控制记录可用于标注暂停区间，所有变化统一作用于全部策略，不增加逐策略归属字段。

运行日志与元信息使用相同结束语义，不能在主动退出后输出默认的全部完成消息。

## 8. 异常、资源与未来 live

数据读取、控制回调、策略回调、结束通知或结果构造发生异常时，关闭本次资源，内部生命周期进入 `failed` 并抛出异常，不返回 `completed` 或 `exited` 结果。不重置或重试已消费对象。关闭异常不能覆盖已有业务异常；单独的关闭失败也不能被当作正常返回。

曲线采样与进度只在完整批次结束后确认。批次中发生异常不承诺回滚 Broker，因此失败对象不能用于续跑；本设计不将半批次状态包装成可继续执行的结果。

未来 live 继续使用“市场与账户持续工作，策略行情回调可关闭”的语义。没有新行情时，运行循环仍需定期检查控制状态，读取等待必须可唤醒或有有限超时。控制回调不能假定每次调用都对应一条新行情；按状态返回值设计，才能适应等待期间的轮询。

live 的本地退出只结束本地执行，不能证明外部订单已撤销或账户已平仓。实时行情接入、跨来源对齐、成交回报、账户同步与断线重连需要独立设计。当前 `add_feed()` 仍只接收有限历史 Feed，本文不将其视为已有 live 能力。

## 9. 验收标准

1. 默认 `run()` 完成普通回测并返回 `completed`，实例注册主路径保持简短。
2. 同一 Exchange 只能启动一次；完成、退出、失败后及运行中重入均被拒绝。独立实验拒绝复用已消费的内置策略或账户，同次共享 Broker 仍可用。
3. `pause` 期间所有策略行情回调停止，已有挂单、退出条件、估值与风控继续，权益和持仓历史时间点连续。
4. `continue` 从当前批次恢复回调，保留状态，不重复初始化、不补发旧数据；指标准备由业务逻辑负责。
5. 控制仅在完整时间批次边界生效，所有标的和回调共用同一状态，暂停期间仍检查控制；非法返回值明确失败。
6. `exit` 停止整个回测，返回 `exited/control_exit`，不处理下一批次、不填充后续曲线；第一批前退出返回零进度快照。
7. 正常结束与主动退出的生命周期通知各执行一次；最终仍暂停时也执行结束通知，执行异常不伪造完成结果。
8. 元信息的结束原因、最终控制状态、实际时间、步数与控制记录一致；重复状态不重复记录，日志不把退出写成正常完成。
9. `[start, end)`、单侧 `None`、多来源、空窗口和不同读取模式符合相同语义，窗口外行情不触发账户推进。
10. 修改查询返回容器或原运行对象不改变旧快照；曲线、最终订单、持仓与盈亏对应同一实际结束点。
11. 追加数据采用新对象完整重放，固定旧段输入和暂停/继续过程时旧段一致，新增收益使用正确的切点权益。
12. 各阶段异常及主动退出都释放读取资源，原始异常优先传播，失败对象不能续跑。

实施记录见 [PLAN-058](../dev/PLAN-058-run-control.md)，使用说明见仓库 README，运行示例见 `examples/10_run_control.py`。
