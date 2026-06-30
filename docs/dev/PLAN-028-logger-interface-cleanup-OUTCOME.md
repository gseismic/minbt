# PLAN-028 logger 用户接口清理结果

## 结论

已将 logger 设计收敛为最小方案：

1. 直接使用 `loguru.logger`。
2. 删除 `I18nLogger` 和额外配置封装。
3. minbt 默认关闭库内部日志，examples 默认只输出策略结果。
4. 用户需要日志时使用 loguru 原生接口配置屏幕或文件输出。

## 代码变更

1. `minbt/logger.py`
   - 改为直接导出 `loguru.logger`。
   - 导入时执行 `logger.disable("minbt")`，默认关闭 minbt 内部日志。
   - `__all__` 仅保留 `logger`。

2. `minbt/utils/i18n_logger.py`
   - 删除双语 logger 封装。
   - 删除 `create_logger`、`I18nLogger` 等非核心实体。

3. `minbt/__init__.py`
   - 移除 `configure_logging`、`disable_logging` 导出。
   - 保留 `logger` 导出。

4. `minbt/exchange.py`
   - 删除双语 key 风格日志。
   - 改为普通 loguru 消息字符串。

5. `minbt/broker/market.py`
   - `pd.Timestamp(...).to_pydatetime()` 前处理 nanosecond，避免 examples 出现 pandas warning。

## 文档变更

1. `README.md`
   - 新增“日志”小节。
   - 明确默认关闭库内部日志。
   - 给出 `logger.enable("minbt")` 和 `logger.add("logs/minbt.log")` 用法。
   - 说明 `logger.remove()` 会影响进程级 loguru sink。

2. `docs/design/minbt-20260630-system-design.md`
   - 新增“日志接口”设计。
   - 明确 logger 不进入入门主路径。
   - 明确不提供 `configure_logging()` / `disable_logging()` 二次接口。
   - 明确 examples 不应定义 `QuietLogger`。

## 测试变更

1. `tests/test_logger.py`
   - 覆盖 `minbt.logger` 是 loguru 原生 logger。
   - 覆盖 minbt 内部日志默认静默。
   - 覆盖 `logger.enable("minbt")` 后可看到内部日志。
   - 覆盖 `logger.add(file)` 可写文件。
   - 覆盖自定义 logger 注入仍可用。

2. `tests/test_examples.py`
   - 增加 `stderr == ""` 断言，防止 examples 再次出现日志或 warning 污染。

3. `tests/test_api_contract.py`
   - 确认包级接口不导出 `I18nLogger`、`create_logger`、`configure_logging`、`disable_logging`。

## 验证

已执行：

```bash
python examples/01_demo_mini.py
python examples/07_scenario_multi_rotation.py
python -m pytest -q tests/test_logger.py tests/test_examples.py tests/test_api_contract.py
python -m pytest -q
git diff --check
```

结果：

- `examples/01_demo_mini.py` 只输出 `final_equity` 和 `final_position`。
- `examples/07_scenario_multi_rotation.py` 只输出策略结果。
- `tests/test_logger.py tests/test_examples.py tests/test_api_contract.py`: 24 passed。
- 全量测试：118 passed。
- `git diff --check`: 通过。

## 设计判断

专业库的常见做法是库默认不主动污染用户输出，由应用入口决定日志 sink、级别和格式。

对于 minbt 当前定位，直接使用 loguru 更合适：

1. 不新增 logger 配置 DSL。
2. 不维护双语消息表。
3. 不引入 `QuietLogger` 这种示例辅助实体。
4. 用户已有 loguru 经验时无需学习 minbt 专属日志接口。

当前方案把 logger 定位为诊断工具，不影响核心回测接口。
