# PLAN-062：更新至 v0.1.1 并提交发布准备结果

- 日期：2026-10-12（Asia/Shanghai）。
- 状态：已完成。
- 计划：[PLAN-062](PLAN-062-release-v0-1-1.md)。

## 实施结果

1. 将 `pyproject.toml` 的项目版本由 `0.1.0` 更新为 `0.1.1`。
2. 在 README ChangeLog 中记录 `minbt-usage` 随安装包发布、资源定位入口、发行物回归测试和 PyPI Trusted
   Publishing 工作流。
3. 将 PLAN-060 的 skill 打包实现、PLAN-061 的 PyPI 发布工作流、各自计划与结果，以及 v0.1.1 版本更新，
   一并纳入本地中文 commit。
4. 更新 `docs/dev/INDEX.md`，记录本计划和结果。

## 审阅与提交范围

- 核对现有工作区改动均属于 PLAN-060、PLAN-061 和 v0.1.1 发布准备。
- `git diff --check` 通过；未运行测试，未触发 GitHub Release、PyPI 上传或推送远程分支。
- 提交包含对应的三个计划文件和三个结果文件，具体变更在 commit message 中逐条列明。
