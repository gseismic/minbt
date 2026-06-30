# PLAN-028 logger 用户接口清理

## 目标

修复 examples 运行时日志输出混乱的问题，使 minbt 符合最简回测系统的用户接口目标：

1. 默认运行示例时不输出库内部 INFO/DEBUG 日志。
2. 用户需要诊断时可以显式开启日志，并选择输出到屏幕或文件。
3. 日志接口保持最小，不再封装双语 logger 或自定义配置 API。
4. 修复例子中与 logger 无关但污染屏幕的 pandas nanosecond warning。

## 范围

1. 梳理并修复 `minbt.logger`：
   - 直接导出 `loguru.logger`。
   - 默认 `logger.disable("minbt")`，避免库内部日志污染 examples。
   - 用户需要诊断时直接使用 loguru 原生接口：`logger.enable("minbt")`、`logger.add(...)`。
   - 移除 `I18nLogger`、`create_logger`、`configure_logging`、`disable_logging` 等非核心实体。
2. 更新导出接口：
   - 仅保留 `minbt.logger`。
3. 更新测试：
   - 默认导入和默认运行不应产生库内部日志。
   - 显式启用 loguru 日志可用。
   - loguru 文件输出可用。
   - 自定义 logger 注入仍可用。
4. 更新 `README.md` 和 `docs/design/minbt-20260630-system-design.md`：
   - 说明默认静默。
   - 给出 loguru 屏幕和文件日志配置示例。
5. 清理 warning：
   - 修复 `Market._to_datetime()` 对 pandas Timestamp 的转换，避免例子运行时出现 nanosecond warning。

## 验证

1. 运行 `python examples/01_demo_mini.py`，确认只输出策略结果。
2. 运行 `python examples/07_scenario_multi_rotation.py`，确认只输出策略结果。
3. 运行 logger 单测和 example 单测。
4. 运行全量测试。
5. 执行 `git diff --check`。

## 非目标

1. 不新增交易功能。
2. 不把 logger 设计成复杂的观测系统。
3. 不要求每个 example 自定义 logger。
4. 不追求双语日志，日志不是 minbt 核心功能。
