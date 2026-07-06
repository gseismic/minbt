# PLAN-038 pyproject 安装配置结果

## 完成内容

1. 新增 `pyproject.toml`，将项目元数据、依赖、可选依赖、setuptools 包发现和 pytest 配置统一迁入。
2. 删除旧的 `setup.py`。
3. 删除独立 `pytest.ini`，原 `pythonpath = .` 已迁入 `[tool.pytest.ini_options]`。
4. 更新 README 安装说明：
   - 明确 `pyproject.toml` 是安装配置来源。
   - 补充 `pyta`、`plot`、`dev` 可选依赖。
   - 说明不再需要单独维护 `pytest.ini`。
   - 补充 `examples/11_crypto_binance_feed.py`。
   - 修正“不能拉取或缓存行情”的过期边界。
5. 更新 `skills/minbt-usage`：
   - 补充安装与测试说明。
   - 补充 `Exchange.add_feed(...)` 和 Binance futures K 线 feed 使用路径。
   - 补充 `dt` 统一为 UTC `datetime.datetime` 的数据契约。
   - 更新验证命令为 `python -m pytest`。

## 关于 pytest.ini

当前不需要保留独立 `pytest.ini`。

原因：

1. 旧文件只有 `pythonpath = .` 一项。
2. 该配置已放入 `pyproject.toml` 的 `[tool.pytest.ini_options]`。
3. 全量测试输出确认 pytest 已读取 `pyproject.toml` 作为配置文件。

## 验证结果

```bash
python -m pip install -e .
```

结果：基于 `pyproject.toml` 构建 editable wheel 并安装成功。

```bash
python -m compileall -q minbt tests examples
```

结果：通过。

```bash
git diff --check
```

结果：通过。

```bash
python -m pytest
```

结果：`145 passed`。测试输出显示 `configfile: pyproject.toml`。

```bash
python examples/01_demo_mini.py
```

结果：

```text
final_equity=10000.05
final_position=0.000000
```

```bash
python examples/11_crypto_binance_feed.py
```

结果：

```text
final_equity=10458.09
final_cash=1992.00
final_position=0.188220
bar_count=48
```
