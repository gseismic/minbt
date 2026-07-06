# PLAN-037 DataFeed 实施结果

## 完成内容

1. 新增 `minbt.data` 包，提供 `FeedEvent`、`DataFeedProtocol` 和 `minbt.data.binance`。
2. 新增 `Exchange.add_feed(feed)`，第一阶段支持 replay-only feed，并在 `run()` 开始前物化进现有时间线。
3. 实现同一 `dt` 下按事件类型合并数据，支持 `bars/books/trades/news` 的基础合并规则。
4. 实现 `minbt.data.binance.BarsReplayFeed`，支持 Binance futures K 线自动下载、SQLite 缓存、coverage 复用和 `cache_only`。
5. Binance 下载优先使用 `crypto_api` 参考实现；没有 `crypto_api` 时回退到 Binance futures 公共 REST。
6. 默认只支持 `market="futures"`，传入其他 market 直接报错。
7. 新增 `examples/11_crypto_binance_feed.py`，展示加密货币 K 线自动下载、缓存和回测。
8. 更新 README，补充 `add_feed` 主路径和 Binance futures K 线自动下载示例。
9. 新增 `tests/test_data_feed.py`，覆盖 feed 驱动策略、重复 bar 冲突、价格冲突、Binance 缓存复用、futures market 限制和未收盘 K 线 coverage 语义。
10. 更新 API 契约测试，固定 `Exchange.add_feed(feed)` 签名。
11. Review 后修复 `set_xx(...)` 和 `add_feed(...)` 混用时 dt 类型不一致的问题，策略回调中的 dt 统一为 UTC `datetime.datetime`。
12. Review 后补充标准 feed row 校验，`bars` 缺少 `close`、`trades` 缺少 `price` 时直接报错。
13. Review 后修复 `cache_only=True` 的只读语义：缓存 DB 不存在时直接报错，不创建空 SQLite 文件。
14. Review 后把 `examples/11_crypto_binance_feed.py` 纳入无网络 fake feed 示例测试。
15. 修复旧示例中的错误日期构造和错误时间列使用，使示例在真实 datetime 语义下继续可运行。

## 验证结果

已通过：

```bash
python -m pytest
python -m compileall minbt examples tests
python examples/11_crypto_binance_feed.py
```

当前完整测试结果：

```text
145 passed
```

真实 Binance futures 小窗口验证已通过：

```text
events 3
cached_events 3
```

新增示例运行结果：

```text
final_equity=10458.09
final_cash=1992.00
final_position=0.188220
bar_count=48
```

## 未实现内容

1. 未实现 live feed。
2. 未支持 Binance spot。
3. 未实现公开 DataStore。
4. 未实现复杂行情修复或自动补 bar。
