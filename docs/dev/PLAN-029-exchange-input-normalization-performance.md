# PLAN-029 Exchange 输入归一化性能优化

## 背景

minbt 的用户接口应允许用户传入常见数据格式：

1. `list[dict]`
2. `pandas.DataFrame`
3. `polars.DataFrame`

但运行期不应把这些格式扩散到策略和 broker。Exchange 应在 `set_bars()` / `set_books()` / `set_trades()` / `set_news()` 阶段把输入一次性归一化并编译成统一的事件结构。

当前问题：

- pandas 路径使用 `DataFrame.iterrows()` 转换成 `list[dict]`。
- 10 万行本地基准下，pandas 输入约 5.5s，主要耗时来自 `iterrows()`。
- 使用 `DataFrame.to_dict("records")` 可把转换成本降到约 0.15s。

## 目标

1. 保持用户接口不变：继续支持 pandas、polars、`list[dict]`。
2. 内部继续统一编译成 `dt -> payload` 事件结构，不引入 polars 作为运行期心智模型。
3. 优化 pandas 输入路径，支持 10 万行级别数据快速载入。
4. 补充测试，防止后续回退到 `iterrows()` 慢路径。

## 实施方案

1. 修改 `Exchange._to_rows()`：
   - `list[dict]`：仍复制为新的 dict，避免外部修改影响内部状态。
   - `polars.DataFrame` 或 duck-typed `iter_rows`：继续使用 `iter_rows(named=True)`。
   - `pandas.DataFrame` 或 duck-typed `to_dict`：改用 `to_dict("records")`。
2. 保持 `_group_rows()` 当前结构：
   - 仍按 `(dt, symbol)` 排序。
   - bars/books 编译为 `OrderedDict[dt, OrderedDict[symbol, row]]`。
   - trades 编译为 `OrderedDict[dt, OrderedDict[symbol, list[row]]]`。
   - news 编译为 `OrderedDict[dt, list[row]]`。
3. 增加测试：
   - pandas-like 对象如果暴露 `to_dict("records")`，不应调用 `iterrows()`。
   - pandas、polars、`list[dict]` 输入在同一数据下产生一致回调结果。
   - `list[dict]` 输入应复制 row，避免 set_bars 后外部修改污染回测。

## 非目标

1. 不改用户接口。
2. 不把 polars 设为内部默认运行格式。
3. 不引入流式执行、缓存编译产物或列式内部结构。
4. 不做性能测试硬阈值断言，避免 CI 环境不稳定。

## 验证

1. `python -m pytest -q tests/test_exchange.py`
2. `python -m pytest -q`
3. `git diff --check`
