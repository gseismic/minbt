from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd

from minbt import Exchange, Strategy

_SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"


def _save_fig(name):
    _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    p = _SCREENSHOT_DIR / f"{name}.png"
    plt.tight_layout(pad=1.5)
    plt.savefig(str(p), dpi=150, bbox_inches="tight")
    print(f"[plot] saved: {p}")
    plt.close()


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

    # ── 绘图：基准测试耗时 ──
    labels = ["build_data", "set_bars", "run", "total"]
    values = [build_seconds, set_bars_seconds, run_seconds, total_seconds]
    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(labels, values, color="steelblue", edgecolor="white", linewidth=0.5)
    ax.set_title(f"09 Benchmark — {N_ROWS:,} rows ({N_DT:,} dt × {N_SYMBOLS} symbols)", fontsize=13, fontweight="bold")
    ax.set_ylabel("Seconds")
    ax.grid(True, alpha=0.3, axis="y")
    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(values) * 0.02, f"{val:.3f}s", ha="center", va="bottom", fontsize=10)
    _save_fig("09_benchmark_100k_empty")


if __name__ == "__main__":
    run_benchmark()
