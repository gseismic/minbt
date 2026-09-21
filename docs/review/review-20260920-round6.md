# 全量代码 Review 报告·第六轮（2026-09-20）

## 背景

第五轮 review 见 `docs/review/review-20260920-round5.md`，基线 main @ 750ed86。本轮基线 main @ c4e0cc0，期间三次提交：

1. `2d44b6e` PLAN-042：新增 CSV / iosql 渐进式数据 Feed（`minbt/data/bars.py`、`csv.py`、`iosql.py`、`Exchange._run_streaming`、`tests/test_streaming_feeds.py`、examples 12/13）；
2. `c4e0cc0` PLAN-042 Review 修正：arrow 时间兼容、缺月告警、CSV end 过滤优化、设计稿同步；
3. 其余为 docs 提交。

即：本轮相对第五轮，**除 data 新文件与 exchange 流式路径外，核心源码零改动**。因此本轮两个目标：

1. 审查 PLAN-042 引入的新代码（前五轮完全未覆盖）；
2. 复测前轮全部发现是否仍成立（重点复测 R5-P1-1）。

## Review 范围与方法

- **范围**：`minbt/data/bars.py`(165)、`minbt/data/csv.py`(201)、`minbt/data/iosql.py`(96)、`minbt/exchange.py` 新增约 140 行流式逻辑、`tests/test_streaming_feeds.py`(441)、examples 12/13、设计稿与 OUTCOME 文档；并对全部核心模块做通读复核。
- **方法**：逐文件通读；运行全量测试；对每个行为类疑点编写独立运行时脚本复现（含流式/物化双路径、iosql 真实库、异常路径、100k 行内存基准）。

## 结论摘要

PLAN-042 的实现质量整体合格：`_KlineRowFeed` 共享层抽象干净，两级乱序防护与重复检测完善，生成器/数据库资源释放考虑周到，流式与物化等价性、重复 run 一致性都有测试保证；100k 行实测峰值内存 38.3MB（物化 180.1MB），设计的内存目标真实达成。

主要问题集中在**“数据缺失静默化”**：新 Feed 对“请求了但不存在的 symbol / 表名 / 时间区间”大多不报错，而唯一的数据空洞信号（缺月 warning）又被 `logger.disable("minbt")` 默认吞掉，用户可能拿到一个“成功结束的空回测”。

本轮新发现（编号 `R6-` 前缀）：

| 级别 | 编号 | 概述 |
| --- | --- | --- |
| P2 建议修复 | R6-P2-1 | 请求的 symbol / 数据表 / 区间不存在时静默产出空回测，无异常 |
| P2 建议修复 | R6-P2-2 | 缺月等数据完整性告警依赖默认关闭的 minbt logger，实际等效静默 |
| P3 信息性 | R6-P3-1 | 仅传 `start` 时缺月检测不生效（回退用已发现月份首尾） |
| P3 信息性 | R6-P3-2 | iosql 表名/interval 拼错时报 iosql 内部契约错误，消息不指向 `interval` 参数 |
| P3 信息性 | R6-P3-3 | 设计稿残留与最终语义矛盾的段落（set_* 包装说明、示例缺文件行为） |
| P3 信息性 | R6-P3-4 | 设计测试计划第 5、7 项（多 event-type 归并顺序、内存基准）未落地为测试 |
| P3 信息性 | R6-P3-5 | arrow 时间支持只加了新 bars.py，`binance._to_utc_datetime` 仍拒绝 arrow |
| P3 信息性 | R6-P3-6 | 流式路径 100k 行比物化慢约 40%（内存换时间），无基准测试与说明 |

前轮发现**全部仍在**：本轮复测确认 R5-P1-1（pending 限价单 + `close_portfolio` 崩溃）在**新增的流式路径上同样必现**，另确认 pyta2 用例失败、`get_positions()` 泄漏、tz-aware + A_STOCK 拒单、`_is_multiple` 浮点容差、`_normalize_dt(None)` 返回 NaT、pyta2 下 `get_hist_position_sizes` 抛 KeyError 等（详见复测表）。

