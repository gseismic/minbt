---
name: minbt-usage
description: 按当前安装版本的 minbt 编写、运行和调试回测策略，适用于行情数据接入、Strategy 回调、Broker 下单、退出条件、分仓、多市场和盈亏查询。不用于开发 minbt 框架内部实现。
---

# minbt 使用指南

帮助用户用少量代码完成一个可运行、可验证的回测。使用此 skill 所在安装包的已实现接口。

## 确认项目环境

用用户项目实际运行策略的 Python 查询版本与资源：

```bash
python -m minbt.skills
python -m minbt.skills --path
```

默认输出 minbt 安装版本和 skill 目录，`--path` 只输出目录。若当前加载的 skill 与输出路径不同，
读取输出目录中的 `SKILL.md` 及所需参考资料，按该环境的版本工作。不要因为其他版本的文档
而主动替换用户安装的版本。源码开发使用 editable 安装；普通使用无需克隆 minbt 仓库。

尚未安装时，用项目的包管理方式安装用户指定的版本，例如：

```bash
python -m pip install "minbt==用户指定版本"
```

核心依赖包含 NumPy、pandas、polars 和 loguru；`plot` 额外依赖提供 Matplotlib，`pyta` 提供可选
历史向量存储。未安装 pyta 时自动使用 Python list，公开历史查询始终返回 list。

## 最小成功路径

用户主要需要三个对象：`Exchange` 接收数据并推进时间，`Strategy` 实现交易逻辑，
`Broker` 提供唯一交易入口。`Order` 是下单结果和退出条件的句柄。

```python
from minbt import Broker, Exchange, Strategy


class BuyAndHold(Strategy):
    def on_bars(self, dt, bars):
        self.broker.order_target_size("TEST", 1)


broker = Broker(initial_cash=1_000)
strategy = BuyAndHold("demo", broker=broker)
exchange = Exchange()
exchange.set_bars([
    {"dt": "2026-01-01", "symbol": "TEST", "close": 100},
    {"dt": "2026-01-02", "symbol": "TEST", "close": 120},
])
exchange.add_strategy(strategy)
result = exchange.run()
print(f"final_equity={broker.get_total_equity():.2f}")
```

结果为 `final_equity=1020.00`：持有一个单位，价格上涨 20，默认零手续费。后续目标不变时
不会重复买入。随包脚本 [scripts/quickstart.py](scripts/quickstart.py) 提供同一可执行示例，
无需绘图、网络、CSV 或其他外部数据。

一个 Exchange 只启动一次 `run()`。独立实验、比较运行方式或追加历史区间时，新建
Exchange、Strategy 和 Broker，完整重放所需数据。

需要“策略类 + 参数文件”时，可调用 `from minbt import run`，传入策略类、JSON 路径或 Mapping，
以及自己实现的 `feed_factory=`。数据准备属于用户，工厂每次返回新的 Feed；可选
`broker_factory=` 替换账户。默认复用核心 Exchange/Broker 并返回 RunResult，手工装配也可直接使用。
具体写法及协议/插件路径见 [references/data-and-control.md](references/data-and-control.md)。

## 策略工作流

1. 检查用户数据的时间列、标的列和价格字段。有现成数据时优先 `set_bars()`，需要数据源接入时用 `add_feed()`。
2. 在 `Strategy.on_init()` 初始化指标状态，默认在 `on_bars(dt, bars)` 接收 `{symbol: row}`。
3. 用 `self.broker.order_target_size/value/percent(...)` 表达目标持仓；精确增量使用市价或限价单。
4. 检查 `Order.status` 的结构化结果，不依赖 `reason` 的精确文本。
5. 通过 Broker 或运行结果快照查询权益、持仓、订单与盈亏，给出脚本的最小运行命令和结果核对。

默认 K 线数据至少包含 `dt`、`symbol`、`close`，输入支持 pandas、polars 和 `list[dict]`。
单标的也是 `{symbol: row}`，不要省略标的层。同一 `(dt, symbol)` 只能有一条 K 线。
列名不同时指定 `date_key` 和 `symbol_key`；单标的缺少标的列时先补列。

```python
exchange.set_bars(data, date_key="date", symbol_key="ticker")
```

策略的 `dt` 是 UTC `datetime.datetime`。默认 Broker 用 `kline.close` 估值；价格字段不同或
来源冲突时，应明确配置 Broker 的 `mark_price`，不能仅靠下单价改变历史估值来源。

## 按需读取

- 自备数据、配置运行、协议/插件、行情格式、非默认价格、Binance/CSV/iosql Feed、多类数据、运行窗口、暂停与退出：读取
  [references/data-and-control.md](references/data-and-control.md)。
- 目标持仓、市价与限价单、退出规则、分仓、市场差异、订单查询与盈亏：读取
  [references/trading.md](references/trading.md)。

这些文件相对于本 skill 目录，全部随当前安装版本发布。用户已有的策略和数据应继续遵循其
现有约定；选择与当前任务相关的参考资料即可。

## 验证

将下面目录替换为 `python -m minbt.skills --path` 的输出，即可在任意工作目录验证安装：

```bash
python /path/to/minbt-usage/scripts/quickstart.py
```

给用户生成或修改策略后，用项目实际的 Python 运行该脚本，核对成交、最终权益与用户预期。
绘图脚本需要 `plot` 额外依赖；网络 Feed 或本地数据库需要相应数据条件。验证不依赖 minbt
仓库中的示例或测试目录。

## 结果解释

需要解释成交或盈亏时，说明与当前场景相关的限制：成交及退出条件使用当前最新价，不由
K 线 high/low 推断路径；不模拟滑点、队列位置或部分成交。账户是保证金账户，
`Position.equity` 不能当作现货市值。持仓未平时，权益和净盈亏包含浮动盈亏及已扣手续费。

交易与账户变化通过 Broker 完成；不要直接修改查询到的 Position，也不要在用户策略中
调用账户内部的价格更新、订单处理或退出检查接口。日志默认关闭，需要诊断时使用
`from minbt import logger; logger.enable("minbt")`。
