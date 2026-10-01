# 全量代码 Review 报告·第七轮（2026-10-02）

## 范围与方法

- **审查范围**：当前工作区 `minbt/` 下的运行时代码，包含 Broker、Portfolio、Market、Exchange、Strategy、通用 Bar 与 Kline 数据 Feed、Binance 缓存、数据模型及辅助模块。
- **排除范围**：`examples/` 按用户要求不审查；该目录正由其他 Agent 处理。
- **基线**：`HEAD=4b8137d`。审查时工作区另有未提交的示例重命名和文档改动；本报告未修改这些文件。
- **方法**：逐模块静态阅读并对照已有设计与历史 Review。没有运行测试或修改运行时代码。

## 结论摘要

核心结构整体清晰，时间批次先聚合再更新组合、CSV/iosql 的缺数据预检、退出状态按净持仓维护等设计已经覆盖了不少常见边界。本轮仍发现若干会改变成交、强平或数据范围的逻辑问题：

| 级别 | 数量 | 概述 |
| --- | ---: | --- |
| P1 应优先修复 | 1 | 隔离保证金批量检查在首个强平仓位后提前返回 |
| P2 建议修复 | 10 | Binance `closed_only` 绕过缓存过滤、空下载被记为完整覆盖、Feed 名称覆盖、A 股时区、交易单位校验、持仓字典泄漏、CSV 乱序截断、挂单使用旧价格、Kline CSV 月份推断过严，以及 tick 倍数容差误拒合法价格 |
| 需明确语义 | 1 | 新订单附带部分退出条件会整体替换原退出配置 |
| P3 边界项 | 2 | 数字时间戳单位启发式、`Portfolio.get_position()` 查询时创建空仓 |

上一轮报告和 PLAN-043 中提到的 tick 浮点容差、`get_positions()` 可变字典以及 A 股时区问题在当前源码中仍存在。

## P1 应优先修复

### R7-P1-1 隔离保证金批量更新遇到首个强平仓位就停止

- **位置**：[minbt/broker/portfolio.py:161](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/portfolio.py:161)
- **问题**：隔离保证金分支逐个检查持仓，但第一个穿仓或触发强平后立即 `return`。此前虽然已批量更新所有持仓价格，后续仓位却不会在这个时间批次接受风险检查。
- **影响**：同一个时间批次内多个仓位都达到强平条件时，只有迭代顺序中的第一个仓位会被处理。其余仓位可能继续以低于强平线的权益保留到下一条市场事件；如果回测刚好结束，就不会再被处理。最终组合状态依赖 `_positions` 的顺序及之后是否还有其他事件。
- **建议**：继续检查该组合的全部隔离仓位，汇总本批次的破产/强平结果后再返回。

## P2 建议修复

### R7-P2-1 `closed_only=True` 没有过滤已缓存的未收盘 K 线

- **位置**：[minbt/data/binance.py:314](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/binance.py:314)、[minbt/data/binance.py:410](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/binance.py:410)
- **问题**：`closed_only` 只在新下载时用于筛行；`_load_rows()` 从 SQLite 读取数据时没有按收盘状态过滤。
- **触发方式**：先用 `closed_only=False` 把当前未收盘 K 线写入完整 coverage，再用相同缓存和区间创建 `closed_only=True` 的 Feed。此时 coverage 已完整，不会重新下载；未收盘行仍会被 `_load_rows()` 返回。新下载行若没有 `close_time`，第 318 行也会把它当作已收盘行保留。
- **影响**：`closed_only=True` 的回测可能消费未完成 K 线，结果依赖缓存是由哪个配置先生成的。
- **建议**：在读取结果阶段也落实 `closed_only`，并明确处理缺少 `close_time` 的行。

### R7-P2-2 Binance 空或不完整响应会被登记为完整覆盖

- **位置**：[minbt/data/binance.py:298](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/binance.py:298)、[minbt/data/binance.py:314](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/binance.py:314)、[minbt/data/binance.py:167](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/binance.py:167)
- **问题**：`_download_range()` 对 API 返回的行做区间过滤后，无论行数为零、是否覆盖完整区间，都会把整个请求区间写入 coverage（`closed_only=True` 时写到当前开盘时间）。`prepare()` 之后也没有核对每个请求 symbol 是否实际加载到数据。
- **影响**：API 暂时返回空/截断数据时，Feed 可正常结束并产生空回测或缺失 symbol；后续普通运行及 `cache_only=True` 会把该范围视为已覆盖，不会自动补取。
- **建议**：区分“已请求”和“已确认完整”的区间；校验响应连续性，并对显式请求但没有行的 symbol 给出明确错误或可见状态。

### R7-P2-3 `set_*()` 可能静默覆盖同名自定义 Feed

