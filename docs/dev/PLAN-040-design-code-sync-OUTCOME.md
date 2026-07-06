# PLAN-040 设计稿与代码同步修复 — 结果

## 概述

系统 review 发现设计稿与代码之间存在 8 处差异。本计划逐项修复，使设计稿与代码保持一致。全部修复完成，145 个测试通过。

## 执行摘要

- 代码修复 3 处：`strategy.py`、`exit.py`、`binance.py`
- 示例重构 1 处：新建 `examples/plot_utils.py` + 修改 11 个示例 + 修复示例 11 的 `sys.path`
- 设计文档更新 4 处：主系统设计稿 3 处 + 市场路由设计稿 1 处
- 验证：`compileall` 通过，`pytest` 145 passed，`lsp_diagnostics` 无新增错误

## 变更文件

### 代码修改

- `minbt/strategy.py`
  - `BROKER_PROTOCOL_METHODS` 补全 `get_active_order`
  - `BrokerProtocol` 补全 `get_active_order` 方法签名

- `minbt/broker/exit.py`
  - 删除 `ExitRule.attached` 死字段（全代码库无引用）

- `minbt/data/binance.py`
  - 删除 `_download_range` 中的 `except ImportError` 死分支（`fetch_klines` 内部已 catch 并回退 HTTP，该 except 永远不触发）

### 示例重构

- `examples/plot_utils.py`（新建）
  - 共享 `save_figure(name)` 函数，替代 11 个示例中各自重复的 `_save_fig`

- `examples/01_demo_mini.py` ~ `examples/11_crypto_binance_feed.py`（11 个文件）
  - 删除重复的 `_SCREENSHOT_DIR` 和 `_save_fig` 定义
  - 添加 `from plot_utils import save_figure` 导入
  - 所有 `_save_fig(` 调用替换为 `save_figure(`

- `examples/11_crypto_binance_feed.py`（追加修复）
  - 补充 `examples/` 目录到 `sys.path`，修复 `importlib.util.spec_from_file_location` 直接导入时 `plot_utils` 找不到的问题

### 文档更新

- `docs/design/minbt-20260630-system-design.md`
  - `Market.on_new_dt` 签名同步为 `on_new_dt(broker, dt, symbols: list[str] | None = None)`
  - 补充 `normalize_order_qty` 数量归一化语义说明（只归一化买入，卖出和空头回补不归一化）
  - `ExitContext` 字段顺序更新为代码实际顺序（`portfolio` 在 `dt` 前，归属信息相邻）

- `docs/design/broker-market-routing-20260701-design.md`
  - 默认 market symbols 推导来源补记：代码已覆盖全部 4 个来源（`last_prices`、`last_price_dates`、`orders` 含 pending、`positions`）

## 验证结果

```bash
python -m compileall -q minbt tests examples
# 通过，无输出

python -m pytest -q
# 145 passed in 56.43s
```

`lsp_diagnostics` 检查 `minbt/` 目录：59 个错误全部为预先存在的 Pyright 类型标注问题（`reportGeneralTypeIssues`、`reportOptionalMemberAccess` 等），本次修改未引入任何新错误。

## 修复对照

| # | 修复项 | 类型 | 严重度 | 状态 |
|---|---|---|---|---|
| 1 | BrokerProtocol 补全 get_active_order | 代码 | P1 | ✅ |
| 2 | 删除 ExitRule.attached 死字段 | 代码 | P2 | ✅ |
| 3 | 清理 binance.py except ImportError 死分支 | 代码 | P2 | ✅ |
| 4 | 示例 _save_fig 抽取到 plot_utils.py | 代码 | P2 | ✅ |
| 5 | 设计稿同步 Market.on_new_dt 签名 | 文档 | P1 | ✅ |
| 6 | 设计稿补充 normalize_order_qty 语义 | 文档 | P3 | ✅ |
| 7 | 设计稿更新 ExitContext 字段顺序 | 文档 | P3 | ✅ |
| 8 | 设计稿补记 market symbols 推导来源 | 文档 | P3 | ✅ |
