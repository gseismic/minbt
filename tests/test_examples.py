import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "script_path",
    [
        "examples/demo_mini.py",
        "examples/single_symbol_sma.py",
        "examples/multi_symbol_rotation.py",
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
