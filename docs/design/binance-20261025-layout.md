# Binance 插件职责与命名整理

日期：2026-10-25。
对应计划：[PLAN-076](../dev/PLAN-076-binance-layout.md)。

## 问题与目标

当前历史数据读取文件散放在 `binance/`，`live.py` 又同时实现 Broker 与 Exchange，包入口只导出
带 `Binance` 前缀的 Feed。调用方需要记住历史命名和特殊的 live 子模块，目录也无法直接体现职责。

以包名表达交易所，以类名表达能力；将历史 Feed、交易账户、实时行情分开。此次只调整组织和命名，
保持现有读取、缓存、时间、下单及资源生命周期契约。

## 用户场景与公开入口

| 频次 | 场景 | 入口 |
| --- | --- | --- |
| 高频 | 从 iosql 渐进读取历史 K 线 | `from minbt.plugins.binance.feed import KlineIosqlFeed` |
| 高频 | 从月度 CSV 读取历史 K 线 | `from minbt.plugins.binance.feed import KlineCsvFeed` |
| 常用 | 下载、缓存并回放历史 K 线 | `from minbt.plugins.binance.feed import KlineFeed` |
| 常用 | 注入历史数据到回测 | `minbt.Exchange.add_feed(feed)` |
| 较低 | 通过外部 SDK 接收实时 K 线 | `from minbt.plugins import binance; binance.Exchange(...)` |
| 较低 | 适配外部 SDK 账户 | `binance.Broker(sdk_broker)` |

历史与实盘均保持显式装配，实盘构造继续要求 `environment` 和 `sdk_factory`；不改变外部交易副作用。
`binance.Exchange` 仍只负责实时行情，回测继续使用 `minbt.Exchange`。

## 文件与依赖边界

```text
minbt/plugins/binance/
    __init__.py       # 仅导出实盘 Broker、Exchange
    broker.py         # SDK 账户薄适配
    exchange.py       # SDK 行情与策略回调生命周期
    _kline.py         # 时间、symbol 和 K 线字段的无状态转换
    feed/
        __init__.py   # 导出三个历史 Feed
        _base.py     # 历史行转 Bar、连续性检查和迭代清理
        cache.py     # KlineFeed 与内部 _KlineClient、HTTP/SQLite 辅助
        csv.py       # KlineCsvFeed
        iosql.py     # KlineIosqlFeed
```

`exchange.py` 单向引用 `broker.Broker`；Broker 通过已有的绑定引用检查所属 Exchange，保持现有状态契约。
Feed 依赖自己的 `_base.py` 与共享纯转换函数，Exchange 不依赖历史 Feed 的基类或缓存。
根包导入不加载历史 Feed、iosql 或外部交易 SDK；具体数据依赖仍在准备时按需导入。
沿用普通 Python 包和直接导入，不增加注册器、工厂框架或新的数据源接口。

## 命名与迁移

| 旧入口 | 新入口 |
| --- | --- |
| `binance.BinanceKlineFeed` | `binance.feed.KlineFeed`，从 feed 子包显式导入 |
| `binance.BinanceKlineCsvFeed` | `binance.feed.KlineCsvFeed` |
| `binance.BinanceKlineIosqlFeed` | `binance.feed.KlineIosqlFeed` |
| `binance.live.Broker` | `binance.Broker` |
| `binance.live.Exchange` | `binance.Exchange` |
| 内部 `cache.BinanceKlineClient` | 内部 `feed.cache._KlineClient` |

这是一次公开导入路径与类名调整，旧名和旧模块直接移除，仓库内调用方统一迁移，不建立兼容转发。
Feed 参数、默认来源名、缓存文件与 schema、K 线可见时间、通配符和分钟缺口语义保持现状。
已归档版本、旧计划结果和已失效迁移稿保留历史记录；有效入口文档与当前实盘设计同步更新。

## 验证边界

延续交接文件保留的“代码认可后再测试”偏好：本轮迁移既有测试引用，不新增或运行测试。
执行 Python 语法检查、ruff、旧入口残留检索和 diff 检查，人工审阅依赖方向、导出、绑定及资源归属。
既有回测/Feed 回归与 fake SDK 实盘验证留待代码认可后执行。
