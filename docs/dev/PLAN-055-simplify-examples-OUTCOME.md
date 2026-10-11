# PLAN-055 结果：精简并独立化示例

## 完成内容

- 审阅了原有 18 个 `examples/*.py` 文件，保留 16 个可运行示例，删除 `example_utils.py` 和 `plot_utils.py`。
- 所有示例不再导入其他 `examples/` 文件，也不再包含绘图代码或绘图依赖。
- 内存行情改用标准库生成的 `list[dict]`；CSV 样本使用标准库 `csv` 读取。
- 突破、轮动和配对策略改为直接调用 `Broker.order_target_value()`、`close_position()`。
- 清理了冗余 matplotlib/iosql/外部路径预检、旧的历史列表转换，并移除了截图和弹窗说明。
- 更新 README、minbt usage skill、盈亏与绘图设计文档及示例测试。
- 保留 Binance、CSV、iosql Feed 专项；这些示例仍需要各自的数据源，其中 iosql 需要 iosql 包。

## 复查与验证

- `python -m pytest -q tests/test_examples.py`：15 项通过。
- `ruff check examples`：通过。
- AST 解析通过全部 16 个可运行示例；检查确认没有 `example_utils` 或 `plot_utils` 导入。
- `git diff --check`：通过。
- 测试使用 fake Feed 验证 Binance 示例；CSV 和 iosql 示例需要外部数据，因此没有在本地运行。
