# v1 参考备份

日期：2026-10-23。关联 [PLAN-071](../../dev/PLAN-071-backtest-first-design.md)。

本目录同时保存回退前的工作区和用户指定的基线提交，避免丢失未提交实现。
使用压缩快照，避免旧测试被 pytest 自动收集、旧源码被误当成当前实现。

| 文件 | 内容 |
| --- | --- |
| [worktree-before-rollback.tar.gz](worktree-before-rollback.tar.gz) | 回退前实际工作区，共 352 个文件，包括第六版设计、复杂实盘实现、PLAN-069 数值修复、未跟踪源码/测试和 GOAL/BRAIN |
| [baseline-6c1e7a0.tar.gz](baseline-6c1e7a0.tar.gz) | `6c1e7a01c56578728bc44cf6e382659bac069a8f` 的完整 Git 快照，307 个普通文件及原有符号链接 |
| [manifest.json](manifest.json) | 原 HEAD、恢复目标、每个工作区文件的 SHA-256/链接目标与两个压缩包的 SHA-256 |
| [unstaged.patch](unstaged.patch) / [staged.patch](staged.patch) | 备份时相对 HEAD 的差异；未跟踪文件保存在工作区快照，不能只用 patch 恢复 |
| [status-before.txt](status-before.txt) | 回退前 Git 状态 |
| [rollback-verification.json](rollback-verification.json) | 已核验的恢复范围、91 个基线文件与备份后删除的 34 个新增文件 |

两个快照均已重新打开并逐文件校验；工作区快照与原文件逐项匹配，基线快照与 git show 匹配。
不包含 `.git`、被 Git 忽略的环境/凭证/缓存/构建产物。Git 提交历史保持原样，HEAD 仍为 `76b6d7a`。

当前工作代码、示例、测试、README 和包配置与目标提交一致；设计和交接另行更新。
PLAN-069 的后续数值修复也随精确回退撤出，留存在工作区快照，未混入目标基线。
外部 crypto_api 仓库未修改，其历史补丁不属于本次回退范围。

查看归档内容：

```bash
tar -tzf docs/ref/v1/worktree-before-rollback.tar.gz
```

需要参考旧实现时，在独立空目录解压，不覆盖当前工作树：

```bash
mkdir -p /tmp/minbt-v1-reference
tar -xzf docs/ref/v1/worktree-before-rollback.tar.gz -C /tmp/minbt-v1-reference
```

当前有效方向见 [第七版设计](../../design/live-trading-20261023-design.md)。归档中的计划、测试结果和交接均为历史记录。
