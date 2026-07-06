# PLAN-038 pyproject 安装配置

## 目标

将项目安装配置从 `setup.py` 迁移到 `pyproject.toml`，并同步 README 与 `skills/minbt-usage` 的安装、测试说明。

## 背景

当前项目只有 `setup.py` 和一个独立 `pytest.ini`。`pytest.ini` 只包含 `pythonpath = .`，迁移到 `pyproject.toml` 后可以放到 `[tool.pytest.ini_options]`，不需要单独保留。

## 实施步骤

1. 新增 `pyproject.toml`，使用 setuptools 的 PEP 621 配置。
2. 删除 `setup.py`。
3. 删除 `pytest.ini`，将 pytest 配置迁入 `pyproject.toml`。
4. 更新 README 的安装、测试、设计边界说明。
5. 更新 `skills/minbt-usage` 的安装、验证、数据 feed 说明。
6. 运行安装、测试和示例验证。

## 验收标准

1. `pip install -e .` 可基于 `pyproject.toml` 安装。
2. `python -m pytest` 全量通过。
3. `python -m compileall -q minbt tests examples` 通过。
4. `git diff --check` 通过。
