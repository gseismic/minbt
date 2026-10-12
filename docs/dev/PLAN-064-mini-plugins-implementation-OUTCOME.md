# PLAN-064：mini 协议与内部插件化实施结果

- 日期：2026-10-12（Asia/Shanghai）。
- 状态：完成，代码与文档已在工作区，自行 review 和验收通过。
- 基准：`7ea1698`、minbt `0.1.1`，未修改版本或安装依赖。
- 对应计划：[PLAN-064](PLAN-064-mini-plugins-implementation.md)。
- 依据：[小内核设计](../design/kernel-20261012-protocol-plugins.md)、[协议规范](../design/protocols/README.md)。

此文件记录 PLAN-064 阶段结果。用户后续取消兼容要求、要求默认 Broker 属于核心，当前结构与清理见
[PLAN-065 结果](PLAN-065-core-broker-no-compatibility-OUTCOME.md)。

## 完成内容

1. `minbt.protocols` 集中数据、交易/回放、运行引擎和结果契约，只导入标准库与其他协议。原 DataFeedProtocol、BrokerProtocol、OrderSnapshot 导入仍指向同一对象；Bar/News/TimeBatch 构造继续复用原实现。
2. Binance 缓存/CSV/iosql/Kline、通用存储和模拟交易组件共 13 个模块迁入 `minbt.plugins.binance/storage/simulation`。旧模块通过模块别名指向唯一实现；旧路径上的猴子补丁仍作用于插件，不复制实现或创建转发类。
3. 新增 `run(策略类, JSON路径或Mapping, feed_factory=...)`：调用用户工厂、构造新策略和账户、使用原 Exchange。工厂支持列表或生成器，自定义账户用 broker_factory，broker=null 支持纯信号；不解释自备数据的字段、路径或市场。
4. 可显式注入 EngineProtocol 对象。核心只委托一次；适配器驱动策略、管理资源、返回独立 ResultProtocol。默认仍返回公共 RunResult，没有额外引擎实现、结果缓存或第二份账本。
5. 订单与累计盈亏快照接受符合标准字段的用户记录，无需继承 Order/Pnl。订单复制并冻结，Pnl 复制到原公共类型；缺能力、查询故障、字段缺失、非有限或口径矛盾继续明确失败。
6. 保留原公共构造参数、方法、回调、读取模式和控制语义。新增装配路径在工厂部分成功、预检失败、运行失败和正常结束时释放资源；关闭属性访问失败也继续清理，原异常优先。
7. 增加 [自备数据示例](../../examples/18_config_run.py) 与 [JSON 参数](../../examples/18_config_run.json)，输出 final_equity=1020.00、net_pnl=20.00，并从结果画权益和盈亏。README、随包使用指南、设计状态及索引同步。

## 代码规模与 mini 边界

统计 `minbt/**/*.py` 的物理行数，包含空行、注释、声明、包入口和原随包示例，不包含 tests、examples 或 Markdown。

| 口径 | 结果 |
| --- | --- |
| 整个包 | 29 文件 / 6295 行 → 52 文件 / 6694 行，净增 **399 行** |
| 搬迁的具体实现 | 13 模块 / 4643 行；除导入路径外 AST 完全一致 |
| plugins 目录 | 4678 行，主要为搬迁代码和包导出 |
| 旧路径兼容别名 | 13 文件 / 78 行，均指向插件模块 |
| 新协议目录 | 5 文件 / 240 行，包含迁入的协议与 OrderSnapshot |
| 新配置入口 | run.py / 115 行，直接调用原 Exchange |
| 原执行模块 Exchange、Strategy、RunResult | 1196 → 1140 行，净减 56 行，主要为声明集中 |
| 上述执行模块加协议和新入口 | 1196 → 1495 行，净增 **299 行** |

搬迁不是整个包的净减少，协议和装配仍有代码成本。本次核心增长限定为声明、薄装配和必要校验；
默认回放依然只有原 Exchange 的循环。没有新增依赖、数据 SDK、市场注册表、Router、命令总线、
独立结果记录框架或 save/load。数据由用户准备；新示例使用普通自备行，不引入 AShare 数据源或示例。
已有显式下载接口随具体插件保留兼容，默认运行入口不选择它或发起数据请求。

## 验证证据

| 检查 | 结果 |
| --- | --- |
| 修改前全量 | 334 passed |
| 协议/迁移/配置及原控制接口针对性检查 | 131 passed |
| 示例与 wheel/sdist/安装资源阶段检查 | 72 passed |
| 最终 `python -m pytest -q` | **385 passed in 40.84s**，较基准新增 51 项 |
| `ruff check minbt tests examples` | 通过 |
| Python 3.8 AST 与 compileall | 70 个运行源码/示例文件通过语法检查，编译通过 |
| 迁移等价与公共签名审计 | 13 模块除导入外 AST 相同；Exchange/Strategy/RunResult 公共参数相同；原 17 个示例源码未改 |
| 发行物 | 干净构建 wheel、sdist、sdist 重建 wheel，全部 Python 源码与 skill 内容逐文件一致 |
| 仓库外安装 | 两种 wheel 实际安装，旧/新类身份和协议导入可用，自备数据配置示例权益 1020、净盈亏 20 |
| 文档、差异检查 | 本轮本地链接、代码块、`git diff --check` 通过 |

行为覆盖包含 Mapping 副本隔离、JSON 同结果、每次独立对象、三种读取模式、时间窗口、pause/exit、
纯信号、自定义无继承记录、错误资源关闭、外部引擎唯一委托和可选查询语义。

自行 review 修复了显式 falsey 工厂被忽略的风险、关闭属性访问跳过后续清理、工厂生成器类型声明不匹配，
以及不可调用的 process_market_batch 延迟到运行后才失败的问题。相关行为均已纳入回归。

## 实际适用边界

- 自定义 Feed 在默认 Exchange 下仍产出原 Bar/News；结构协议用于声明形状，不隐式转换任意记录。
- 用户工厂每次创建新资源。带连接或特殊构造的对象通过代码工厂或原手工装配注入，不序列化活对象。
- 外部引擎 SDK 与策略桥接由真实适配器实现，本次固定输入/输出协议，不宣称已接入所有引擎。
- 自定义 Broker 对隔离和只读控制的支持沿用现有边界；协议本身不能阻止绕过入口修改内部状态。
- Python 3.8 进行了语法检查，未在 Python 3.8 解释器中运行全套测试。

未提交、推送或发布；本次交付为可直接审查的工作区改动。
