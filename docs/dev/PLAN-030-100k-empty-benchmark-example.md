# PLAN-030 10 万行空策略基准示例

## 目标

新增一个可直接运行的 10 万行回测基准示例，用于验证 minbt 在策略为空、不开日志的情况下处理 10 万行 bar 数据的耗时。

## 范围

1. 新增 `examples/09_benchmark_100k_empty.py`。
2. 示例生成 10 万行 pandas DataFrame：
   - 10,000 个 dt。
   - 10 个 symbol。
   - 合计 100,000 行。
3. 策略为空，不下单，不主动配置 logger。
4. 结束时输出：
   - `rows`
   - `symbols`
   - `datetimes`
   - `build_data_seconds`
   - `set_bars_seconds`
   - `run_seconds`
   - `total_seconds`
5. 增加测试，确认示例可运行、无 stderr 输出、包含关键计时字段。

## 非目标

1. 不把性能基准变成硬阈值测试。
2. 不修改回测核心逻辑。
3. 不新增日志配置。

## 验证

1. `python examples/09_benchmark_100k_empty.py`
2. `python -m pytest -q tests/test_examples.py`
3. `python -m pytest -q`
4. `git diff --check`