## P2 建议修复

### R6-P2-1 请求的数据不存在时静默产出空回测

- **位置**：
  - `minbt/data/csv.py:91-97`（symbol/interval 过滤）、`107-111`（仅当**所有** symbol 都无文件才报错）、`121-124`；
  - `minbt/data/iosql.py:51-76`（`prepare` 不做表/符号存在性检查）；
  - `minbt/exchange.py:717-734`（`run` 对“0 事件”无任何检查）。
- **现象**（均运行时复现）：
  1. **CSV 部分 symbol 静默缺失**：`symbols=["BTCUSDT","TYPOUSDT"]`、目录只有 BTCUSDT 文件 → 运行成功，事件流只含 BTCUSDT，`feed.symbols` 却包含 TYPOUSDT。
  2. **CSV interval 过滤静默缺失**：目录同时存在 1m/5m，传 `interval="1m"` 时 5m 文件被静默滤掉；若某标的只有 5m 文件，则该标的数据整体消失。
  3. **iosql 表名/interval 拼错**：`interval="1h"`（库中只有 `kline_1m`）且未传 `start/end`、`symbols` 时，`Database.table()` 返回无契约空表，`query(order_by=...)` 返回 0 行，**零异常零告警**；传了 `symbols/start/end` 时才抛 iosql 内部契约错误（见 R6-P3-2）。
  4. **区间与数据无交集**：CSV `start="2023-05-01"` 而只有 2023-01 文件 → 0 事件；唯一信号是缺月 warning，而它默认不可见（R6-P2-2），实测脚本不启用日志时什么都看不到。
- **影响**：`on_finish` 照常调用、`final_equity` 等于初始现金，用户可能把“空回测”当成“策略没信号”。这是比崩溃更隐蔽的错误形态。
- **修复建议**：
  1. CSV `prepare()` 末尾校验：每个 `requested_symbols` 至少命中一个文件，否则抛 `FileNotFoundError`（消息含未命中的 symbol 列表）；
  2. iosql `prepare()` 校验目标表存在/契约可查询，并校验 `requested_symbols` 至少有一个命中（可先做一次轻量查询或读取表元数据）；
  3. 流式路径在用户显式给出 `start/end` 且整个 run 产生 0 个事件时，至少给出与 R6-P2-2 联动的可见信号或直接报错。

### R6-P2-2 数据完整性告警被默认日志策略吞掉

- **位置**：`minbt/logger.py:4`（`logger.disable("minbt")`）、`minbt/data/csv.py:144`（缺月 `logger.warning`）。
- **现象**（运行时复现）：缺月 + 区间不匹配的 CSV Feed，在默认配置下 `list(feed.events())` 不产生任何可见输出；`tests/test_streaming_feeds.py:104-114` 必须手动 `raw_logger.enable("minbt")` 才能断言告警，恰好证明默认路径下该告警不可见。
- **影响**：设计稿与 OUTCOME 把“缺月告警”列为已实现的数据完整性保障，但默认配置下它等价于“静默跳过”，PLAN-042 想解决的正是这个问题。
- **修复建议**（与第五轮末尾备忘同一决策点，二选一后全局统一）：
  1. 数据完整性问题（缺月、区间无交集、请求符号未命中）改为抛异常，默认 fail-fast；
  2. 或调整默认日志策略：仅 disable DEBUG/INFO，保留 WARNING/ERROR 可见（例如 `logger.disable` 收紧到 `minbt` 的 info 级别，或提供 `minbt` 数据告警独立开关）。

## P3 信息性

