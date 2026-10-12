# minbt 设计文档索引

## 最新有效设计

- [交易、回放与缓存不变式](execution-20261013-invariants.md)：PLAN-067 修复全量 Review 的 14 项缺陷；
  明确强平提交、成交与估值、当前交易时间、Kline 可见时间、退出合并、统一标的和资源边界。
- [小内核、内部插件化与标准协议](kernel-20261012-protocol-plugins.md)：按 PLAN-065 修正基础能力归属。
  以 mini 与全部数据由用户准备为约束，复用 Exchange，直接注入自定义 Feed/Broker。
  默认模拟交易属于核心 `minbt.broker`，具体读取位于 `minbt.plugins`，协议集中，使用“策略类 + 配置”便捷入口。
  不保留历史导入转发。细则见 [协议目录](protocols/README.md)，规模与验收见 [实施结果](../dev/PLAN-065-core-broker-no-compatibility-OUTCOME.md)。
  本稿优先于旧接口重构中删除 `on_bar`、隐藏读取模式等冲突方向；旧金融模型的有效契约继续保留。

## 当前有效设计

- `minbt-20260921-api-refactor.md`：历史接口重构目标设计；其中删除回调、引入 `price_key`、隐藏读取模式的安排不是本轮实施内容，现有用户接口以最新小内核设计和代码为准。
- `minbt-20260630-system-design.md`：账户、Strategy、Order、Portfolio、Position、Market、退出条件和限价单边界；其中 Exchange 数据回放部分以本索引下的新稿为准。
- `broker-market-routing-20260701-design.md`：Strategy-Broker 关系和 broker 内多市场路由设计稿，明确保留 `Strategy(..., broker=broker)` 主路径，并通过 `broker.add_market(...)` 支持跨市场规则。
- `data-feed-20260701-design.md`：历史数据接入背景稿；当前自备数据契约以 protocols/data 规范为准。
- `exchange-20260921-replay-modes.md`：Exchange 实现背景；通用 `Bar.kind`、TimeBatch 和读取模式继续保留，同一 dt 收齐、批量账户更新和异常路径释放资源的正确性要求继续有效。
- `pnl-20261011-library-api.md`：库级账户、分仓、标的与订单盈亏查询，明确平均成本、手续费、强平、穿仓和已关闭分仓统计契约。
- `pnl-20260920-examples.md`：多空与手续费场景的库级接口示例、权益历史绘图和测试分工。
- [Exchange 单次运行与控制回调设计](run-20261012-control.md)：当前已实施的运行生命周期与结果契约。保留实例注册，一个 Exchange 只启动一次；通过 `run(control=...)` 统一继续、暂停和中途退出。暂停期间行情、账户与曲线持续推进，退出返回已处理区间的快照及状态元信息。未来 live 的实际接入与等待轮询尚未实现。
- [Skill 随安装包发布设计](skills-20261012-packaging.md)：已实施。用户 skill 与当前安装的 minbt 代码一起发布，通过 `python -m minbt.skills` 定位版本与资源，参考资料和最小脚本均在包内；仓库发现入口使用相对链接。

## 已合并删除的旧设计

- `DESIGN-001-broker-account-market-api.md`：已合并进当前系统设计。
- `DESIGN-002-data-feeds-and-callbacks.md`：已合并进当前系统设计。
- `broker-20260629-interface.md`：已合并进当前系统设计，并修正 `Trade` 为用户侧 `Order`。

## 当前总原则

minbt 的目标是最简、方便、快捷的回测系统，不做大而全交易所模拟。

稳定用户模型：

```python
class MyStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        target = 0.8 if price > 100 else 0.0
        self.broker.order_target_percent("BTCUSDT", target)
```

核心边界：

- Exchange 负责按时间提供同类数据切片。
- Strategy 负责产生交易意图。
- Broker 是唯一交易入口。
- Order 是用户修改订单关联退出条件的句柄。
- Portfolio 和 Position 负责账户状态。
- Market 负责市场规则差异。

## 当前文档结论

1. 用户回调使用 `on_bars/on_books/on_trades/on_bar/on_news`，生命周期和历史查询直接服务当前运行。
2. Exchange 继续使用 `set_bars/set_books/set_trades/set_news/add_feed`；新增薄 run 不替换原入口。
3. 用户交易统一通过 `self.broker`。
4. 所有下单类接口统一返回 `Order`，无交易用 `status="skipped"`，业务失败用 `status="rejected"`。
5. 市场差异通过 `Market(...)` 特征和 `markets.*` 预设表达，不推荐市场子类。
6. 分仓入口是 `broker.add_portfolio(name, cash)`，用户参数是 `portfolio="..."`。
7. 同一净持仓生命周期只有一份有效退出配置，当前 `Order.id` 作为访问句柄，修改按字段合并。
8. 标准止盈止损命名为 `stop_loss_price/take_profit_price`，移动止损命名为 `trailing_stop_pct/trailing_stop_amount`。
9. 函数型退出条件使用独立高级接口，不混进标准止盈止损参数。
10. 限价单、撤单和最小 pending limit order 已实现；不模拟队列位置、部分成交和 intrabar 路径。
11. 当前实现仍以 `set_bars/on_bars` 为主路径，同时已定义并实现 `set_books/set_trades/set_news` 的同一时间截面契约。
12. 跨市场能力优先通过单 broker 内的 `symbol -> Market` 路由设计，不把一个策略多个 broker 作为主路径。
13. 数据由用户准备，通过 `exchange.add_feed(feed)` 或 `feed_factory=` 接入；`set_bars(...)` 继续服务用户已有数据的最短路径。
14. 当前估值由 Broker 的 `mark_price` 指定，默认 `kline.close`；Feed 优先级不代替价格选择，来源歧义按当前规则失败。
15. Exchange 的执行入口为单次 `run(start=None, end=None, control=None, load_mode="auto")`，返回独立结果；读取模式保留，运行控制以 `run-20261012-control.md` 为准，配置与输出边界见最新协议规范。

## 阅读顺序

1. 先读最新小内核设计与协议目录，确认已经实施的接口和扩展边界。
2. 再读 `minbt-20260630-system-design.md` 的 Broker、Order、Portfolio、Market 和退出条件章节。
3. 再读 `broker-market-routing-20260701-design.md`，确认 Strategy-Broker 和多市场边界。
4. 需要理解当前代码来源时，再读 DataFeed、Exchange 和接口重构历史设计；冲突处以最新小内核设计为准。
