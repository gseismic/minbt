# PLAN-052 示例绘图弹窗结果

## 结果

已完成 [PLAN-052](PLAN-052-example-plot-windows.md)：

1. 16 个可运行示例运行后都会调用共享绘图保存流程。12 个原有图表和 4 个新增的 Feed/Exchange 图表都保留截图，并默认调用 `plt.show(block=True)`；关闭图窗后程序继续。
2. `MINBT_EXAMPLE_SHOW=0` 可关闭窗口显示并仅保存截图，测试运行环境已设置该变量。
3. 移除了示例和共享辅助模块中把仓库目录写入 `sys.path` 的代码。示例从已安装的 minbt 导入库代码；直接运行脚本时由 Python 将脚本目录用于导入同目录的示例辅助模块。
4. 更新 README、usage skill 和绘图设计文档，说明安装依赖、弹窗行为和无窗口选项。

## Review

- 对 `examples/` 的 18 个 Python 文件执行 AST 语法解析，全部通过。
- 检查所有 16 个可运行示例均调用绘图保存流程。
- 在 examples 和使用说明中未发现强制 `Agg` 后端或仓库路径注入。
- `git diff --check` 通过。
- 未运行测试。
