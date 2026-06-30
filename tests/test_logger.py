import os
import subprocess
import sys
from pathlib import Path

from loguru import logger as raw_logger

from minbt.logger import logger


def _run_minimal_exchange():
    import pandas as pd

    from minbt import Broker, Exchange, Strategy

    class DemoStrategy(Strategy):
        def on_bars(self, dt, bars):
            price = bars["BTCUSDT"]["close"]
            self.broker.order_target_percent("BTCUSDT", 0.5, price=price)

    data = pd.DataFrame([
        {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
    ])
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = DemoStrategy(strategy_id="demo", broker=broker)
    exchange = Exchange()
    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()


def test_minbt_logger_is_loguru_logger():
    assert logger is raw_logger


def test_minbt_internal_logs_are_silent_by_default_in_subprocess():
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root) + os.pathsep + env.get("PYTHONPATH", "")
    code = """
import pandas as pd
from minbt import Broker, Exchange, Strategy

class DemoStrategy(Strategy):
    def on_bars(self, dt, bars):
        price = bars["BTCUSDT"]["close"]
        self.broker.order_target_percent("BTCUSDT", 0.5, price=price)

data = pd.DataFrame([
    {"dt": "2026-01-01", "symbol": "BTCUSDT", "close": 100.0},
])
broker = Broker(initial_cash=1000, fee_rate=0)
strategy = DemoStrategy(strategy_id="demo", broker=broker)
exchange = Exchange()
exchange.set_bars(data)
exchange.add_strategy(strategy)
exchange.run()
"""

    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=repo_root,
        env=env,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_minbt_logger_can_be_enabled_with_loguru():
    records = []
    sink_id = logger.add(lambda message: records.append(str(message)), format="{message}")
    try:
        logger.enable("minbt")
        _run_minimal_exchange()
    finally:
        logger.disable("minbt")
        logger.remove(sink_id)

    assert any("Start running 1 strategies" in record for record in records)
    assert any("Submit order: BTCUSDT" in record for record in records)


def test_minbt_logger_can_write_to_file(tmp_path):
    log_path = tmp_path / "minbt.log"
    sink_id = logger.add(log_path, format="{message}")
    try:
        logger.enable("minbt")
        _run_minimal_exchange()
    finally:
        logger.disable("minbt")
        logger.remove(sink_id)

    output = log_path.read_text()
    assert "Start running 1 strategies" in output
    assert "Submit order: BTCUSDT" in output


def test_custom_logger_injection_still_works():
    class CaptureLogger:
        def __init__(self):
            self.records = []

        def info(self, message):
            self.records.append(message)

    from minbt import Exchange

    capture = CaptureLogger()
    exchange = Exchange(logger=capture)
    exchange.logger.info("custom output")

    assert capture.records == ["custom output"]
