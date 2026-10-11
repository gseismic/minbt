# PLAN-056 结果：示例内联绘图

## 完成内容

- 为当前维护的 16 个 `examples/*.py` 脚本添加独立的 Matplotlib 图表，并在脚本入口调用 `plt.show()`。
- 策略及 Feed 示例显示权益曲线；盈亏 sanity check 对比各场景净盈亏；100k 基准示例显示构造、加载和回放耗时。
- 未恢复 `example_utils.py` 或 `plot_utils.py`，示例之间仍无共享文件依赖。
- README、minbt usage skill 和绘图设计文档已说明 Matplotlib 安装方式与内联绘图约定。
- 示例测试使用 `Agg` 后端并抑制该后端无法弹窗的提示；增加静态检查，确保所有活动示例直接导入 pyplot 并调用 `show()`。

## 复查与验证

- `python -m pytest -q tests/test_examples.py`：16 项通过。
- `ruff check examples tests/test_examples.py`：通过。
- `git diff --check`：通过。
- 静态检查覆盖当前 16 个示例脚本；CSV 和 iosql Feed 示例需要用户配置的数据源，因此未在本机实跑。Binance Feed 测试使用 fake feed。

## 使用说明

运行示例前安装绘图依赖：`pip install -e ".[plot]"`。在支持图形界面的环境中，示例运行结束后会弹出图表；无图形界面时 Matplotlib 使用当前环境配置的后端。
