# PLAN-061：配置 GitHub Actions 发布到 PyPI 结果

- 日期：2026-10-12（Asia/Shanghai）。
- 状态：已完成，变更位于 WORKTREE。
- 计划：[PLAN-061](PLAN-061-pypi-publish.md)。

## 实施结果

1. 新增 `.github/workflows/release.yml`，只在 GitHub Release 发布后启动流程。
2. 构建 job 使用 Python 3.12 安装 `.[dev,plot]` 与 Twine，先检查 Release 标签必须等于
   `pyproject.toml` 版本的 `vX.Y.Z`，再运行全量测试、构建 wheel/sdist、执行 `twine check --strict`。
3. 构建 job 将发行物作为 Actions artifact 保存；独立发布 job 下载同一份发行物并调用
   `pypa/gh-action-pypi-publish`。只有发布 job 请求 `id-token: write`，并绑定 `pypi` 环境。
4. README 增加发布操作说明，列出 GitHub Environment 与 PyPI Trusted Publisher 的 owner、repository、
   workflow 和 environment 配置值；无需在 GitHub Secrets 保存 PyPI API Token。
5. 更新 `docs/dev/INDEX.md`，登记计划和结果。

## 审阅记录

- 检查触发条件为 `release.published`；标签与项目版本不一致时会在构建阶段失败，无法进入发布 job。
- 检查 `publish` 依赖 `build` 成功，并仅消费已构建与检查过的 artifact。
- 检查 OIDC 权限限定在发布 job，工作流默认仅有 `contents: read`。
- 审阅时将 artifact 下载动作修正为 `actions/download-artifact@v8`，与当前 GitHub Actions artifact 工作流版本一致。
- 本地未触发 GitHub Release 工作流，也未上传 PyPI。完整联调需要先在 PyPI 配置 Trusted Publisher、在 GitHub
  配置 `pypi` 环境，再创建一个版本匹配的 GitHub Release。

## 发布步骤

1. 更新 `pyproject.toml` 中的版本并推送代码。
2. 按 `vX.Y.Z` 创建并发布 GitHub Release，标签与项目版本保持一致。
3. Actions 自动完成测试、构建和发行包检查，通过后上传到 PyPI。
