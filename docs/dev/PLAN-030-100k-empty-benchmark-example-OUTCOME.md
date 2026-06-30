# PLAN-030 10 万行空策略基准示例结果

## 结论

已新增 10 万行空策略基准示例，默认不输出 minbt 内部日志，结束时只输出规模和计时信息。

## 变更

1. `examples/09_benchmark_100k_empty.py`
   - 生成 10 万行 bar 数据。
   - 使用空 `Strategy`。
   - 执行 `Exchange.set_bars()` 和 `Exchange.run()`。
   - 输出构造数据、载入数据、运行回测和总耗时。

2. `tests/test_examples.py`
   - 新增测试确认基准示例可运行。
   - 确认 stdout 包含关键计时字段。
   - 确认 stderr 为空，避免日志或 warning 污染输出。

## 本地运行结果

```text
rows=100000
symbols=10
datetimes=10000
build_data_seconds=0.1161
set_bars_seconds=0.2893
run_seconds=0.0760
total_seconds=0.4815
```

## 验证

已执行：

```bash
python examples/09_benchmark_100k_empty.py
python -m pytest -q tests/test_examples.py
python -m pytest -q
git diff --check
```

结果：

- `examples/09_benchmark_100k_empty.py` 正常输出计时信息。
- `tests/test_examples.py`: 9 passed。
- 全量测试：124 passed。
- `git diff --check`: 通过。
