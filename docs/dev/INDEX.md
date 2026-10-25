# 开发计划索引

本索引从 PLAN-059 开始维护；更早的计划和结果保留在 `docs/dev/` 中。

| 更新时间（Asia/Shanghai） | 计划 | 状态 | 结果 |
| --- | --- | --- | --- |
| 2026-10-25 | [PLAN-075：本地 K 线 Feed 支持 `*` 订阅全部 symbol](PLAN-075-symbol-wildcard-local-kline-feeds.md) | 已完成 | [结果](PLAN-075-symbol-wildcard-local-kline-feeds-OUTCOME.md)：CSV/iosql 支持独立 `*` 通配符，语法、ruff 与 diff 检查通过 |
| 2026-10-25 | [PLAN-074：增加 iosql 全部 symbol 示例](PLAN-074-iosql-all-symbols-example.md) | 已完成 | [结果](PLAN-074-iosql-all-symbols-example-OUTCOME.md)：新增 `symbols=None` iosql 遍历示例，语法、ruff 与 diff 检查通过 |
| 2026-10-12 14:38 | [PLAN-059：简化入门示例和文件命名](PLAN-059-simple-examples-model-unknown.md) | 已完成 | [结果](PLAN-059-simple-examples-model-unknown-OUTCOME.md)：首例 24 行，17 个示例改名，54 项相关测试通过 |
| 2026-10-12 15:22 | [PLAN-060：用户 Skill 随安装包发布](PLAN-060-package-skills.md) | 已完成 | [结果](PLAN-060-package-skills-OUTCOME.md)：包内唯一来源、定位入口与项目发现链接，发行物和仓库外安装验证通过，全量 334 项测试通过 |
| 2026-10-12 15:27 | [PLAN-061：配置 GitHub Actions 发布到 PyPI](PLAN-061-pypi-publish.md) | 已完成 | [结果](PLAN-061-pypi-publish-OUTCOME.md)：Release 触发、构建校验与 OIDC Trusted Publishing 流程及配置说明 |
| 2026-10-12 15:47 | [PLAN-062：更新至 v0.1.1 并提交发布准备](PLAN-062-release-v0-1-1.md) | 已完成 | [结果](PLAN-062-release-v0-1-1-OUTCOME.md)：版本和变更日志更新，PLAN-060/061 与本计划一并提交 |
| 2026-10-12 | [PLAN-063：mini 内核、协议集中与自备数据设计](PLAN-063-protocol-plugin-design.md) | 设计完成，实施见 PLAN-064 | [结果](PLAN-063-protocol-plugin-design-OUTCOME.md)：设计阶段无代码改动；复用 Exchange、自定义 Feed/Broker 直接注入，移除必需管理框架 |
| 2026-10-12 | [PLAN-064：实施 mini 协议、插件与自备数据入口](PLAN-064-mini-plugins-implementation.md) | 已完成 | [结果](PLAN-064-mini-plugins-implementation-OUTCOME.md)：13 模块迁入插件、标准协议与自备数据薄入口，整个包净增 399 行，全量 385 项通过，原示例/签名保留，仓库外安装验证通过 |
| 2026-10-12 | [PLAN-065：默认 Broker 归回核心，删除兼容层](PLAN-065-core-broker-no-compatibility.md) | 已完成 | [结果](PLAN-065-core-broker-no-compatibility-OUTCOME.md)：默认 Broker 回归核心、删除全部转发层，包减少 109 行，全量 373 项通过，默认回测不加载插件 |
| 2026-10-12 | [PLAN-066：示例、README 与使用 Skill 对齐](PLAN-066-examples-readme-skill-sync.md) | 已完成 | [结果](PLAN-066-examples-readme-skill-sync-OUTCOME.md)：修正交易/回调/结果语义，补齐撤单和模式比较，移除发行物测试旧目录依赖，全量 377 项及最终安装包检查通过 |
