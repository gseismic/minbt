# PLAN-076：Binance 插件职责与命名整理结果

日期：2026-10-25。
对应计划：[PLAN-076](PLAN-076-binance-layout.md)。
设计：[Binance 插件职责与命名整理](../design/binance-20261025-layout.md)。

## 完成内容

- 历史读取器统一归入 `minbt.plugins.binance.feed`，公开 `KlineFeed`、`KlineCsvFeed`、`KlineIosqlFeed`。
- 原 live.py 拆为 broker.py 与 exchange.py，根包只导出实盘 `Broker` 和 `Exchange`。
- 时间、symbol 和字段纯转换归入内部 `_kline.py`；历史行转 Bar、分钟连续性与迭代清理归入 `feed/_base.py`。
- 内部下载客户端重命名为 `_KlineClient`；旧 Feed 名称、根目录读取模块与 live 模块直接移除。
- 同步 5 个示例、5 个既有测试文件、README、随包使用指南及相关有效设计和索引。
- 保持参数、来源名、缓存文件/schema、close_time 可见时间、通配符、分钟缺口、SDK 下单绑定与清理逻辑。

## 源码审阅与验证

- 与重构前基线 `ef238fc` 静态比对原 cache/csv/iosql/kline/live 中全部 25 个顶层类和函数定义，包含类内方法；
  归一化重命名和一处错误提示后，AST 一致。模块常量与辅助字段映射随源码原样迁移并人工审阅。
- 9 个插件模块的 21 处相对导入逐项静态解析，目标模块与导入符号均存在；Exchange 不引用历史 Feed。
- 19 个变更 Python 文件均通过语法编译与 Python 3.8 AST 解析；未通过导入执行项目代码。
- `uv run --no-project ruff check minbt/plugins/binance examples/13_binance_feed.py examples/14_csv_feed.py examples/15_iosql_feed.py examples/19_live.py examples/20_iosql_all_symbols.py tests/test_api_contract.py tests/test_binance_continuity.py tests/test_binance_feed.py tests/test_data_feed.py tests/test_examples.py`：通过。
- 静态检查发现并修复一处缓存测试 monkeypatch 的旧模块别名；生产代码、示例及随包指南无旧入口残留。
  旧设计中的历史命名保留，并补充当前命名规范链接；迁移表明确记录旧入口。
- `git diff --check`：通过；新增文件一并检查末尾换行与行尾空白。
  提交前对暂存区再次检查，修正拆分后 _base.py 的多余末尾空行。

## 迁移与验证边界

这是导入路径和类名的公开调整：历史读取器改从 `minbt.plugins.binance.feed` 导入，
`binance.live.Exchange/Broker` 改为 `binance.Exchange/Broker`；不保留兼容别名。

延续交接文件的“代码认可后再测试”偏好，本轮只迁移既有测试引用，没有新增或运行测试、示例或 SDK 行情，
没有连接账户或下单。运行时的历史 Feed/回测回归与 fake SDK 行为验证仍待代码认可后执行，
静态检查不能替代这些验证。本轮未修改核心回测或相邻 SDK。

用户随后明确要求提交，本结果与计划、设计、代码和示例一并纳入本地提交；不执行推送。
