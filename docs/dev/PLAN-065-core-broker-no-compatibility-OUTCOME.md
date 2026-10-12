# PLAN-065：默认 Broker 归回核心与兼容层清理结果

- 日期：2026-10-12（Asia/Shanghai）。
- 状态：完成，工作区改动已 review 和验证。
- 对应计划：[PLAN-065](PLAN-065-core-broker-no-compatibility.md)。
- 当前设计：[小内核与扩展边界](../design/kernel-20261012-protocol-plugins.md)。

## 边界修正

默认模拟账户、订单、分仓、持仓、盈亏、撮合和退出是基础回测能力，唯一实现直接位于
`minbt.broker`。可替换性由 BrokerProtocol/ReplayBrokerProtocol 和工厂表达，不要求默认实现归入插件。
plugins 承载数据格式/来源读取以及未来特殊市场扩展；默认核心不反向依赖这些模块。

## 完成改动

1. 把 simulation 的 8 个实现模块移回 broker，移除 simulation 包。`git diff -- minbt/broker` 为空，默认金融实现与 `7ea1698` 基准完全相同，未新增或重写模拟算法。
2. 清理上一轮全部 13 个 sys.modules 别名；8 个 Broker 文件恢复真实实现，删除 data 下的 binance/csv/iosql/kline/bar_feed 转发文件。不存在重复类或废弃入口空壳。
3. data 只导出 Bar/News/SimpleFeed/MemoryFeed；DataFeedProtocol 从 protocols 使用。根包 OrderSnapshot 直接引用协议定义，result 不再额外声明兼容导出。
4. 数据读取示例、测试、README 和随包参考资料直接导入 `minbt.plugins.binance` 或 `minbt.plugins.storage`，当前设计停止承诺旧读取路径。协议测试从正式协议位置导入。
5. 删除旧模块身份兼容测试，新增全新 Python 进程中的默认自备数据回测：权益 1020、净盈亏 20，且从导入到结果完成均未加载任何 minbt.plugins 模块。
6. 更新安装包回归，在仓库外分别安装 wheel 和 sdist 重建 wheel，先运行纯核心配置示例，再导入具体读取插件，验证核心和扩展的正式归属。
7. 当前总设计、协议细则、索引、使用指南同步；PLAN-064 结果保留为阶段记录，并指向本轮最新结果。

普通用户仍可通过 `from minbt import Broker, Exchange, Strategy, run` 使用核心。扩展按唯一入口
引用，无需迁移兼容阶段。自备数据、配置、外部引擎协议和独立结果查询行为继续正确。

## 代码规模

统计包内 Python 源码物理行数，包含空行、注释、声明与随包脚本，不含测试/仓库示例/Markdown。

| 口径 | 结果 |
| --- | --- |
| 清理前 PLAN-064 | 52 文件、6694 行 |
| 当前包 | 38 文件、6585 行 |
| 本轮减少 | 14 个文件、109 行 |
| 与原始 0.1.1 基准比较 | 29 文件、6295 行 → 38 文件、6585 行，净增 290 行 |
| core broker 目录 | 3115 行，包含原包入口，与仓库基准无差异 |
| plugins 目录 | 1563 行，仅现有读取插件和包入口 |

默认账户归回核心是职责纠正，不是新增算法。不能通过移动基础能力来制造核心变小的统计。
协议仍为 240 行、薄 run 仍为 115 行；没有增加依赖、数据 SDK、注册表、回放循环或结果存储框架。

## 验证

- 针对性交易、协议/插件、配置、数据、控制与 API 测试：201 passed。
- 最终 `python -m pytest -q`：**373 passed in 68.73s**，包括所有金融行为、示例与发行物/仓库外安装验证。
- 前一阶段 385 项 → 删除 13 项模块别名兼容测试、增加 1 项默认回测独立于插件测试 → 373 项；金融测试没有删减。
- `ruff check minbt tests examples`、`compileall`、56 个运行源码/示例文件的 Python 3.8 AST 语法检查通过。
- README 的 MemoryFeed 配置片段按当前正式导入实际执行，最终权益 1020、净盈亏 20。
- 扫描包源码无 sys.modules 模块别名、无 simulation、无 5 个旧读取文件；当前资料无失效插件/旧数据导入。
- 本轮文档代码块、本地链接及 `git diff --check` 通过。Python 3.8 做了语法检查，未在 3.8 解释器中运行全套测试。

本次只清理历史 API 转发，Python 支持版本与缺少可选存储依赖时的正常运行能力继续保留。
用户数据准备职责不变，默认回测不会获取外部行情。

按用户要求，与 PLAN-063/064/065 的设计、计划和结果文档一并提交；未推送或发布。
