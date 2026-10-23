# minbt 最小协议设计规范

状态：协议已实施；核心与插件边界按 PLAN-065 修正，最新验收见 [实施结果](../../dev/PLAN-065-core-broker-no-compatibility-OUTCOME.md)。总设计见 [小内核与自定义数据](../kernel-20261012-protocol-plugins.md)。

本目录集中说明契约，类型定义位于 `minbt/protocols/`。协议声明与现有执行实现分开。

| 规范 | 最小边界 |
| --- | --- |
| [运行引擎](engine-20261012-contract.md) | 运行策略、返回标准结果；默认复用 Exchange |
| [配置入口](run-20261012-contract.md) | 参数文件与用户提供的 Feed/Broker 工厂 |
| [自定义数据](data-20261012-contract.md) | 保留 name/events，集中时间、排序和资源约定 |
| [Broker 扩展](trading-20261012-contract.md) | 原交易接口、回放推进和现有状态查询 |
| [策略共用接口](../live-trading-20261023-design.md#3-先定义最小协议) | TradingBrokerProtocol 与 StrategyExchangeProtocol；不统一成交和运行结果 |
| [结果读取](result-20261012-contract.md) | 现有 RunResult 查询，足够支持权益/盈亏绘图 |

共同约定：

- 所有数据由用户准备，核心不下载、识别市场、推断数据含义或选择数据服务。
- 协议只依赖标准库；数据形状集中声明，Bar/News/TimeBatch 构造仍在原实现路径，避免重复解析。
- 默认 Exchange 只有一套回放主循环；默认 Broker/账户/撮合属于核心，具体读取与特殊市场行为属于扩展。
- 直接引用正式模块与协议，不保留旧数据入口、模块别名或兼容转发。
- 只给实际跨模块边界定义协议，不给每个辅助函数、日志或配置步骤定义接口。
- 不需要全局注册表、市场包工厂、Router、命令总线或结果记录框架才能扩展。
- 不支持的结果能力保持明确异常；有效空结果与没有能力不能混淆。
- 执行语义、资源关闭和错误传播沿用当前正确性要求，不能为减行数删掉必要保证。
- 用户模块可直接提供实现，不要求写入已安装的 minbt 包目录。

薄 run 和声明直接服务核心与扩展；默认回测不导入 plugins，未新增依赖或预设外部引擎适配器。
