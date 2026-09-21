# PLAN-046 物化行数上限与自动降级流式

## 目标

为 `Exchange.run()` 增加物化路径的行数上限参数 `max_materialize_rows`：当
`add_feed` 数据源的物化消费超过上限时，不报错，而是自动降级到流式路径重跑，
保证大数据集零干预可回测。

## 背景

- 物化路径（`_run_materialized` → `_run_feeds` → `_materialize_data_feed`）会把
  全部 feed 事件先拉进内存再回测，内存 ∝ 全量数据。
- 流式路径（`_run_streaming`）内存 ∝ 单个时间截面，但 run 循环更慢。
- 用户无法在 run 前预知 feed 数据总量；等内存爆掉才失败太晚。
- 行数是确定性指标：比内存监测更直接、可预测、跨平台一致。

## 接口

```python
Exchange.run(streaming=None, max_materialize_rows=None)
```

- `max_materialize_rows=None`（默认）：行为与现状完全一致，不限流。
- `max_materialize_rows=N`（正整数）：物化消费 feed 事件时逐行计数（含 set_*
  数据行），超过 N 触发降级。

## 语义

### 触发与降级流程

1. `run(max_materialize_rows=N)` 且未强制流式时，走物化路径。
2. `_materialize_data_feed` 逐事件累计行数（`set_*` 数据的行数在开始时计入基数）。
3. 累计行数超过 N：
   - 抛内部信号 `_MaterializeLimitExceeded`，终止物化；
   - 在 finally 中对已 prepare 的 feed 逐一 `close()`，丢弃已物化的 feeds；
   - 记录 warning 日志（含已消费行数与上限）；
   - 改走 `_run_streaming()`。
4. 降级发生在 `on_init` 之前（物化阶段不执行策略回调），策略无感知；
   设计文档已保证物化与流式结果逐位一致，降级不影响回测结果。

### 不可降级场景（明确报错）

| 场景 | 行为 |
|---|---|
| 存在 `set_*` 注册数据且无任何流式 feed | 物化行数来自内存数据，降级无意义，超限时抛 ValueError 并提示 |
| 存在 `set_*` 数据且存在流式 feed | set_* 部分无法流式，超限时抛 ValueError 并提示混合场景不支持降级 |
| `streaming=True` 强制流式 | 不经过物化，`max_materialize_rows` 无效（允许传入但不使用，不报错） |
| `streaming=False` 强制物化 | 仍按上限检查，超限时报错而非降级（用户显式要求物化） |
| `max_materialize_rows` 非正整数 | TypeError/ValueError |

### 计数口径

- 每个 feed 事件的行数 = 事件 payload 的行数（`by_symbol` 为 symbol 数，
  `by_symbol_list`/`list` 为行列表长度）。
- set_* 数据行数在各 feed 的 `grouped` 中统计后作为计数基数。
- 计数按“已消费行”累计，即超限发生在读取第 N+1 行之后的事件边界上。

## 实施要点

- `_MaterializeLimitExceeded(Exception)` 内部信号类，不导出。
- `_materialize_data_feed` 增加计数器参数；`_add_feed_event` 返回或可查询本次
  合并行数（从 `_merge_payload` 后的 payload 尺寸差值计算）。
- `run()` 中物化循环用 try/except 包裹，捕获信号后清理并切换 `_run_streaming`。
- feed 可重入性依赖既有 prepare/events/close 生命周期（PLAN-042 已验证
  `run()` 可重复调用），降级重启直接复用。

## 测试计划

1. 超限触发降级：小上限 + 流式 feed → 走流式，结果与不限物化逐位一致。
2. 不超限不降级：上限足够大 → 物化路径，日志无降级警告。
3. `streaming=False` + 超限 → ValueError。
4. 混合场景（set_bars + feed）超限 → ValueError。
5. 仅 set_* 数据 + 超限 → ValueError。
6. 参数校验：0、负数、非 int → 报错。
7. 降级后 feed 可正常 close、重复 run 结果一致。

## 文档

- README「数据回放」小节补充 `max_materialize_rows` 说明。
- skills/minbt-usage/SKILL.md 的 run 参数表补充该参数。
- 设计文档 csv-iosql-feed-20260920-design.md 追加“物化行数上限”小节。

## 验收标准

- 新增测试全部通过；现有测试不回归。
- 默认参数下行为与现状完全一致。
- 降级发生时输出 warning 日志，且回测结果与纯流式路径逐位一致。
