import os
import importlib.util
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from minbt import Bar


@pytest.mark.parametrize(
    "script_path",
    [
        "examples/000_core_pnl_sanity_check.py",
        "examples/001_core_demo_mini.py",
        "examples/002_core_single_symbol_sma.py",
        "examples/003_core_multi_symbol_rotation.py",
        "examples/100_scenario_exit_rules.py",
        "examples/101_scenario_limit_order.py",
        "examples/102_scenario_single_breakout.py",
        "examples/103_scenario_multi_rotation.py",
        "examples/104_scenario_pairs_mean_reversion.py",
        "examples/105_scenario_cross_market.py",
        "examples/400_exchange_replay_modes.py",
        "examples/401_exchange_generic_bar_storage.py",
    ],
)
def test_examples_run_from_repo_root(script_path):
    """测试安装 minbt 后 README 中的示例命令可从仓库根目录运行。"""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["MINBT_EXAMPLE_SHOW"] = "0"
    result = subprocess.run(
        [sys.executable, script_path],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "final_equity=" in result.stdout
    assert result.stderr == ""


def test_pnl_sanity_example_matches_independent_hand_calculation(monkeypatch):
    """盈亏示例的曲线和最终结果必须符合独立手算值。"""
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root / "examples"))
    script_path = repo_root / "examples" / "000_core_pnl_sanity_check.py"
    spec = importlib.util.spec_from_file_location("example_000_core_pnl_sanity_check", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    results = module.run_scenarios(make_plot=False)
    expected = {
        "long_profit": ([0.0, 10.0, 20.0], 20.0),
        "short_profit": ([0.0, 5.0, 10.0], 10.0),
        "fees_turn_small_gain_into_loss": ([-0.1, -0.15005], -0.15005),
    }

    assert {result["name"] for result in results} == set(expected)
    for result in results:
        expected_curve, expected_final = expected[result["name"]]
        assert result["pnl"] == pytest.approx(expected_curve)
        assert result["actual_pnl"] == pytest.approx(expected_final)
        assert result["final_equity"] == pytest.approx(1000.0 + expected_final)


def test_100k_benchmark_example_runs_without_logs():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["MINBT_EXAMPLE_SHOW"] = "0"
    result = subprocess.run(
        [sys.executable, "examples/200_benchmark_100k_empty.py"],
        cwd=repo_root,
        env=env,
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


def test_crypto_binance_feed_example_runs_with_fake_feed(monkeypatch, capsys):
    monkeypatch.setenv("MINBT_EXAMPLE_SHOW", "0")
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.syspath_prepend(str(repo_root / "examples"))
    script_path = repo_root / "examples" / "300_feed_crypto_binance.py"
    spec = importlib.util.spec_from_file_location("example_300_feed_crypto_binance", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    class FakeBinanceKlineFeed:
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

    monkeypatch.setattr(module.binance, "BinanceKlineFeed", FakeBinanceKlineFeed)

    module.run_strategy()
    output = capsys.readouterr().out

    assert "final_equity=" in output
    assert "bar_count=3" in output
