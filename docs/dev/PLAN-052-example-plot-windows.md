# PLAN-052 示例绘图弹窗

## 目标

运行 `examples/` 中的任一可运行示例时，在有图形界面的环境中弹出图表窗口，用户关闭窗口后程序继续退出；仍保留原有 PNG 截图保存。

## 现状

- 12 个示例已有绘图，但脚本强制使用 Matplotlib `Agg` 后端，且共享保存函数保存后立即关闭图表。
- `301_feed_csv.py`、`302_feed_iosql.py`、`400_exchange_replay_modes.py`、`401_exchange_generic_bar_storage.py` 当前没有绘图。
- 自动化运行需要能通过环境变量关闭弹窗，避免测试进程等待用户操作。

## 实施

1. 移除示例脚本强制选择 `Agg` 的代码，让 Matplotlib 按当前环境选择后端。
2. 修改 `examples/plot_utils.py`：保存截图后默认调用 `plt.show(block=True)`；提供 `MINBT_EXAMPLE_SHOW=0` 的无窗口选项。
3. 增加通用价格与权益图，并为 CSV、iosql、Replay Modes、Generic Bar Storage 四个示例补齐图表；图表标题使用新的示例编号。
4. 移除 examples 中把仓库目录加入 `sys.path` 的代码，示例依赖已安装的 minbt；导入本地绘图工具由直接执行脚本时的 Python 脚本目录解析。
5. 在 `tests/test_examples.py` 中关闭弹窗并为动态导入配置本地工具路径；更新 README、usage skill 和绘图设计文档的说明。

## 验收

- 16 个可运行示例都有图表调用；有 GUI 时默认显示窗口，窗口关闭后脚本结束。
- 执行示例仍保存同名截图；设置 `MINBT_EXAMPLE_SHOW=0` 时保存截图但不显示窗口。
- 示例不通过 `sys.path` 注入仓库目录加载 minbt。
- Review 确认绘图数据来自示例实际回放结果，且不改变回测逻辑。
