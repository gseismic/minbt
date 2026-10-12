# 最小 Broker 与扩展契约

状态：已实施；声明位于 `minbt.protocols.broker`。参见 [总设计](../kernel-20261012-protocol-plugins.md)。

## 1. 数据和 Broker 独立组合

自定义数据不要求自定义账户；需要特殊交易或记账模型时才提供自己的 Broker。一个 Broker 可以
接收不同 Feed，同一 Feed 也可以用于不同实验中的不同 Broker。

用户直接创建并注入对象，或者给薄运行入口提供工厂。具体实现可以放入用户模块或 minbt.plugins，
无需 MarketPlugin 基类、注册表、命名市场包或工厂组合矩阵。

## 2. 策略侧协议沿用现有接口

BrokerProtocol 定义在 protocols/broker.py，扩展和调用处直接引用。使用当前交易和查询方法，
包括 submit_market_order、submit_limit_order、cancel_order、order_target_*、close_*、分仓与退出查询。

参数、符号数量、portfolio、Order 句柄和拒单/无交易状态不改变。协议化不增加通用 command/submit 层，
不为每个方法写一个新的门面转发实现。

具体 Broker 负责自己的合法性、费用、成交、现金、持仓、结算和盈亏；Exchange 不读取或修改该模型
的私有财务字段。用户不能仅更换数据就假设旧账户模型自动具有另一套财务语义。

2026-10-13 修正：有限数值检查先于账户副作用；有效显式价格先推进风险，目标和平仓数量按更新后
的持仓计算。成交价与市场估值分开，旧报价时间不能代替当前交易时钟。同一净持仓的退出条件
通过任一当前订单句柄按字段合并，保留函数 state，清除必须显式。全仓强平按账户一次结算。
完整边界见 [执行不变式](../execution-20261013-invariants.md)。

## 3. 只补当前实际需要的回放方法

Exchange 原本已调用 process_market_batch，本次通过 ReplayBrokerProtocol 补齐这个边界：

```python
from typing import Mapping, Protocol

from minbt.protocols.broker import BrokerProtocol
from minbt.protocols.data import TimeBatch

class ReplayBrokerProtocol(BrokerProtocol, Protocol):
    def process_market_batch(self, batch: TimeBatch) -> Mapping[str, float]:
        ...
```

这个方法按当前模型推进完整批次：估值、挂单、退出和风险处理。原 Broker 返回的价格映射仍保留，
不借补协议修改公共返回值。其他运行引擎不需要使用 TimeBatch，由其适配器桥接交易和结果。

不把 claim_run、phase、capture_state、close 等一组新方法强制加给每个用户 Broker。当前运行隔离、
控制/结束通知只读和异常清理由现有实现保障；共享保护逻辑可以局部抽取，不能再复制一套生命周期。

当前自定义 Broker 的隔离能力与内置实现可能不同，保持现有接入并明确约定；不能通过删掉内置保护
来获得表面统一，也不能宣称仅满足协议就能阻止用户绕过入口修改内部状态。

## 4. 状态与结果仍用已有查询

运行继续使用 get_total_equity、get_position_sizes 等现有查询。订单、分仓与累计盈亏查询保持可选：
不提供或明确未实现时，相关结果查询报错；不能把缺失能力伪装成空交易或零盈亏。

快照适配已经使用现有字段校验并复制。新增 Broker 无需返回具体内置 Order/Pnl 子类，
但必须保证标准字段和语义；不得根据最终订单反推不存在的成交明细。

本阶段不强制 BrokerRecordsProtocol、增量成交报告、另一套订单缓存或资金流水接口。等确实需要
这些输出时，在 Broker 侧增加独立可选查询，不挪入回放核心。

## 5. 扩展实现的组织

默认 Broker、订单、分仓、持仓、盈亏、撮合和退出属于回测基础能力，直接位于 `minbt.broker`。
可替换性通过协议和工厂表达；不需要把默认实现做成插件，也不保留 simulation 或模块转发层。
具体读取器和未来特殊市场行为可位于 plugins，核心不导入插件；当前经济模型没有重写。

用户实现可以复用原订单、分仓和退出组件，或完全提供另一个符合协议的 Broker。数据读取、规则与
财务计算不要求同时发布，也不要求每个实现都拆 calendar/rules/accounting 等多个模块。

原 add_market/Market 预设继续可用；本轮不新增市场预设、真实规则资料、汇率换算和组合账户。
跨市场路由的已有行为不删除；新的复杂路由等真实需求出现时再设计，不预建通用 Router。

## 6. 必要验收

- 旧策略调用、类型、状态、数值和异常语义保持一致。
- 自定义 Feed 配默认 Broker 可直接运行；需要时自定义 Broker 可独立替换。
- 回放推进方法有明确契约，结果不强制插件继承内置实现。
- 读取状态无副作用，预检和失败订单不污染账本。
- 一个 Broker 只有一份真实账本，不在引擎适配器或转发层再记一份。
