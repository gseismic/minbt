# PLAN-036 DataFeed Binance 自动下载补充

## 背景

当前 `docs/design/data-feed-20260701-design.md` 已定义 `exchange.add_feed(feed)` 作为统一数据接入入口，但还缺少一块更贴近现有代码的描述：内置 Binance 历史数据如何通过下载器适配层自动拉取、落盘、复用。

参考代码位于 `binance.kline.dserver/kline_dserver/binance_client.py`，当前暴露了：

1. `list_symbols()`
2. `fetch_klines(...)`
3. `fetch_recent_klines(...)`
4. `fetch_raw_klines(...)`

## 目标

1. 把 Binance 自动下载的内部契约补进设计稿。
2. 明确哪些是用户接口，哪些只是内部下载适配层。
3. 保持最简回测系统定位，不把下载器膨胀成通用数据平台。

## 非目标

1. 不实现代码。
2. 不引入新的公开用户概念。
3. 不把实时 feed 拉进第一阶段。

## 计划

1. 更新 `docs/design/data-feed-20260701-design.md`，新增 Binance 下载适配层说明。
2. 同步必要时调整 `docs/design/README.md`。
3. 生成本次文档修订结果文件。

## 追加复查

用户要求再次检查刚才的设计改动后，需要重点确认：

1. 参考客户端实际使用 Binance futures API，设计默认值不能写成 spot。
2. 下载器内部参数不能污染用户主路径。
3. SQLite coverage 语义需要覆盖成功请求但返回空结果的情况。
4. Binance provider-specific 字段应可保留，但不能变成通用 bars feed 的必需字段。
