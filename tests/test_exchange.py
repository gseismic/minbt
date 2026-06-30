import pandas as pd
import polars as pl
import pytest

from minbt import Broker, Exchange, Strategy


class EmptyDataStrategy(Strategy):
    def on_init(self):
        self.initialized = True

    def on_finish(self):
        self.finished = True


class MultiAssetStrategy(Strategy):
    def on_init(self):
        self.snapshots = []

    def on_bars(self, dt, bars):
        self.snapshots.append(
            (
                dt,
                list(bars.keys()),
                self.broker.get_last_price("A"),
                self.broker.get_last_price("B"),
                self.exchange.get_current_dt(),
            )
        )


class DtCaptureStrategy(Strategy):
    def on_init(self):
        self.dts = []

    def on_bars(self, dt, bars):
        self.dts.append(self.exchange.get_current_dt())


class PriceCaptureStrategy(Strategy):
    def on_init(self):
        self.prices = []

    def on_bars(self, dt, bars):
        self.prices.append(bars["A"]["close"])


class MultiFeedStrategy(Strategy):
    def on_init(self):
        self.calls = []

    def on_bars(self, dt, bars):
        self.calls.append(("bars", dt, list(bars.keys()), self.broker.get_last_price("A")))

    def on_books(self, dt, books):
        self.calls.append(("books", dt, list(books.keys()), self.broker.get_last_price("A")))

    def on_trades(self, dt, trades):
        self.calls.append(("trades", dt, list(trades.keys()), self.broker.get_last_price("A")))

    def on_news(self, dt, news):
        self.calls.append(("news", dt, len(news), self.broker.get_last_price("A")))


