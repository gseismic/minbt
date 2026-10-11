# PLAN-056：在每个示例中直接显示图表

## 目标

当前维护的 16 个示例运行结束后都通过 Matplotlib 显示图表，并保持每个脚本可单独运行，不依赖共享示例工具文件。

## 范围

- 为全部 `examples/*.py` 可运行示例添加内联绘图和 `plt.show()`。
- 策略示例绘制权益曲线；盈亏核对示例绘制各场景净盈亏；性能示例绘制阶段耗时。
- Feed 和 Exchange 示例使用策略公开的权益历史数据。
- 保持 Matplotlib 为可选安装项，在 README 和 usage skill 中说明运行示例需安装 `minbt[plot]`。
- 自动化测试使用非交互后端，避免测试期间阻塞或弹窗。
- 不恢复 `example_utils.py`、`plot_utils.py`，不添加自定义导入预检。
- 不修改 `docs/versions/v0/examples/` 历史快照。

## 实施步骤

1. 记录逐例绘图方案和依赖说明。
2. 为所有活动示例添加独立、简短的图表代码。
3. 调整 README、usage skill、设计文档和测试环境配置。
4. 运行示例测试、静态检查，并审阅每个示例都有直接绘图入口。
5. 记录验证结果和外部数据源示例的运行边界。

## 验收标准

- 当前 16 个示例均直接导入 Matplotlib 并调用 `plt.show()`。
- 示例之间没有共享工具文件依赖。
- 核心测试环境将 Matplotlib 后端设置为 `Agg`，示例仍然可以无窗口运行。
- README 与 usage skill 说明 Matplotlib 安装方式。
