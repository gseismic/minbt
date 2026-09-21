# PLAN-044：增加可手算的盈亏曲线示例——实施结果

## 实施结果

已完成可手算盈亏示例和端到端正确性校验，未修改 Broker、Portfolio、Position 的计算逻辑或公共 API。

### 新增示例

文件：`examples/00_pnl_sanity_check.py`

包含三个离线场景：

- 多头：`100 -> 110 -> 120`，数量 `1`，理论净盈亏 `+20`。
- 空头：`100 -> 95 -> 90`，数量 `-1`，理论净盈亏 `+10`。
- 手续费：`100 -> 100.05`，数量 `1`，手续费率 `0.001`，理论净盈亏 `-0.15005`。

示例将 `权益 - 初始资金`作为净盈亏曲线，输出毛盈亏、手续费、理论净盈亏、实际净盈亏和最终权益，
并把曲线保存到被 git 忽略的 `examples/screenshots/00_pnl_sanity_check.png`。

### 新增测试

- `tests/test_examples.py`：验证示例脚本可从仓库根目录运行，并独立断言三条盈亏曲线和最终结果。
- `tests/test_pnl.py`：通过 Broker 公共接口验证多头、空头和手续费后的往返交易总权益。

### 文档

- `docs/design/pnl-20260920-examples.md`：设计和盈亏口径。
- `README.md`：增加示例入口、净盈亏曲线计算方式和专项测试命令。
- `skills/minbt-usage/SKILL.md`：增加盈亏校验示例及使用说明。
- `docs/design/README.md`：登记设计文档。

## 验证结果

```text
python examples/00_pnl_sanity_check.py
多头盈利: gross_pnl=20.00000, fees=0.00000, expected_pnl=20.00000, actual_pnl=20.00000
空头盈利: gross_pnl=10.00000, fees=0.00000, expected_pnl=10.00000, actual_pnl=10.00000
手续费覆盖小幅上涨: gross_pnl=0.05000, fees=0.20005, expected_pnl=-0.15005, actual_pnl=-0.15005

python -m pytest -q tests/test_pnl.py tests/test_examples.py
16 passed

python -m pytest -q
213 passed

python -m compileall -q minbt examples tests
passed

git diff --check
passed
```

## Review 结论

1. 示例使用现有 `Strategy.get_hist_equity()` 和 `Broker` 公共接口，用户可以直接对照手算公式定位方向或手续费问题。
2. 持仓期间曲线表示按最新价盯市的净盈亏，最终平仓值包含开仓和平仓手续费。
3. 图表使用 ASCII 文本，避免不同环境缺少中文字体时向示例测试的 stderr 写入字体告警。
4. 工作区中原有未提交的 `HANDOFF.md` 和 `docs/review/review-20260920-round6.md` 未修改。
