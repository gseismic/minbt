import ast
import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from minbt import Bar

HEADLESS_ENV = {
    **os.environ,
    "MPLBACKEND": "Agg",
    # Python 3.8 可安装的 Matplotlib 使用旧警告文本；只屏蔽已知的无 GUI 提示。
    "PYTHONWARNINGS": (
        "ignore:FigureCanvasAgg is non-interactive:UserWarning,"
        "ignore:Matplotlib is currently using agg:UserWarning"
    ),
}


def test_every_example_has_inline_plot_and_show():
    repo_root = Path(__file__).resolve().parents[1]
    scripts = sorted((repo_root / "examples").glob("*.py"))

    assert scripts
    for script_path in scripts:
        tree = ast.parse(script_path.read_text(encoding="utf-8"))
        has_pyplot_import = any(
            isinstance(node, ast.Import)
            and any(
                alias.name == "matplotlib.pyplot" and alias.asname == "plt"
                for alias in node.names
            )
            for node in ast.walk(tree)
        )
        has_show_call = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "plt"
            and node.func.attr == "show"
            for node in ast.walk(tree)
        )

        assert has_pyplot_import and has_show_call, script_path.name


@pytest.mark.parametrize(
    "script_path",
    [
        "examples/01_quickstart.py",
        "examples/02_moving_average.py",
        "examples/03_rotation.py",
        "examples/04_exit_rules.py",
        "examples/05_limit_orders.py",
        "examples/06_breakout.py",
        "examples/07_rebalance.py",
        "examples/08_pairs_trading.py",
        "examples/09_cross_market.py",
        "examples/10_run_control.py",
        "examples/11_pnl.py",
        "examples/16_replay_modes.py",
        "examples/17_bar_storage.py",
        "examples/18_config_run.py",
    ],
)
def test_examples_run_from_repo_root(script_path):
    """测试安装 minbt 后 README 中的示例命令可从仓库根目录运行。"""
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=repo_root,
        env=HEADLESS_ENV,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "final_equity=" in result.stdout
    assert result.stderr == ""


def test_pnl_example_matches_independent_hand_calculation():
    """在测试中独立核对示例的库级结果，示例本身无需重复实现盈亏公式。"""
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "examples" / "11_pnl.py"
    spec = importlib.util.spec_from_file_location("example_11_pnl", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    results = module.run_scenarios()
    expected = {
        "long_profit": ([0.0, 10.0, 20.0], 20.0, 20.0, 0.0),
        "short_profit": ([0.0, 5.0, 10.0], 10.0, 10.0, 0.0),
        "fees_turn_small_gain_into_loss": ([-0.1, -0.15005], -0.15005, 0.05, 0.20005),
    }

    assert {result["name"] for result in results} == set(expected)
    for result in results:
        expected_curve, expected_final, expected_realized, expected_fees = expected[result["name"]]
        assert result["pnl_curve"] == pytest.approx(expected_curve)
        assert result["pnl"].net_pnl == pytest.approx(expected_final)
        assert result["pnl"].realized_pnl == pytest.approx(expected_realized)
        assert result["pnl"].unrealized_pnl == 0
        assert result["pnl"].fees == pytest.approx(expected_fees)
        assert sum(record.net_pnl for record in result["records"]) == pytest.approx(expected_final)
        assert result["final_equity"] == pytest.approx(1000.0 + expected_final)


def test_100k_benchmark_example_runs_without_logs():
    repo_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [sys.executable, "examples/12_benchmark.py"],
        cwd=repo_root,
        env=HEADLESS_ENV,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "rows=100000" in result.stdout
    assert "set_bars_seconds=" in result.stdout
    assert "run_seconds=" in result.stdout
    assert "total_seconds=" in result.stdout
    assert result.stderr == ""


def test_limit_order_example_cancels_before_price_reaches_limit():
    """独立核对撤单后不再成交，另一订单按限价成交、按最新价止盈。"""
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "example_05_limit_orders", repo_root / "examples" / "05_limit_orders.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    strategy, broker = module.run_strategy()

    assert strategy.canceled_order.status == "canceled"
    assert strategy.canceled_order.filled_qty == 0
    assert strategy.position_log[2][1:] == (96, 0)
    assert strategy.limit_order.status == "filled"
    assert strategy.limit_order.avg_price == 95
    assert broker.get_position_size(module.SYMBOL) == 0
    assert broker.get_total_equity() == pytest.approx(1010)
    assert broker.get_total_pnl().net_pnl == pytest.approx(10)


@pytest.mark.parametrize("mode", ["auto", "preload", "incremental"])
def test_replay_mode_example_matches_price_source_and_callback_order(mode):
    """三种读取方式遵守相同的数据族回调顺序，盈亏由自定义估值源更新。"""
    repo_root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "example_16_replay_modes", repo_root / "examples" / "16_replay_modes.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    strategy, broker = module.run(mode)

    assert strategy.callbacks == ["bars", "books", "price"] * 2
    assert strategy.get_hist_equity() == pytest.approx([10_000, 10_000.12])
    assert broker.get_last_price(module.SYMBOL) == pytest.approx(101.2)
    assert broker.get_position_size(module.SYMBOL) == pytest.approx(0.1)
    assert broker.get_total_pnl().net_pnl == pytest.approx(0.12)


def test_crypto_binance_feed_example_runs_with_fake_feed(monkeypatch, capsys):
    repo_root = Path(__file__).resolve().parents[1]
    script_path = repo_root / "examples" / "13_binance_feed.py"
    spec = importlib.util.spec_from_file_location("example_13_binance_feed", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FakeKlineFeed:
        name = "fake-binance-bars"
        feed_priority = 0
        supports_preload = True
        supports_incremental = True
        ordered = True
        replayable = True

        def __init__(self, *args, **kwargs):
            pass

        def events(self):
            for index, close in enumerate((100.0, 105.0, 110.0)):
                dt = datetime(2024, 1, 1, index, tzinfo=timezone.utc)
                yield Bar(
                    dt=dt,
                    symbol=module.SYMBOL,
                    kind="kline",
                    data={
                        "open": close,
                        "high": close,
                        "low": close,
                        "close": close,
                        "volume": 1.0,
                    },
                )

    monkeypatch.setattr(module, "KlineFeed", FakeKlineFeed)

    module.run_strategy()
    output = capsys.readouterr().out

    assert "final_equity=" in output
    assert "bar_count=3" in output
