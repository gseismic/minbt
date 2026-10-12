# PLAN-060：用户 Skill 随安装包发布结果

- 日期：2026-10-12（Asia/Shanghai）。
- 状态：已完成，变更位于 WORKTREE。
- 计划：[PLAN-060](PLAN-060-package-skills.md)。
- 设计：[Skill 随安装包发布](../design/skills-20261012-packaging.md)。

## 实施结果

1. 将 `skills/minbt-usage/` 迁移到 `minbt/skills/minbt-usage/`，保留一份用户 skill 内容。
2. 主说明改为只描述安装版本已实现的能力。交易/盈亏和数据/控制分别放入相对路径参考资料，
   移除开发设计稿、仓库示例和仓库测试的必需引用。更新 UI 元数据。
3. 新增 `scripts/quickstart.py`，只使用核心依赖和两条内联行情，无需绘图或外部数据。
4. 新增 `minbt.skills.get_skill_path()`、`python -m minbt.skills` 和 `--path`。默认读取当前环境的
   发行版本元数据并显示绝对资源目录；纯路径模式可供工具使用；安装资源缺失时报错。
5. setuptools 显式收集 skill 的 Markdown、YAML、Python 脚本。关闭隐式命名空间扫描，
   保留既有真实 Python 包，skill 数据目录不成为子包。
6. 新增仓库 `.agents/skills/minbt-usage` 相对链接，指向包内唯一来源。README 说明消费项目
   的环境绑定、链接创建和发行验证。通用库设计 skill 继续位于 `skills/library-design-zh/`。
7. 增加 6 项打包与安装回归检查。`dev` 增加 build 和 pip，用于隔离构建及临时目录真实安装；
   核心运行依赖和 minbt 版本仍保持原有配置。

## 审阅修正

- 核对实际回调实现，将逐笔成交明确为 `{symbol: [row, ...]}`，新闻载荷明确为 News 元组，
  避免发布错误的数据契约。
- 测试按 tarfile 是否支持过滤器选择解压方式，兼容 Python 3.8 并消除新版本的解压弃用警告。
- 安装测试验证未知 CLI 参数、缺少资源时明确失败，不回退到工作区或旧的全局 skill。
- 普通安装与 editable 安装的路径不同，README 明确切换安装模式后需要重新建立消费项目链接。

## 验证证据

```text
uv run --no-project python -m pytest -q
334 passed in 44.13s

ruff check minbt/skills tests/test_skill_packaging.py
All checks passed!

quick_validate.py minbt/skills/minbt-usage
Skill is valid!

python -m minbt.skills
minbt 0.1.0
skill: /home/lsl/macbook/pai-studio-fin/library/minbt/minbt/skills/minbt-usage

python minbt/skills/minbt-usage/scripts/quickstart.py
final_equity=1020.00
```

发行回归从干净副本构建 wheel、sdist 与 sdist 派生 wheel，完整比对 5 个 skill 资源的字节内容。
两种 wheel 使用 pip 安装到临时目录，仓库外的子进程确认 minbt 模块与 skill 路径来自安装目录，
再执行 skill 内脚本和主说明中的最小 Python 示例。两者都返回最终权益 1020，全部相对引用存在。
回归安装复用当前测试环境的运行依赖，不要求下载外部行情或数据文件。

额外使用临时虚拟环境验证普通安装、升级、降级及 editable 安装：

- 当前源码构建的 0.1.0 安装到临时环境，消费项目链接可读取 skill 并运行示例。
- 仅在临时副本中制作 0.1.1 验证包，给 skill 增加标记和一份参考资料。升级后版本显示 0.1.1，
  同一项目链接读到新内容；降级回 0.1.0 后内容恢复，新增参考资料随卸载移除。
- 临时 editable 安装的定位结果指向其源码目录，显示 0.1.0，仓库外最小回测仍返回 1020。
- editable 首次隔离构建的依赖准备超时，随后复用本机已安装的构建后端，使用
  `uv pip install --no-build-isolation --no-deps --editable ...` 完成验证。
  临时 0.1.1 包未发布，也未修改项目版本。

新增 Python 文件通过 Python 3.8 语法解析检查；当前执行环境为 Python 3.12，未实跑完整 Python 3.8 环境。
`agents/openai.yaml` 的简述长度与 skill 引用检查通过，`git diff --check` 通过。

## 发布维护

此功能会进入后续构建的安装包。后续公开接口变化时应同步更新 skill 与可执行示例，并执行
`tests/test_skill_packaging.py`。新增资源类型或目录层级时同步修改 package-data；完整资源比对会检测漏打包。
源码中携带 skill 保证版本配套，内容与 API 的语义一致仍需随接口改动维护。
