import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "script_path",
    [
        "examples/01_demo_mini.py",
        "examples/02_single_symbol_sma.py",
        "examples/03_multi_symbol_rotation.py",
        "examples/04_scenario_exit_rules.py",
        "examples/05_scenario_limit_order.py",
        "examples/06_scenario_single_breakout.py",
        "examples/07_scenario_multi_rotation.py",
        "examples/08_scenario_pairs_mean_reversion.py",
    ],
)
def test_examples_run_from_repo_root(script_path):
    """测试 README 中的示例命令可以从仓库根目录运行"""
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
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


def test_100k_benchmark_example_runs_without_logs():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "examples/09_benchmark_100k_empty.py"],
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
