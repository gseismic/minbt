# PLAN-058 实施结果：单次运行、控制回调与结果快照

## 已完成的行为

- `Exchange.run(start=None, end=None, control=None, load_mode="auto")` 返回独立 `RunResult`，默认完成历史回放；同一 Exchange 只启动一次。
- `[start, end)` 使用 UTC 事件时间，`None` 保留数据自然边界。窗口外数据不推进行情、账户和历史；空窗口明确失败。
- 每个完整时间批次前统一检查 `continue/pause/exit`。暂停关闭全部策略行情回调，行情、挂单、退出规则、强平和账户历史持续工作；继续保留状态，不补发旧行情。
- 退出结束整个回测，返回已处理区间，包括零进度退出。`meta` 分别记录运行结束状态、结束原因和最后的控制状态，不把退出写成正常完成。
- 结果提供含时间的权益、默认分仓持仓曲线，以及初始资金、订单、最终分仓持仓和库级盈亏。订单、元信息、账户快照不可变，查询容器和原对象的后续变化不会污染结果。
- 内置 Strategy/Broker 拒绝跨实验复用；同次共享账户仍可用。启动后固定注册与关联，控制及结束通知只读内置账户，外部线程不能直接写运行账户。
- 失败原样传播并消费生命周期；显式关闭批次生成器、事件迭代器与 Feed。Feed 包装幂等关闭，正常关闭失败不会被吞掉，已有业务异常优先。
- 新增 `examples/106_scenario_run_control.py`，使用公开结果查询并内联绘图；更新 README、运行设计、系统及接口设计、回放背景和使用指南，清除本次运行方案的废弃草案与重跑描述。

## 审阅修正

1. 主动结束生成器会进入 `GeneratorExit`。资源关闭时不把它当作需要掩盖关闭故障的业务异常；外层已有错误则继续保留原错误。
2. 自定义 Broker 只支持默认分仓时，快照不强制使用具名分仓查询。可选数据能力缺失或声明未实现时，仅对应结果查询报 `NotImplementedError`；真正的查询故障仍使运行失败。
3. 结果先冻结账户与历史，再执行报告和释放资源。收尾失败不返回已经准备的快照；内置账户在报告阶段拒绝追加交易。
4. 启动占用在实例检查通过后原子完成。独立 Exchange 竞争同一内置 Broker 时仅一个成功，校验失败未开始的配置仍可修正。

## 设计验收审计

以下序号对应 `docs/design/run-20261012-control.md` 的验收标准。测试名称位于 `tests/test_run_control.py`，另注明者除外。

| 序号 | 已验证要求 | 权威证据 |
| --- | --- | --- |
| 1 | 默认回测返回 completed，普通实例注册保持可用 | `test_default_and_single_sided_windows_include_last_available_data`；既有 Exchange 和示例测试 |
| 2 | 仅一次启动，失败或退出不能重启，拒绝跨实验复用，允许同次共享账户 | 非法控制及空窗口后的重跑测试；`test_native_instances_cannot_be_reused_but_unstarted_setup_can_be_corrected`；同一入口及跨入口并发占用测试；共享账户完整批次测试 |
| 3 | 暂停停止行情回调，账户估值、挂单、止损、函数规则、强平和穿仓继续 | 真实权益曲线测试；挂单与止损测试；函数退出规则测试；四种保证金风险场景测试 |
| 4 | 当前批次继续，保留状态，不重初始化或补发 | `test_pause_continue_exit_preserve_real_account_curve` 核对回调仅收到第 0、3 个时间点且初始化一次；实现无额外恢复钩子 |
| 5 | 批次只检查一次，所有类型与策略共用状态，暂停仍检查，非法值失败 | `test_all_callbacks_and_shared_broker_use_one_state_per_complete_timestamp`；暂停/继续/退出边界观测；六种非法返回值测试 |
| 6 | 整次退出，曲线不补点，首批前退出零进度 | 控制曲线测试以 999 的未执行价格核对结束点；`test_initial_exit_returns_empty_progress_and_real_initial_account`；pending 订单保留及后续成交隔离测试 |
| 7 | 正常与退出通知一次，最后暂停仍结束，失败不伪通知 | 生命周期计数与自然暂停完成测试；初始化、读取、控制、行情、采样、快照和结束失败阶段测试 |
| 8 | 元信息、进度及去重控制记录一致，日志区分实际结束 | 控制曲线测试逐字段核对完整 meta；`Exchange.run` 日志由同一 status/reason 生成；独立示例输出 exited/control_exit |
| 9 | 半开窗口、None、多来源、空窗口与读取方式一致 | 默认、预加载、渐进控制测试；两种显式模式窗口测试；单侧边界、空窗口与多类型来源测试 |
| 10 | 快照不受返回容器及原对象影响，各数据对应同一结束点 | `test_result_remains_immutable_after_account_and_returned_containers_change`；退出订单后续成交隔离；曲线、持仓、订单及 Pnl 手算 |
| 11 | 加长数据旧前缀一致，新增绩效使用切点权益 | `test_long_replay_preserves_old_prefix_and_uses_boundary_equity_for_validation` 核对权益、订单前缀，以及新增收益 5 与已实现盈亏 15 的区别 |
| 12 | 所有失败及退出释放资源，原异常优先，失败对象不得续跑 | 八个执行阶段失败测试；Feed/迭代器关闭故障与业务错误组合；两种模式的窗口及退出资源计数 |

## 实际验证

- 相关测试：118 项通过；补充默认分仓和 pending 退出边界后，全量 `python -m pytest -q`：**328 passed**。
- `ruff check minbt tests examples`：通过。
- `python -m compileall -q minbt tests examples`：通过。
- 60 个维护中的 Python 文件通过 Python 3.8 AST 语法检查；运行设计中的 Python 示例与本地链接检查通过。
- `git diff --check`：通过；提交前另检查暂存区的新文件。
- 新控制示例以 Matplotlib Agg 后端运行：`status=exited reason=control_exit`，5 个账户时间点、3 次策略回调，最后时间为 2026-01-05，`final_equity=1015.00 net_pnl=15.00`。未执行的 999 价格不影响结果。
- 全量示例测试覆盖新的控制示例、既有核心和场景示例、兼容回放示例，以及 10 万行基准与 fake Binance 数据源。

## 实施边界与交付

当前仍保留已有读取模式与兼容行情接口；统一回放内核重构不属于本计划。指标恢复由业务逻辑负责，自定义 Broker 自行保证运行隔离与控制/报告阶段的只读约定。

未来 live 的实时接入、等待期间轮询、成交回报和账户对账未实施；当前继续拒绝 live Feed。历史控制只承诺在同步读取或用户回调返回后的完整批次边界响应。

功能提交为 `9533351`（实现单次回测控制和独立结果快照），已推送至 `origin/main`。计划及本结果文件随功能提交保存；收尾文档补齐完成状态与实际交付记录。
