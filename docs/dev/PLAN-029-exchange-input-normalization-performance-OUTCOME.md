# PLAN-029 Exchange 输入归一化性能优化结果

## 结论

已完成 10 万行级别输入归一化优化。

用户接口保持不变：

1. `list[dict]`
2. `pandas.DataFrame`
3. `polars.DataFrame`

内部仍统一编译为 Exchange 事件结构，不把 pandas/polars 暴露给策略或 broker。

## 代码变更

1. `minbt/exchange.py`
   - pandas 输入从 `DataFrame.iterrows()` 改为 `DataFrame.to_dict("records")`。
   - pandas-like 对象如果支持 `to_dict("records")`，优先使用该路径。
   - 保留 `iterrows()` 作为非常规 fallback，避免破坏非标准 dataframe-like 对象。
   - `list[dict]` 和 polars 输入行为保持不变。

2. `tests/test_exchange.py`
   - 新增 pandas、polars、`list[dict]` 输入一致性测试。
   - 新增 pandas-like 对象不调用 `iterrows()` 的测试。
   - 新增 `list[dict]` 输入复制测试，确认 `set_bars()` 后外部修改不会污染内部 feed。

## 性能结果

本地 10 万行基准，执行 `Exchange.set_bars()`：

优化前：

```text
list   : 0.1797s
pandas : 5.5008s
polars : 0.3669s
```

优化后：

```text
list   : 0.3530s
pandas : 0.4486s
polars : 0.4043s
```

不同基准数据分布会影响排序成本，但核心结论不变：pandas 输入不再受 `iterrows()` 慢路径拖累，已和 list/polars 进入同一量级。

## 验证

已执行：

```bash
python -m pytest -q tests/test_exchange.py
python -m pytest -q
git diff --check
```

结果：

- `tests/test_exchange.py`: 16 passed。
- 全量测试：123 passed。
- `git diff --check`: 通过。

## 设计判断

本次没有把 polars 设为内部默认运行格式，原因：

1. minbt 的主路径是事件驱动策略回调，最终仍要给策略 Python dict payload。
2. 10 万行数据通过一次性归一化和 Python 分组已经足够快。
3. 把 polars 引入运行期内部模型会增加实现复杂度，但对当前目标收益有限。

当前设计仍是：

```text
多格式用户输入
    -> 一次性归一化
    -> 统一事件结构
    -> run() 遍历事件并回调策略
```

这更符合 minbt “最简、方便、快捷回测系统”的目标。