| # | 位置 | 问题与建议 |
| --- | --- | --- |
| R6-P3-1 | `minbt/data/csv.py:133-137` | 仅传 `start` 时，期望月份回退为“已发现月份首尾”，实测 `start=2023-01`、文件仅 2023-03 时不告警 2023-02。建议 `first` 优先取 `start`，缺省才用已发现首月。 |
| R6-P3-2 | `minbt/data/iosql.py:51-72`、`39` | 表名/interval 错误时错误信息来自 iosql 内部（`BadArgument query(symbols=) 需要表契约声明 symbol_column`、`MissingTimeColumn`），不指向 minbt 的 `interval` 参数；`batch_size=None` 时是裸 `TypeError` 而非 ValueError。建议捕获/预检并转换为“table kline_1h not found / invalid interval”类消息。 |
| R6-P3-3 | `docs/design/csv-iosql-feed-20260920-design.md:107-108`、`364-365` | 决策 3 的 96-99 行已更新为“显式报错”，但 107-108 行仍写“set_* 数据包装为内存事件源，保证 run(streaming=True) 总是可用”，与实现矛盾；364-365 行写示例“文件缺失时自动跳过”，实际 `examples/12_csv_feed.py:41-45`、`13_iosql_feed.py:52-56` 是 SystemExit 报错。建议删除矛盾段落。 |
| R6-P3-4 | `tests/test_streaming_feeds.py` | 设计测试计划第 5 项（bars+books+trades 同 dt 的 `_FEED_ORDER` 归并顺序）与第 7 项（内存基准）无对应测试。手工复现确认顺序正确、内存目标达成（见验证记录），但无防回归测试；归并顺序测试建议补齐。 |
| R6-P3-5 | `minbt/data/bars.py:35-46` vs `minbt/data/binance.py:427-433` | PLAN-042 只给新共享工具加了 arrow 支持；`BarsReplayFeed` 走的 `binance._to_utc_datetime` 仍用 `pd.Timestamp(value)`，实测传 arrow 对象抛 `TypeError: Cannot convert input ... of type Arrow to Timestamp`。同一“给 feed 传 start/end”在两个数据源行为不一致，建议复用同一实现。 |
| R6-P3-6 | `minbt/exchange.py:294-360` | 100k 行单标的实测：流式 15.4s / 峰值 38.3MB，物化 10.9s / 180.1MB。省内存的代价是约 40% 耗时（heapq.merge + `_checked_stream` 包装 + 逐 dt 分发），当前无文档说明该取舍。可在 README“渐进读取”章节补一句，并补设计计划第 7 项基准用例或记录本次数字。 |

## 上轮（第五轮）发现复测状态

第五轮报告的 3 项新发现与上轮全量报告的 7 项 P3 均未修复（代码未变），本轮逐项确认：

| 编号 | 状态 | 复测方式与结果 |
| --- | --- | --- |
| R5-P1-1 pending 限价单 + `close_portfolio` 崩溃 | **仍在，且流式路径同样必现** | 复现：`add_portfolio("p1")` → `submit_limit_order(limit=70, portfolio="p1")` → `close_portfolio("p1")`（skipped，组合被移除）→ 价格跌至 60 → 两条路径均在 `broker.py:749 get_position_size` 抛 `ValueError: portfolio not found: p1` 终止 run（流式 traceback 经 `exchange.py:672`） |
| R5-P2-1 pyta2 下 `get_hist_position_sizes` 抛 KeyError | 仍在 | 实测 `KeyError: 'Column A does not exist'`（从未有持仓记录的 symbol） |
| R5-P2-2 tz-aware + A_STOCK 全部拒单 | 仍在 | Asia/Shanghai 09:35 数据 → 订单 `rejected`；naive 同钟点数据 → `filled` |
| 全量报告 P1-1 pyta2 下测试失败 | 仍在 | `python -m pytest tests -q` → **1 failed, 185 passed**（失败用例不变） |
| 全量报告 P2-1 `_is_multiple` 浮点容差 | 仍在 | `_is_multiple(60000.0, 0.00001)` 仍返回 `False` |
| 全量报告 P2-2 `get_positions()` 泄漏内部字典 | 仍在 | `broker.get_positions()` 返回值上 `d["HACK"]="x"; d.pop("AAPL")` 后，broker 内部只剩 `['HACK']` |
| 全量报告 P2-3 加仓静默替换退出条件 | 仍在 | 代码未变（`broker.py:411-417`） |
| R5-P3-1 `_normalize_dt(None)` 返回 NaT | 仍在 | 实测返回 `NaT`；流式路径 `_checked_stream` 的 `isinstance(event.dt, datetime)` 同样拦不住 NaT |
| R5-P3-2 `Portfolio.get_position` 默认创建空壳 | 仍在 | `portfolio.py:300-305` 未变 |
| R5-P3-3 binance 不支持 `1w`/`1M` | 仍在 | `binance.py:446-453` 未变（且新增 R6-P3-5 的 arrow 不一致） |

