# Skill 随安装包发布设计

- 日期：2026-10-12。
- 状态：已实施；实施结果见 [PLAN-060 结果](../dev/PLAN-060-package-skills-OUTCOME.md)。

## 问题和目标

当前用户 skill 位于仓库根目录 `skills/minbt-usage/`，打包只发现 `minbt*`，普通安装无法得到这份资源。另行复制 skill 会使其与用户安装的 minbt 版本脱节。现有说明还引用仓库的设计稿、示例和测试，无法在只有安装包的环境中独立使用。

将面向用户策略开发的 skill 作为 minbt 包资源发布。用户使用项目实际运行的 Python 定位资源，安装、升级和降级时同时取得该版本的代码与说明。随包发布解决版本配套问题；接口变更仍须同步维护内容并通过发布验证。

## 内容与目录

```text
minbt/skills/
├── __init__.py
├── __main__.py
└── minbt-usage/
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── references/
    │   ├── data-and-control.md
    │   └── trading.md
    └── scripts/quickstart.py
```

主说明负责安装环境确认、核心流程、数据约定和验证入口；数据与运行控制、交易与盈亏细节分别按需读取。参考资料和最小脚本都随包发布，引用路径相对于 skill 目录。发布 skill 只描述已实现的接口，开发设计稿留在 `docs/design/`。

通用库设计 skill `skills/library-design-zh/` 服务于框架开发，继续留在开发目录。删除根目录的用户 skill 内容副本，仓库通过 `.agents/skills/minbt-usage` 的相对符号链接发现包内唯一来源。

## 定位入口

```bash
python -m minbt.skills
python -m minbt.skills --path
```

默认输出安装版本和 `minbt-usage` 的绝对目录；`--path` 只输出目录，便于其他工具读取或建立链接。`--help` 提供使用说明，未知参数按命令行标准返回非零状态。没有安装元数据的源码环境明确显示版本不可用，不硬编码第二份版本号。

Python 接口为 `minbt.skills.get_skill_path() -> pathlib.Path`，返回包含 `SKILL.md` 的实际目录。资源缺失时抛出 `FileNotFoundError`，提示重新安装，不回退到其他位置的 skill。路径由当前导入的包定位，普通 wheel 安装和 editable 开发安装使用相同入口。版本从当前环境的发行元数据读取；源码开发应先完成 editable 安装，使元数据对应当前源码。

## 打包与发现

沿用 setuptools。显式声明 skill 的 Markdown、YAML 和示例脚本为 package-data。关闭隐式命名空间扫描，带连字符的 skill 目录和参考资料目录只作为资源，不作为 Python 子包。

普通安装资源位于当前环境的 `site-packages/minbt/skills/minbt-usage/`；editable 安装指向源码中的同一目录。资源为只读使用，不自动复制或写入用户全局 skill 目录。

Codex 本地发现通过 `.agents/skills/` 等受支持的目录接入，并支持符号链接。消费项目可将项目级链接指向 `--path` 输出；同一环境普通安装升级或降级后链接继续指向该环境的资源，更换环境或切换普通/editable 安装时重新建立链接。仓库内链接直接指向当前源码。

依据：[Setuptools 包资源文档](https://setuptools.pypa.io/en/stable/userguide/datafiles.html)、[OpenAI 本地 skill 文档](https://learn.chatgpt.com/docs/build-skills)。

## 验收与发布要求

1. 从干净源码副本构建 wheel 和 sdist，再从 sdist 构建 wheel，三者包含全部 skill 资源；不包含通用开发 skill。
2. 在仓库外安装并读取资源，验证路径来自安装目录、版本与安装元数据一致，而不是仓库的源码。
3. 在仓库外执行随包最小脚本，只用核心依赖和内联行情，得到最终权益 1020。
4. 验证 CLI 默认输出、纯路径输出、帮助和错误参数，并验证 skill 的相对引用完整。
5. 完成 skill 元数据校验、相关及全量测试、Ruff 与差异检查。

后续公开接口变化时，应同步更新 skill 与可执行示例。新增资源类型或目录层级时，应更新打包配置；完整资源比对测试会发现未进入发行物的文件。
