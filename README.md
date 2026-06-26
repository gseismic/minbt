# minbt

minbt 是一个简易的量化回测框架，主要面向 T+0 的加密货币和其他高频换仓场景。项目刻意保持小规模代码量，核心目标是让用户用最少样板代码完成多空双向、市价撮合、保证金和分仓回测。

## 主要特点

- [x] 支持 pandas、polars 和 `list[dict]` 行情输入。
- [x] 支持市价单。
- [x] 支持多空双向持仓。
- [x] 支持动态杠杆。
- [x] 支持逐仓和全仓两种保证金模式。
- [x] 支持多 portfolio 分仓。
- [x] 自动记录策略权益和持仓历史。
- [ ] 支持限价单。
- [ ] 支持止盈止损。

## 安装

从源码目录安装：

```bash
pip install -e .
```

核心依赖：

```text
numpy
pandas
polars
loguru
```

可选依赖：

```bash
pip install -e ".[pyta]"
```

`pyta_dev` 可用于更高效的历史向量存储；未安装时 minbt 会自动回退为 Python list。

## 快速开始

下面示例使用内存行情数据完成一个最小回测。行情至少需要 `symbol` 和 `close` 两列；如果提供 `date_key`，Exchange 会按 `date_key` 和 `symbol` 稳定排序。

```python
import pandas as pd
from minbt import Broker, Exchange, Strategy


class DemoStrategy(Strategy):
    def on_init(self):
        self.orders = 0

    def on_data(self, row):
        symbol = row["symbol"]
        price = row["close"]

        if self.orders == 0:
            self.broker.submit_market_order(symbol, qty=1, price=price, leverage=2)
        elif self.orders == 2:
            self.broker.submit_market_order(symbol, qty=-1, price=price)

        self.orders += 1

    def on_finish(self):
        print("equity:", self.broker.get_total_equity())
        print("position:", self.broker.get_position_size("BTCUSDT"))


data = pd.DataFrame(
    [
        {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
        {"dt": "2026-01-02", "symbol": "BTCUSDT", "close": 110.0},
        {"dt": "2026-01-03", "symbol": "BTCUSDT", "close": 120.0},
    ]
)

exchange = Exchange()
exchange.set_data(data, date_key="dt")

broker = Broker(initial_cash=10_000, fee_rate=0.001, leverage=2.0)
strategy = DemoStrategy(strategy_id="demo", broker=broker)

exchange.add_strategy(strategy)
exchange.run()
```

也可以直接运行仓库示例：

```bash
python examples/demo_mini.py
```

示例文件：

- [examples/demo_mini.py](./examples/demo_mini.py)
- [examples/data.csv](./examples/data.csv)

## 行情数据约定

`Exchange.set_data(data, date_key=None)` 支持三种输入：

- `pandas.DataFrame`
- `polars.DataFrame`
- `list[dict]`

必需字段：

- `symbol`: 标的代码。
- `close`: 当前 bar 的成交价格，市价单默认按该价格成交。

时间字段：

- 推荐传入 `date_key`，例如 `dt` 或 `timestamp`。
- 传入 `date_key` 时，数据会按 `[date_key, symbol]` 排序。
- 不传 `date_key` 时，Exchange 使用行号作为时间戳，并要求数据中只能有一个 `symbol`。

## 核心对象

### Exchange

`Exchange` 负责保存行情数据、按行广播行情、维护最新价格，并调度策略生命周期：

- `on_init()`: 回测开始前调用。
- `on_data(row)`: 每行行情调用一次。
- `on_finish()`: 回测结束后调用。

### Strategy

用户通常继承 `Strategy` 并实现 `on_data`。策略可通过 `self.broker` 下单和查询账户状态：

```python
self.broker.submit_market_order("BTCUSDT", qty=1, price=100, leverage=3)
self.broker.submit_market_order("BTCUSDT", qty=-1, price=105)
self.broker.get_total_equity()
self.broker.get_position_size("BTCUSDT")
```

`qty > 0` 表示买入或做多，`qty < 0` 表示卖出或做空。反向下单会先平掉已有仓位，超出部分再开反向仓位。

### Broker 和 Portfolio

`Broker` 管理一个或多个 portfolio。默认创建 `default` portfolio：

```python
broker = Broker(initial_cash=100_000, fee_rate=0.001, portfolio_cash=60_000)
broker.add_sub_portfolio("alt", initial_cash=30_000)
```

权益查询语义：

- `broker.get_total_equity()`: 所有 portfolio 权益加未分配现金。
- `broker.get_all_portfolio_equity()`: 所有 portfolio 权益，不含未分配现金。
- `broker.get_equity(portfolio_id=None)`: 指定 portfolio 权益；默认返回主 portfolio。
- `broker.get_cash(portfolio_id=None)`: 指定 portfolio 可用现金。

## 资金和保证金模型

开仓时：

- 手续费为 `abs(qty) * price * fee_rate`。
- 保证金占用为 `abs(qty) * price / leverage`。
- 手续费从现金扣除，不计入持仓未实现盈亏。

逐仓模式：

- 每个 symbol 独立计算 `position.equity / position.margin`。
- 单个仓位触发穿仓或强平时，只影响该仓位。

全仓模式：

- 使用账户级权益计算保证金水平：`portfolio_equity / total_margin`。
- 可用现金会作为全仓风险缓冲。
- 账户穿仓时，该 portfolio 会被标记破产，现金和持仓归零。

## 日志

全局 logger 支持中英文消息：

```python
from minbt import logger

logger.set_lang("zh")
logger.info("[start_strategy]", "demo")
logger.info("on_data", {"symbol": "BTCUSDT", "close": 100})
```

普通消息支持 `{}` 格式化；没有占位符但传入参数时，会追加参数文本，避免日志参数被静默丢弃。

## Codex Skill

仓库包含一个面向 Codex 的本地 skill：

```text
./skills/minbt-usage
```

在支持本地 skills 的 Codex 环境中，可以使用：

```text
Use $minbt-usage to build a minbt strategy for my CSV data.
```

该 skill 会提醒 Codex 遵循本项目的数据约定、保证金语义、测试命令和文档规范，适合生成策略、排查资金/仓位问题、补测试或更新示例。

## 测试

运行全量测试：

```bash
pytest -q
```

运行基础编译检查：

```bash
python -m compileall -q minbt tests
```

当前测试环境可能出现 `Polars binary is missing!` warning；这属于环境依赖警告，不影响现有测试通过。

## 设计约束和已知限制

- 目前只实现市价单，限价单、止盈止损和追踪止损接口仍是 `NotImplementedError`。
- Exchange 不负责拉取或缓存历史行情，用户需要自行准备数据。
- 市价单在回测中按当前 `close` 成交，未模拟订单簿、滑点或部分成交。
- 多 symbol 数据应显式传入 `date_key`，否则只允许单 symbol。

## ChangeLog

- [@2026-06-24] v0.0.4：修复全仓保证金、总权益统计、日志参数和 Python 3.8 注解兼容问题。
- [@2024-11-16] v0.0.3 release。
