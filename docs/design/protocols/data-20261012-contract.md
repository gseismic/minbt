# 用户自备数据协议

状态：已实施；声明位于 `minbt.protocols.data`。参见 [总设计](../kernel-20261012-protocol-plugins.md)。

## 1. 数据责任

用户负责准备、清洗、字段映射和决定数据何时可见。库接收用户已经准备的数据或用户实现的读取器。

核心不能根据标的名称猜数据来源、时区、交易日、复权方式或价格含义。读取自定义文件的代码可以
位于用户项目，也可以作为可选实现放入 minbt.plugins；它不成为核心依赖。

## 2. 最小 Feed 保持不变

```python
from typing import Iterable, Protocol

from minbt.protocols.data import MarketEvent

class DataFeedProtocol(Protocol):
    name: str

    def events(self) -> Iterable[MarketEvent]:
        ...
```

使用 Bar(dt, symbol, kind, data)、News 和自定义 kind。协议从 `minbt.protocols.data` 导入；
具体读取器从 `minbt.plugins` 导入，不保留旧数据读取路径。
不要求为自定义数据额外包装市场对象、来源描述类或插件注册记录。

`protocols.data` 中的 BarProtocol/NewsProtocol/TimeBatch/BatchItem 描述结构；默认 Exchange 的
事件仍使用 `minbt.Bar`/`minbt.News` 构造，批次使用 `minbt.data.replay.TimeBatch`/BatchItem。
协议不是这些记录的另一个构造实现，默认引擎不会把任意鸭子类型记录自动转换成 Bar/News。

最短接入仍是 `exchange.set_bars(data)`。需要按需读取时实现 events；一个来源返回多个标的也不需要
另外的“多标的 Feed”接口。

## 3. 时间和载荷

- dt 表示这份记录进入回放的时间；用户/读取器负责让它符合数据真实可见时间。
- Bar 保留当前时间归一化和毫秒批次精度，旧无时区输入的处理不改变。
- 自定义 reader 明确解释时间戳单位与时区，不让 Exchange 猜测。
- 完整区间数据不能在尚不可知的时点发给策略，这由用户准备的数据和 reader 保证。
- 核心不自动把日期移动到某个收盘时点，不增加必需 available_dt 字段或市场日历。
- data 保留当前载荷能力；标准字段由用户策略和所用 Broker 约定。
- 原 symbol 归一化及回调分组保留，不能在搬迁时悄悄改标识。

2026-10-13 修正：数据、交易、查询和市场路由统一使用非空字符串、去首尾空白并转大写。
毫秒键用 UTC epoch 差值的整数运算生成。截面回调的映射及 Trade 序列只读，策略自行复制容器后处理。
三个 Binance Kline reader 按 close_time 调度完整行，保留 open_time；读取 start/end 按开盘时间筛选，
运行窗口按事件可见时间筛选。缺收盘时间不得回退到开盘时间。
具体状态、缓存完整性与验证见 [执行不变式](../execution-20261013-invariants.md)。

如果用户需要额外时间或信号，可以放在 data 中供策略/Broker 读取。需要新时间语义时单独增加可选
能力，不能先对所有 Feed 更改构造参数或调度时点。

## 4. 读取能力与资源

现有能力字段和安全默认值保留：

| 属性/方法 | 约定 |
| --- | --- |
| supports_preload | 缺省 True，有限历史输入可预加载 |
| supports_incremental / ordered | 缺省 False，声明有序渐进读取后仍需实际校验 |
| replayable | 沿用现有声明，不能据此假设原文件永不变化 |
| feed_priority | 缺省 0，保留当前排序和重叠处理 |
| prepare | 可选，缺失无操作，不能在核心偷偷下载 |
| close | 可选，释放自有资源，幂等；缺失不免除内部迭代器的清理 |
| is_live | 当前 Exchange 继续只接受有限历史输入 |

同一时间的数据先收齐再推进账户，保留当前 TimeBatch/BatchItem 和唯一批次边界，不同时重写回放方式。
声明有序却回退、非法记录或源内重复按当前规则失败；不能为简化接入而吞错或自动覆盖。

成功、窗口结束、退出和异常都关闭迭代器及 Feed。工厂应为每次运行创建新读取对象；数据读取失败
包含来源和行号/主键。运行不自动修改或补齐用户原始数据。

## 5. 示例：使用当前接口

```python
from minbt import Bar

class MyFeed:
    name = "prepared-data"

    def events(self):
        for row in self.prepared_rows:
            yield Bar(
                dt=row["dt"],
                symbol=row["symbol"],
                kind="kline",
                data={"close": row["close"]},
            )

    def __init__(self, prepared_rows):
        self.prepared_rows = prepared_rows
```

该例不限定存储格式。用户可在外部读取后传入行，也可在 events 中从自己维护的文件/数据库读取。
内核只依赖 Feed，不依赖这些存储或数据源 SDK。
