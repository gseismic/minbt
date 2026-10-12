# 最小运行结果协议

状态：已实施；ResultProtocol、OrderProtocol、OrderSnapshot、PnlProtocol 位于 `minbt.protocols.result`。
RunResult 实现位于 `minbt.result`；根包直接导出常用结果类型，OrderSnapshot 的定义只有一处。

## 1. 先标准化当前接口

目前 RunResult 已经独立于活账户，提供带时间的权益、持仓曲线、订单快照、初始资金和累计盈亏。
这些接口足以支持基础绘图，不需要先增加六张输出表、记录事件总线或结果存储框架。

最小协议集中表达当前查询；返回记录的字段沿用现有定义：

```python
from datetime import datetime
from typing import Any, Dict, List, Mapping, Protocol, Tuple

from minbt.protocols.result import OrderSnapshot, PnlProtocol

class ResultProtocol(Protocol):
    meta: Mapping[str, Any]

    def get_initial_cash(self, *, strategy_id=None) -> float:
        ...

    def get_equity_curve(self, *, strategy_id=None) -> List[Tuple[datetime, float]]:
        ...

    def get_position_curve(self, symbol: str, *, strategy_id=None) -> List[Tuple[datetime, float]]:
        ...

    def get_orders(self, *, strategy_id=None) -> List[OrderSnapshot]:
        ...

    def get_total_pnl(self, *, strategy_id=None) -> PnlProtocol:
        ...

    def get_position_sizes(self, *, strategy_id=None, portfolio=None) -> Dict[str, float]:
        ...
```

PnlProtocol 描述当前四个字段 realized_pnl、unrealized_pnl、fees、settlement_adjustment 与 net_pnl
只读属性；标准订单记录描述 OrderSnapshot 字段。集中类型声明，调用处直接引用。

不要求每个数据提供者或 Broker 都支持全部查询。当前可选能力缺失时继续抛 NotImplementedError，
没有 Broker 时明确报错；不返回伪零权益、伪空订单或猜出的盈亏。

## 2. 快照和语义保持不变

- 元信息、曲线、订单和最终持仓对应同一次实验及真实结束点。
- completed/exited 和当前 reason/control_events 保留；失败继续抛异常。
- pause 时市场、账户和曲线仍推进，exit 不补未执行点，不自动平仓。
- 共享账户不复制资金，不把同一份盈亏当作每个策略的独立贡献。
- 查询返回容器不会污染快照；不持有活 Broker、Strategy、连接或退出回调。
- get_hist_equity/get_hist_position_sizes 仍返回原 list，缺失标的数量语义不变。
- 标准字段使用真实账本数据，不通过 repr 或最终订单猜测成交事实。

现有历史重复记录可以局部整理，但不能一边保留两份旧历史，一边又新增一套 Recorder 管线。
快照构造已经接受符合字段契约的记录；订单深拷贝并冻结，Pnl 按原四项口径复制为公共 Pnl。
net_pnl 必须有限且与四项计算一致，否则抛 ValueError；缺少标准字段抛 TypeError。

## 3. 绘图直接消费结果

以下使用当前已实现查询，数据无外部资金变化时可以这样计算净权益盈亏：

```python
initial_cash = result.get_initial_cash()
curve = result.get_equity_curve()
times = [dt for dt, equity in curve]
equity = [value for dt, value in curve]
net_pnl = [value - initial_cash for value in equity]
```

费用已经反映在权益中，不再减一次。存在外部资金变化或不同初始资产时，不能沿用这个简式，
应由自定义 Broker 提供清楚的口径和净盈亏查询，核心不猜测或自动补资金流水。

绘图库独立使用 times/equity/net_pnl，不导入数据 reader 或具体市场实现。原 plot 辅助函数保留；
没有需要时也不必新增一个绘图插件体系。

## 4. 当前不增加的内容

成交逐笔表、流水表、多账户换汇、自定义指标录制、额外 Pnl 字段、save/load、多格式持久化和全量数据
指纹不是本次协议化的前置条件。有实际需求时增加可选查询或独立工具，避免一次扩张核心。

普通用户仍通过现有 RunResult 查询取得输出；新的引擎适配器需要把它自己的真实结果映射到这个契约。
详细边界见 [总设计](../kernel-20261012-protocol-plugins.md)。
