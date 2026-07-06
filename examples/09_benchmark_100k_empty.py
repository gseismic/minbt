from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd

from minbt import Exchange, Strategy


N_DT = 10_000
N_SYMBOLS = 10
N_ROWS = N_DT * N_SYMBOLS


class EmptyStrategy(Strategy):
    pass


def build_data():
    symbols = [f"S{i:03d}" for i in range(N_SYMBOLS)]
    rows = []
    start_dt = pd.Timestamp("2026-01-01")
    for i in range(N_DT):
        dt = (start_dt + pd.Timedelta(minutes=i)).isoformat()
        for j, symbol in enumerate(symbols):
            rows.append(
                {
                    "dt": dt,
                    "symbol": symbol,
                    "close": 100.0 + i * 0.01 + j,
                }
            )
    return pd.DataFrame(rows)


def run_benchmark():
    t0 = time.perf_counter()
    data = build_data()
    build_seconds = time.perf_counter() - t0

    exchange = Exchange()
    strategy = EmptyStrategy(strategy_id="empty_100k")

    t1 = time.perf_counter()
    exchange.set_bars(data)
    set_bars_seconds = time.perf_counter() - t1

    exchange.add_strategy(strategy)

    t2 = time.perf_counter()
    exchange.run()
    run_seconds = time.perf_counter() - t2

    total_seconds = time.perf_counter() - t0

    print(f"rows={N_ROWS}")
    print(f"symbols={N_SYMBOLS}")
    print(f"datetimes={N_DT}")
    print(f"build_data_seconds={build_seconds:.4f}")
    print(f"set_bars_seconds={set_bars_seconds:.4f}")
    print(f"run_seconds={run_seconds:.4f}")
    print(f"total_seconds={total_seconds:.4f}")


if __name__ == "__main__":
    run_benchmark()
