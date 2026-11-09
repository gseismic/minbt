# 许可证元数据修复结果

- 时间：2026-11-10 03:57（Asia/Shanghai）
- 执行模型：GPT-6（环境未提供更精确的实际模型 ID）
- 范围：WORKTREE，基准提交 48ec9fa4e6287cf95b8f03e7223e8c989d6b2ef3；变更包括 `pyproject.toml`、`setup.cfg` 和本计划及结果、索引文件，尚未提交。
- 计划：`docs/plans/PLAN-20261110-001-model-unknown-license-metadata.md`

## 完成情况与计划偏差

使用 setuptools 动态读取 `setup.cfg` 中的 MIT 许可证元数据，保留 Python >=3.8 声明，并把构建依赖下限调整为 75.3.2。与直接使用 PEP 639 字符串不同，产物使用传统的 `License: MIT` 字段，以支持 Python 3.8 上的旧版构建工具。可编辑安装提示仍由 setuptools 决定，未修改。

## 验证

- Python 3.11 的隔离环境中可编辑安装成功，未出现许可证表弃用警告。
- 新版 setuptools 和 setuptools 75.3.2 均成功构建 wheel；产物包含 MIT 许可证元数据及 LICENSE 文件。
- sdist 包含 `setup.cfg` 和 LICENSE；从 sdist 构建的 wheel 包含 MIT 元数据和 LICENSE。
- pip 以 Python 3.8 为目标解析到 setuptools 75.3.4；本机没有 Python 3.8 解释器，因此未在 Python 3.8 上实际构建。
- setuptools 61.0.0 无法展开动态许可证字段，已提高下限以排除该版本。
- `git diff --check` 通过。

## 遗留事项

未在真实 Python 3.8 环境执行安装；现有 release workflow 包含 Python 3.8 验证。无其他已知遗留事项。
