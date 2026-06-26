---
name: minbt-usage
description: Use when building, reviewing, debugging, or documenting minbt backtests and strategies in this repository. Trigger for tasks involving Exchange, Strategy, Broker, Portfolio, Position, market orders, cross or isolated margin, portfolio equity, OHLCV data loading, examples, tests, README updates, or minbt usage guidance.
---

# minbt Usage

## Core Workflow

1. Inspect current code before changing behavior: start from `minbt/exchange.py`, `minbt/strategy.py`, `minbt/broker/broker.py`, `minbt/broker/portfolio.py`, and `minbt/broker/struct.py`.
2. For user-facing usage, read `README.md` and `examples/demo_mini.py` before writing examples.
3. For behavior changes, add focused tests under `tests/` and run the relevant tests plus `pytest -q`.
4. Follow `AGENTS.md`: write Chinese docs under `docs/dev/PLAN-XXX-*.md` and `*-OUTCOME.md` for implementation work.

## Data Contract

- `Exchange.set_data(data, date_key=None)` accepts pandas DataFrame, polars DataFrame, or `list[dict]`.
- Required fields are `symbol` and `close`.
- If `date_key` is provided, data is sorted by `[date_key, symbol]`.
- If `date_key` is omitted, data must contain exactly one symbol and row index is used as the time key.
- During `Exchange.run()`, broker prices are updated before `Strategy.on_data(row)` is called.

## Strategy Pattern

Prefer this structure for examples:

```python
from minbt import Broker, Exchange, Strategy


class MyStrategy(Strategy):
    def on_init(self):
        self.orders = 0

    def on_data(self, row):
        symbol = row["symbol"]
        price = row["close"]
        if self.orders == 0:
            self.broker.submit_market_order(symbol, qty=1, price=price)
        self.orders += 1

    def on_finish(self):
        print(self.broker.get_total_equity())
```

Use `qty > 0` for buy or long exposure and `qty < 0` for sell or short exposure. Reversal orders close existing exposure first and open the remaining opposite exposure.

## Broker Semantics

- `Broker(initial_cash, fee_rate, portfolio_cash=None, leverage=1.0, margin_mode="cross")` creates a default portfolio.
- `broker.add_sub_portfolio(id, initial_cash)` allocates cash from `remaining_free_cash`.
- `broker.get_total_equity()` returns all portfolio equity plus unallocated cash.
- `broker.get_all_portfolio_equity()` excludes unallocated cash.
- `broker.get_equity(portfolio_id=None)` returns one portfolio, defaulting to the main portfolio.
- `broker.submit_market_order(symbol, qty, price=None, leverage=None, portfolio_id="default")` uses the last known price when `price` is omitted.

## Margin Semantics

- Fee is `abs(qty) * price * fee_rate`.
- Required margin is `abs(qty) * price / leverage`.
- Isolated margin checks each position's `equity / margin`.
- Cross margin checks account-level `portfolio_equity / total_margin`; free cash is part of the risk buffer.
- Cross bankruptcy zeroes that portfolio's cash and clears positions.

## Tests And Validation

Use targeted tests first, then full validation:

```bash
pytest -q tests/test_exchange.py tests/test_strategy.py tests/test_broker.py
pytest -q tests/test_portfolio.py tests/test_portfolio2.py tests/test_position.py
pytest -q
python -m compileall -q minbt tests
git diff --check
```

The current environment may emit `Polars binary is missing!`; treat it as an environment warning unless a test fails.

## Documentation Updates

- Keep user docs in Chinese unless the user asks otherwise.
- For README examples, show complete runnable snippets with local in-memory data when possible.
- Mention current limitations: limit orders, stop orders, stop-loss/take-profit, slippage, and order-book simulation are not implemented.