class CountingBroker(Broker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.price_updates = []

    def on_new_price(self, symbol, price, dt=None):
        self.price_updates.append((symbol, price, dt))
        return super().on_new_price(symbol, price, dt)


def _duplicate_bar_rows():
    return [
        {"dt": "2026-01-01", "symbol": "A", "close": 100.0},
        {"dt": "2026-01-01", "symbol": "A", "close": 101.0},
    ]


def _make_duplicate_bar_data(kind):
    rows = _duplicate_bar_rows()
    if kind == "pandas":
        return pd.DataFrame(rows)
    if kind == "polars":
        try:
            return pl.DataFrame(rows)
        except Exception as exc:
            pytest.skip(f"polars DataFrame unavailable: {exc}")
    return rows


def _make_multi_asset_data(kind):
    rows = [
        {"dt": "2026-01-02", "symbol": "B", "close": 190.0},
        {"dt": "2026-01-01", "symbol": "B", "close": 200.0},
        {"dt": "2026-01-02", "symbol": "A", "close": 110.0},
        {"dt": "2026-01-01", "symbol": "A", "close": 100.0},
    ]
    if kind == "pandas":
        return pd.DataFrame(rows)
    if kind == "polars":
        try:
            return pl.DataFrame(rows)
        except Exception as exc:
            pytest.skip(f"polars DataFrame unavailable: {exc}")
    return rows


class PandasLikeData:
    columns = ["dt", "symbol", "close"]

    def __init__(self, rows):
        self.rows = rows
        self.to_dict_calls = 0

    def to_dict(self, orient):
        assert orient == "records"
        self.to_dict_calls += 1
        return self.rows

    def iterrows(self):
        raise AssertionError("iterrows should not be called when to_dict('records') is available")


def test_exchange_run_empty_bars_does_not_divide_by_zero():
    exchange = Exchange()
    strategy = EmptyDataStrategy(strategy_id="empty", broker=Broker(initial_cash=1000, fee_rate=0))
    data = pd.DataFrame(columns=["dt", "symbol", "close"])

    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.initialized
    assert strategy.finished
    assert strategy.get_hist_equity() == []


def test_exchange_run_requires_data():
    exchange = Exchange()

    with pytest.raises(ValueError, match="set_bars"):
        exchange.run()


def test_exchange_updates_full_bar_before_strategy_callbacks():
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = MultiAssetStrategy(strategy_id="multi", broker=broker)
    data = pd.DataFrame(
        [
            {"dt": "2026-01-01", "symbol": "A", "close": 100.0},
            {"dt": "2026-01-01", "symbol": "B", "close": 200.0},
            {"dt": "2026-01-02", "symbol": "A", "close": 110.0},
            {"dt": "2026-01-02", "symbol": "B", "close": 190.0},
        ]
    )

    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.snapshots == [
        ("2026-01-01", ["A", "B"], 100.0, 200.0, "2026-01-01"),
        ("2026-01-02", ["A", "B"], 110.0, 190.0, "2026-01-02"),
    ]
    assert strategy.get_hist_equity() == [1000, 1000]


def test_exchange_set_bars_requires_symbol_and_price():
    exchange = Exchange()
    data = pd.DataFrame([{"dt": "2026-01-01", "symbol": "A"}])

    with pytest.raises(ValueError, match="close"):
        exchange.set_bars(data)


@pytest.mark.parametrize("data_kind", ["pandas", "polars", "list"])
def test_exchange_set_bars_rejects_duplicate_symbol_in_same_dt(data_kind):
    exchange = Exchange()
    data = _make_duplicate_bar_data(data_kind)

    with pytest.raises(ValueError, match="duplicate"):
        exchange.set_bars(data)


@pytest.mark.parametrize("data_kind", ["pandas", "polars", "list"])
def test_exchange_set_bars_input_formats_produce_same_payload(data_kind):
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = MultiAssetStrategy(strategy_id=data_kind, broker=broker)
    data = _make_multi_asset_data(data_kind)

    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.snapshots == [
        ("2026-01-01", ["A", "B"], 100.0, 200.0, "2026-01-01"),
        ("2026-01-02", ["A", "B"], 110.0, 190.0, "2026-01-02"),
    ]


def test_exchange_prefers_pandas_records_over_iterrows():
    rows = [{"dt": "2026-01-01", "symbol": "A", "close": 100.0}]
    data = PandasLikeData(rows)
    exchange = Exchange()

    exchange.set_bars(data)

    assert data.to_dict_calls == 1


def test_exchange_copies_list_rows_before_storing_feed():
    rows = [{"dt": "2026-01-01", "symbol": "A", "close": 100.0}]
    exchange = Exchange()
    strategy = PriceCaptureStrategy(strategy_id="copy")

    exchange.set_bars(rows)
    rows[0]["close"] = 999.0
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.prices == [100.0]


def test_exchange_requires_explicit_date_key():
    exchange = Exchange()

    with pytest.raises(ValueError, match="dt"):
        exchange.set_bars([{"symbol": "A", "close": 100.0}])


def test_exchange_runs_list_dict_bars_in_dt_order():
    exchange = Exchange()
    strategy = DtCaptureStrategy(strategy_id="list_data")
    data = [
        {"dt": "2026-01-02", "symbol": "A", "close": 101.0},
        {"dt": "2026-01-01", "symbol": "A", "close": 100.0},
    ]

    exchange.set_bars(data)
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.dts == ["2026-01-01", "2026-01-02"]


def test_exchange_updates_shared_broker_once_per_feed_slice():
    exchange = Exchange()
    broker = CountingBroker(initial_cash=1000, fee_rate=0)
    strategy_a = Strategy(strategy_id="a", broker=broker)
    strategy_b = Strategy(strategy_id="b", broker=broker)
    data = pd.DataFrame(
        [
            {"dt": "2026-01-01", "symbol": "A", "close": 100.0},
            {"dt": "2026-01-01", "symbol": "B", "close": 200.0},
            {"dt": "2026-01-02", "symbol": "A", "close": 110.0},
            {"dt": "2026-01-02", "symbol": "B", "close": 190.0},
        ]
    )

    exchange.set_bars(data)
    exchange.add_strategy(strategy_a)
    exchange.add_strategy(strategy_b)
    exchange.run()

    assert broker.price_updates == [
        ("A", 100.0, "2026-01-01"),
        ("B", 200.0, "2026-01-01"),
        ("A", 110.0, "2026-01-02"),
        ("B", 190.0, "2026-01-02"),
    ]


def test_exchange_multi_feed_callbacks_share_same_dt_snapshot():
    exchange = Exchange()
    broker = Broker(initial_cash=1000, fee_rate=0)
    strategy = MultiFeedStrategy(strategy_id="multi_feed", broker=broker)

    exchange.set_bars([{"dt": "2026-01-01", "symbol": "A", "close": 100.0}])
    exchange.set_books([{"dt": "2026-01-01", "symbol": "A", "mid": 101.0, "bid": 100.5, "ask": 101.5}], price_key="mid")
    exchange.set_trades(
        [
            {"dt": "2026-01-01", "symbol": "A", "price": 102.0, "qty": 1},
            {"dt": "2026-01-01", "symbol": "A", "price": 103.0, "qty": 2},
        ]
    )
    exchange.set_news([{"dt": "2026-01-01", "headline": "A announces product"}])

    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.calls == [
        ("bars", "2026-01-01", ["A"], 103.0),
        ("books", "2026-01-01", ["A"], 103.0),
        ("trades", "2026-01-01", ["A"], 103.0),
        ("news", "2026-01-01", 1, 103.0),
    ]
