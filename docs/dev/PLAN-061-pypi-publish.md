# PLAN-061：配置 GitHub Actions 发布到 PyPI

- 创建日期：2026-10-12（Asia/Shanghai）。
- 基准提交：`2c76c64`；此前工作区已有未提交改动，本计划只覆盖列出的文件。

## 目标和范围

为 minbt 建立可审查的 PyPI 自动发布流程。维护者发布 GitHub Release 后，Actions 校验 Release 标签与
`pyproject.toml` 版本一致，安装项目测试依赖并运行全量测试，构建 wheel 和 sdist，检查发行包，再由独立
job 使用 PyPI Trusted Publishing 上传。

新增 `.github/workflows/release.yml`。发布认证使用 GitHub OIDC，不保存 PyPI API Token；构建与发布分成
两个 job，只有发布 job 获得 `id-token: write`。README 说明 PyPI Trusted Publisher 和 GitHub Environment
的一次性配置，以及版本、标签和 Release 的操作顺序。不修改运行时 API、包元数据、版本号或既有用户改动。

## 实施步骤

1. [x] 核对现有构建配置、测试依赖和 Release 发布触发条件。
2. [x] 新增独立的 `release.yml`，完成测试、版本标签校验、构建、发行包检查和 OIDC 发布。
3. [x] 在 README 中说明 Trusted Publisher 配置及创建 Release 的步骤。
4. [x] 审阅工作流权限、触发范围、制品传递和文档步骤；修复发现的问题。
5. [x] 记录实施结果并更新开发索引。

## 完成标准

- 只有已发布的 GitHub Release 会启动 PyPI 流程。
- 版本标签必须严格匹配 `pyproject.toml` 中的版本（格式 `vX.Y.Z`），不匹配时在发布前失败。
- 全量测试、构建和 `twine check` 完成后，发布 job 才能下载发行物并上传。
- 仅发布 job 请求 OIDC 身份，PyPI 凭据不存入 GitHub Secrets。
- README 给出与该工作流文件名和环境名一致的首次配置步骤。

## 操作边界

- 本次只写仓库配置和文档，不在 PyPI 创建 Trusted Publisher，不创建 GitHub Environment，不发布版本。
- 不提交或推送工作区中的变更；当前工作区包含本计划以外的既有未提交改动。
