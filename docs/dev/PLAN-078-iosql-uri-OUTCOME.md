# PLAN-078 实施结果

日期：2026-11-07。
对应计划：[PLAN-078](PLAN-078-iosql-uri.md)。
状态：已完成实施、复审和验证。

## 实施结果

- 将两个 iosql 示例、README、当前设计示例、使用技能和 Feed 错误提示的推荐写法改为 `iosql:///绝对路径`。
- 保持 Feed 对 `sqlite://` 等 iosql 支持的其他 URI 的透传兼容，未引入强制迁移。
- 测试创建新库时显式使用 `Database.create(..., engine=...)`；读取已有库时使用 `iosql://`，由 iosql 自动识别 SQLite 或 Parquet。
- 文档说明 `iosql://` 需要支持该 URI 的 iosql 版本，并说明它用于打开已有本地库。
- 既有历史计划和归档版本保持原貌。

## 验证

- `python -m pytest -q`：**598 passed in 40.87s**。
- iosql Feed 及相关回归测试：**125 passed**，覆盖真实临时 SQLite、Parquet 和旧 `sqlite://` URI。
- 使用真实临时 iosql SQLite 库分别运行 `examples/15_iosql_feed.py` 和 `examples/20_iosql_all_symbols.py` 的策略入口：均成功读取三条 K 线。
- 对修改的 Python 文件运行 `ruff check`：通过；`git diff --check`：通过。
