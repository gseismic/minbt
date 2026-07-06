# PLAN-040 设计稿与代码同步修复

## 背景

系统 review 发现设计稿与代码之间存在 8 处差异（5 处代码侧、3 处文档侧）。本计划逐项修复，使设计稿与代码保持一致。

## 修复清单

### 代码修复

1. **BrokerProtocol 补全 get_active_order 声明**
   - 文件: `minbt/strategy.py`
   - 问题: 设计稿把 `get_active_order` 列为查询接口，但 `BrokerProtocol` 未声明
   - 修复: 在 `BROKER_PROTOCOL_METHODS` 和 `BrokerProtocol` 中补全 `get_active_order`

2. **删除 ExitRule.attached 死字段**
   - 文件: `minbt/broker/exit.py`
   - 问题: `attached: bool = False` 全代码库无引用
   - 修复: 删除该字段

3. **清理 binance.py 的 except ImportError 死分支**
   - 文件: `minbt/data/binance.py`
   - 问题: `_download_range` 的 `except ImportError` 永远不会触发（fetch_klines 内部已 catch）
   - 修复: 删除该 except 块，让真实错误自然传播

4. **将示例 _save_fig 抽取到 plot_utils.py**
   - 文件: 新建 `examples/plot_utils.py`，修改 11 个示例
   - 问题: 11 个示例各自重复定义 `_save_fig` 和 `_SCREENSHOT_DIR`
   - 修复: 创建共享 `save_figure(name)`，示例改为 `from plot_utils import save_figure`

### 文档修复

5. **主系统设计稿同步 Market.on_new_dt 签名**
   - 文件: `docs/design/minbt-20260630-system-design.md`
   - 问题: 设计稿写 `on_new_dt(broker, dt)`，代码实际是 `on_new_dt(broker, dt, symbols=None)`
   - 修复: 更新设计稿签名

6. **设计稿补充 normalize_order_qty 语义说明**
   - 文件: `docs/design/minbt-20260630-system-design.md`
   - 问题: 代码只归一化买入（qty>0），设计稿未说明
   - 修复: 补充说明

7. **设计稿更新 ExitContext 字段顺序**
   - 文件: `docs/design/minbt-20260630-system-design.md`
   - 问题: 设计稿字段顺序与代码不一致
   - 修复: 改为代码实际顺序（portfolio 在 dt 前）

8. **设计稿补记默认 market symbols 推导来源**
   - 文件: `docs/design/broker-market-routing-20260701-design.md`
   - 问题: 设计稿说"至少覆盖 positions 和 pending orders"，代码实际覆盖 4 个来源
   - 修复: 补记实际覆盖的来源

## 验证

- `python -m compileall -q minbt tests examples`
- `python -m pytest -q`
- `lsp_diagnostics` 检查修改的源文件
