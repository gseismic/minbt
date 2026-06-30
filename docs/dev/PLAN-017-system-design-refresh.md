# PLAN-017 系统设计文档收敛

## 背景

`docs/design` 中同时存在多个 Broker、Market、Exchange 设计稿，命名不一致，部分内容已经过期。最新讨论已经明确：

- minbt 目标是最简、方便、快捷的回测系统。
- 用户真实场景是在策略中调用 `broker` 完成交易。
- 用户回调主路径是 `on_bars(dt, bars)`。
- Broker 退出条件应绑定用户侧 `Order`，不是 `Trade`。
- 市场差异应通过 `Market(...)` 特征和 `markets.*` 预设表达。

## 目标

1. 合并 `docs/design` 中过期和分散的设计稿。
2. 使用 AGENTS 规定的新命名：`{topic}-{date}-{tag}.md`。
3. 给出完整系统设计，覆盖用户接口、内部接口、当前实现状态和迁移顺序。
4. 删除或替代不合适的旧设计文档。
5. 保持设计围绕最简回测系统，不扩展为大而全交易所模拟器。

## 范围

本计划只修改文档，不修改代码。

## 预期产物

1. `docs/design/minbt-20260630-system-design.md`
2. 更新后的 `docs/design/README.md`
3. 删除旧设计稿：
   - `docs/design/DESIGN-001-broker-account-market-api.md`
   - `docs/design/DESIGN-002-data-feeds-and-callbacks.md`
   - `docs/design/broker-20260629-interface.md`
