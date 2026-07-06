# PLAN-041 二次 Review 修复

## 背景

二次 review 发现 P1×2 + P2×4 + P3×3 共 9 项问题。本计划逐项修复。

## 修复清单

### P1 应修复

1. **exit.py `state: Dict = None` 类型标注** → `Optional[Dict] = None`
2. **feed.py `prices: Mapping = None` 类型标注** → `Optional[Mapping] = None`
3. **get_orders 过滤 cancel_order 动作订单** → 避免用户看到重复 canceled 订单

### P2 建议修复

4. **补 exit.py 4 个工厂函数测试** → stop_loss_pct/take_profit_pct/stop_loss_price/take_profit_price
5. **补空头退出条件测试** → 止损/止盈/追踪的空头分支
6. **补 trailing_stop_amount 测试**
7. **示例 matplotlib 降级** → 顶层 try/except 提示安装

### P3 信息性

8. **宽泛 except Exception 改为具体类型** → exchange.py + market.py 共 3 处
9. **合并 test_portfolio.py / test_portfolio2.py** → 去重
10. **示例 06/07/08 补 sys.path 引导** → 与其他示例一致

## 验证

- `python -m compileall -q minbt tests examples`
- `python -m pytest -q`
- `lsp_diagnostics` 无新增错误
