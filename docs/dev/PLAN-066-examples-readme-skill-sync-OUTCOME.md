# PLAN-066：示例、README 与使用 Skill 对齐结果

- 日期：2026-10-12（Asia/Shanghai）。
- 状态：已完成，改动已自行 review。
- 对应计划：[PLAN-066](PLAN-066-examples-readme-skill-sync.md)。
- 核查范围：当前 18 个示例、README、随包 Skill 及其两份参考资料和最小脚本。

## 发现与修正

1. 公开导入已使用当前 `minbt.plugins.binance` / `minbt.plugins.storage` 路径；手工装配与配置入口均可运行，保留现有写法。
2. 区分手工 Strategy 的必填 `strategy_id` 与配置入口省略 ID 时使用类名；说明配置入口传入构造函数的四个参数。修正省略必填资金的 Broker 用法表述。
3. 说明完整时间批次先更新账户，但策略截面按 Feed 分别回调；补充来源内重复校验、优先级排序、最小 Feed 与 auto 模式的能力要求。
4. 明确限价单按最新价触发、以提交限价成交；市价单显式价格也会更新当前最新价，后续批次仍按配置的 mark_price 估值。
5. `clear_exit()` 默认清除全部条件；README 和交易参考示例显式将其他清除开关设为 False，使示例只清除追踪止损。
6. 说明权益/总盈亏覆盖全账户，持仓曲线只记录 main，其他分仓可查询最终持仓；补充自定义账户缺少可选能力时的结果异常。
7. 核对 A 股示例的日期行情适用 allow_daily_bar 规则，补充工作日午夜日线与节假日处理边界；原示例无需更改。
8. 限价单示例增加撤单，撤销限价 97 的挂单后最新价跌至 96 仍无成交；另一限价 95 的单在最新价 94 时以 95 成交，最终 105 止盈，净盈亏 10。
9. 回放模式示例实际分别创建全新对象运行 auto/preload/incremental，并输出 bars/books/price 回调顺序与估值结果；移除无操作的资源钩子和不需要显式声明的 replayable。
10. README 删除已移除的 `skills/library-design-zh` 指引，改为当前协议设计文档；发行物测试只复制实际包源码，不再依赖已删除的根目录 skills。

保留工作区原有三个开发 Skill 文件的删除改动，没有修改框架实现、公开接口、项目版本或依赖。

## 验证

- 全量 `uv run --no-project python -m pytest -q --tb=short`：**377 passed in 186.46s**。新增 4 项验证撤单后的成交结果及三种回放模式的价格来源、曲线和回调顺序。
- 18 个示例均完成核查：离线脚本和基准由现有测试执行；Binance 下载示例使用模拟 Feed；CSV、iosql 示例额外使用临时 CSV 与真实 iosql 数据库运行，均得到权益 10072、净盈亏 72。
- README/Skill 共 55 个 Python 代码块语法及 32 个本地链接通过；最小回测、MemoryFeed 配置与 Skill 配置片段实际执行，权益 1020、净盈亏 20。
- README/交易参考的选择性 clear_exit 片段实际执行，固定止损、止盈和自定义条件保留，仅追踪止损被清除。
- Skill 格式校验、Ruff 与差异空白检查通过。随包最小脚本输出 `final_equity=1020.00`。
- 最后补充当前估值更新说明后，重新验证最终资源：`tests/test_skill_packaging.py` **6 passed in 28.49s**；wheel、sdist、sdist 重建 wheel 的全部 Skill 资源与源码一致，仓库外安装运行通过。
- 所有示例与修改测试通过 Python 3.8 AST 语法检查；未在 Python 3.8 解释器下运行全套测试。

仅核对当前仓库内容和可执行行为，未请求外部行情或个人数据库；无需修改历史版本资料。