## 值得肯定的部分

- **两级乱序防护**：feed 行级（`_KlineRowFeed.events` 的 dt 回退检查、CSV 文件内 `open_time` 检查）+ Exchange 归并前 `_checked_stream` 检查，错误消息含 feed 名与具体行，fail-fast 语义正确。
- **资源生命周期**：`ExitStack` 保证月内文件句柄释放；`_row_stream`/`events()` 的 `finally` 级联；`close()` 幂等；异常路径下策略抛错后原始异常不被 close 错误掩盖（手工验证）。
- **等价性保障**：`test_streaming_matches_materialized_set_bars` 对回调序列/权益/持仓逐位比较；重复 run 一致性在流式与物化两条路径都有测试；iosql 用 monkeypatch 断言不走 `select()`，防回归倒车。
- **内存目标真实达成**：100k 行峰值 38.3MB vs 180.1MB，符合“内存 O(单 dt)”设计。
- 合并顺序手工验证正确：同 dt 下 `bars → trades → news`，与 `_FEED_ORDER` 一致。

## 验证记录

- `python -m pytest tests -q`：1 failed, 185 passed（失败项为既有 pyta2 问题）。
- 复现脚本（临时目录，未改动仓库代码）：
  - CSV 缺失 symbol：`symbols=["BTCUSDT","TYPOUSDT"]` → 1 个事件、data 只含 BTCUSDT；
  - isoql 无 start/end + 错误 interval：0 事件、无异常；传 start/end 时抛 iosql 契约错误；
  - CSV 区间不匹配：`start=2023-05`、文件 2023-01 → 0 事件、默认日志下无输出；
  - 流式 + pending 限价单 + `close_portfolio`：`ValueError: portfolio not found: p1`（traceback 见复测表）；
  - 200k（100k bars）CSV：流式 38.3MB/15.4s，物化 180.1MB/10.9s；
  - 多 event-type 流式 feed：顺序 bars→trades→news 正确；
  - 策略中途抛异常 + iosql feed：资源释放后原始 RuntimeError 正常上抛。

## 建议后续

第五轮建议的“合并立项 `PLAN-042-review-fixes.md`”未发生——PLAN-042 编号已被 CSV/iosql 功能占用，修复计划至今缺位。建议本轮同样合并立项 **`PLAN-043-review-fixes.md`**：

1. **批次一（崩溃/正确性）**：R5-P1-1（含流式路径）、P1-1（pyta2 测试/类型语义）、R5-P2-1；
2. **批次二（静默数据问题）**：R6-P2-1、R6-P2-2（先做默认日志策略决策，再实现）；
3. **批次三（其余 P2/P3）**：P2-1/P2-2/P2-3、R5-P2-2（需先决策时段钟点语义）、R5-P3-1/2/3、R6-P3-1..6；
4. 文档同步：设计稿 107-108/364-365 矛盾段落、README 流式性能取舍说明。

其中需先做语义决策的项：R5-P2-3（加仓退出条件合并 vs 文档明示）、R5-P2-2（trading_sessions 判定钟点语义）、R6-P2-2（数据问题 fail-fast vs 让警告默认可见）。