- **位置**：[minbt/exchange.py:628](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/exchange.py:628)
- **问题**：`add_feed()` 允许用户注册名为 `bars`、`books`、`trades` 或 `news` 的 Feed；之后调用相应 `set_*()` 时，`_replace_source()` 直接按名称写入 `_sources`，没有识别并拒绝覆盖自定义 Feed。
- **影响**：旧 Feed 被无提示移除，回测会漏掉该来源的数据。反向顺序则由 `add_feed()` 因重名而报错，行为不对称。
- **建议**：只允许 `set_*()` 替换同一入口先前创建的内存 Feed；如果名称已属于 `add_feed()` 来源，应报重名错误。

### R7-P2-4 A 股交易时段与 UTC 归一化后的时间不一致

- **位置**：[minbt/data/model.py:17](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/model.py:17)、[minbt/broker/market.py:78](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/market.py:78)、[minbt/broker/markets.py:8](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/markets.py:8)
- **问题**：`Bar` 将带时区时间归一化为 UTC；`Market.is_trading_time()` 随后直接拿 UTC 的 `value.time()` 与 A 股 `09:30–11:30`、`13:00–15:00` 比较。`Market` 没有市场时区配置。
- **触发方式**：有效的上海时间 `2026-01-05 09:35+08:00` 会变成 `01:35 UTC`，被 A 股市场拒绝；相同钟点的无时区输入按 UTC 解释后却会通过时段判断。
- **影响**：同一实际成交时刻仅因时间输入是否带时区而得到不同订单结果。
- **建议**：为 Market 明确交易时区，并在该时区解释交易时段与交易日；或者限制输入契约并在入口处一致校验。

### R7-P2-5 `Market` 未校验交易单位，非法 `lot_size` 可扩大订单

- **位置**：[minbt/broker/market.py:69](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/market.py:69)、[minbt/broker/market.py:109](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/market.py:109)
- **问题**：构造时只检查 `t_plus` 和交易时段，没有验证 `lot_size`、`tick_size`、`min_qty`、`min_notional` 为有限正数。
- **影响**：`lot_size=0` 会在目标仓位归一化时触发除零；`lot_size=-100` 时请求数量 `150` 会按 `floor(150 / -100) * -100` 归一化为 `200`，下单量高于用户目标。
- **建议**：Market 创建时拒绝非有限或非正交易单位；`None` 表示未配置，零值不要兼作关闭开关。

### R7-P2-6 tick 倍数容差会误拒高价小 tick 的合法价格

- **位置**：[minbt/broker/market.py:40](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/market.py:40)
- **问题**：`_is_multiple()` 对 `value / step` 的结果使用固定绝对容差 `1e-9`。比值很大时，浮点除法误差可能超过该容差。
- **影响**：例如 `60000.0` 配 `tick_size=0.00001`，比值约为 `6e9`，合法价格可能被判为不是 tick 的整数倍并拒单。该问题也见上一轮 Review，当前公式未变。
- **建议**：使用基于价格差及 step 尺度的安全容差，或用 Decimal/整数化比较；需确保容差不会放过真实的半 tick 偏差。

### R7-P2-7 `get_positions()` 返回内部字典，外部可直接改写 Broker 持仓

- **位置**：[minbt/broker/portfolio.py:372](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/portfolio.py:372)、[minbt/broker/broker.py:1552](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/broker.py:1552)
- **问题**：Portfolio getter 直接返回 `_positions`，Broker 将该对象原样透出。调用方可以对返回值增删 symbol，绕过下单和组合记账逻辑。
- **影响**：例如 `broker.get_positions().clear()` 会清空 Broker 的持仓索引，但现金、历史订单和其他内部状态仍保留，造成账户不一致。该项在上一轮 Review 中也已提出。
- **建议**：返回浅拷贝，避免调用方增删内部字典项；如果需保护 Position 对象本身，再提供只读快照。

### R7-P2-8 通用 CSV Feed 的 `end` 截断会掩盖文件乱序

- **位置**：[minbt/data/bar_feed.py:157](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/bar_feed.py:157)
- **问题**：Feed 声明 `ordered=True`，基类只对实际产出的行检查顺序；CSV 遇到第一条 `dt >= end` 就 `break`。若后续行又回到区间内，乱序检查看不到它。
- **触发示例**：文件时间顺序为 `00:00、00:10、00:05`，请求 `end=00:06`。Feed 在 `00:10` 处停止，静默遗漏 `00:05`，而不会报告乱序。
- **建议**：在提前停止前继续验证文件顺序，或明确要求并验证已排序输入后再使用 `break`。

### R7-P2-9 挂单会在其他标的的时间批次上使用旧价格成交

