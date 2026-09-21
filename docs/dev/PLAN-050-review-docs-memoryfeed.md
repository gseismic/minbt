# PLAN-050 评审反馈：文档引导与 MemoryFeed 清理

## 目标

处理评审指出的四个小问题：

1. 修正 README 中 `BinanceKlineFeed` 示例的缩进。
2. 在 README 的通用 Bar 小节说明 `on_bar(dt, bar)` 按事件逐条调用，不聚合成截面。
3. 删除 `MemoryFeed.__init__` 中与类属性重复的实例赋值。
4. 明确 `mark_price="kind.field"` 是推荐形式，元组、callable 和关闭估值属于高级用法；
   三元组会耦合 Feed 名称，需谨慎使用。

## 范围

- README、当前 Exchange 设计稿和 minbt 使用技能。
- `minbt/data/feed.py`。
- 不改变 Broker 估值行为、Exchange 分发行为或公开参数签名。

## 验收

- 文档示例可直接复制，缩进正确。
- `on_bar` 的逐事件语义和 `mark_price` 分层在主文档中可见。
- 全量测试、静态检查和编译检查通过。