- **位置**：[minbt/broker/broker.py:559](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/broker.py:559)、[minbt/broker/broker.py:928](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/broker.py:928)
- **问题**：每个全局时间批次都会调用 `process_pending_orders()`；它对每张订单读取 `last_prices[order.symbol]`，没有确认当前批次是否更新了该 symbol 的市场价格。成交时间却使用当前批次的 `dt`。
- **影响**：A 标的的挂单可以在仅包含 B 标的或 News 的较新批次中，按 A 的旧价格条件成交，并把成交记录时间写成 B/News 的时间。订单结果因此受无关 Feed 的事件驱动。
- **建议**：明确挂单是否仅能由同一 symbol 的新市场数据触发；若是，应把本批次更新的 symbol 集合传入成交检查，并避免把旧报价标成新时间。

### R7-P2-10 Kline CSV 缺月检查把不同上市历史的 symbol 当成相同覆盖区间

- **位置**：[minbt/data/csv.py:177](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/csv.py:177)
- **问题**：未指定 `start/end` 时，代码用所有文件的最早月份和最晚月份作为统一区间，并要求每个 symbol 在其中每个月都有文件。
- **触发方式**：BTC 文件从 2023-01 开始，ETH 文件从 2023-03 开始；未传 `start` 时仍会要求 ETH 提供 2023-01 和 2023-02 文件，并报缺月。
- **影响**：有效的多标的历史数据只要各标的上市时间不同，就可能无法读取。对没有显式时间边界的请求，缺文件不一定代表数据丢失。
- **建议**：无显式边界时按 symbol 各自文件跨度推断范围；有显式边界时再对用户请求的公共区间执行完整性检查，或让调用方显式选择严格模式。

## 需明确语义

### R7-S1 新成交附带部分退出条件会停用旧配置的其他条件

- **位置**：[minbt/broker/broker.py:378](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/broker.py:378)、[minbt/broker/broker.py:388](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/broker.py:388)、[minbt/broker/broker.py:425](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/broker.py:425)
- **行为**：持仓已有 `take_profit_price` 时，同方向新订单仅提供 `stop_loss_price`，新状态成为唯一 active exit，旧状态停用；新状态没有止盈价，因此原止盈也失效。
- **评估**：当前设计允许同一净持仓只保留一个有效退出订单，因此“整体替换”可能是预期语义；但可选参数也容易被理解为只覆盖已传字段。现有文档和测试没有明确覆盖这个“部分参数是否继承”的情形。
- **建议**：明确是完整替换还是按字段合并。若完整替换，应说明新订单必须重复传入仍需保留的退出项；若字段合并，则在激活新状态时继承旧状态中未提供的字段。

## P3 边界项

### R7-P3-1 数字时间戳单位按数量级推断，1973 年前的毫秒值会被当成秒

- **位置**：[minbt/data/model.py:24](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/data/model.py:24)
- **问题**：小于 `1e11` 的数字统一按秒解释。因此表示 1973-03-03 之前时间点的 Unix 毫秒值会产生错误日期。常见现代行情时间戳不受影响，但这是启发式的时间输入边界。
- **建议**：数字时间戳 API 显式要求单位，或在文档中写明推断范围。

### R7-P3-2 `Portfolio.get_position()` 默认创建空仓记录

- **位置**：[minbt/broker/portfolio.py:359](/home/lsl/macbook/pai-studio-fin/library/minbt/minbt/broker/portfolio.py:359)
- **问题**：查询不存在的 symbol 默认向 `_positions` 插入空 `Position`。Broker 的公开查询已传 `create_if_missing=False`，但直接使用 Portfolio 或调用其关闭空仓方法仍会改变内部结构。
- **影响**：空仓记录会留在 `positions` 中，并参与后续遍历；目前多处逻辑会跳过空仓，影响主要是状态查询与额外开销。
- **建议**：查询默认不创建；需要初始化仓位时由成交路径显式创建。

## 保持项

- `Exchange` 会先收齐同一时间的 Bar，再由 Broker 批量更新价格；这避免了同一时间截面中跨标的处理顺序改变全仓估值。
- CSV/iosql Kline Feed 对缺失 symbol 和空查询已做启动前预检，错误路径更明确。
- `Strategy` 的历史查询已统一返回 list；pyta2 只影响内部存储。
- `close_portfolio()` 对平仓计划执行预检，并在成功关闭后清理该组合的 pending 订单。

## 建议处理顺序

1. 先修复隔离保证金的批量风险检查提前返回。
2. 修复 Binance `closed_only` 与 coverage 误判，避免读取未收盘 K 线和缓存静默标记空洞。
3. 修复 Feed 名称覆盖、Market 时间/交易单位校验、通用 CSV 截断和持仓字典泄漏。
4. 决定挂单跨标的时间批次的成交语义，以及新订单退出参数采用整体替换还是按字段合并。
5. 处理 tick 精度与多标的 CSV 文件跨度推断，并补齐对应回归覆盖。

## 验证记录

- 本轮仅静态审查，没有运行测试或修改运行时代码。
- 本报告只覆盖 `minbt/`；示例由其他 Agent 审查。
