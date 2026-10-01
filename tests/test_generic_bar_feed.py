import csv
import json
from datetime import datetime, timezone

import pytest

from minbt import Bar, Broker, Exchange, Strategy
from minbt.data import CsvBarFeed, IosqlBarFeed, SimpleFeed


UTC = timezone.utc


def _dt(minute):
    return datetime(2026, 1, 1, 0, minute, tzinfo=UTC)


def test_simple_feed_only_needs_name_and_events_and_uses_safe_preload_defaults():
    class UnorderedFeed(SimpleFeed):
        def events(self):
            yield Bar(_dt(1), "A", "price", {"value": 101.0})
            yield Bar(_dt(0), "A", "price", {"value": 100.0})

    class Probe(Strategy):
        def on_init(self):
            self.values = []

        def on_bar(self, dt, bar):
            self.values.append((dt, bar.kind, bar.data["value"]))

    feed = UnorderedFeed("simple")
    exchange = Exchange()
    exchange.add_feed(feed)
    strategy = Probe("simple", Broker(initial_cash=1000, mark_price=None))
    exchange.add_strategy(strategy)

    exchange.run()

    assert strategy.values == [(_dt(0), "price", 100.0), (_dt(1), "price", 101.0)]


def test_plain_feed_without_capability_attributes_uses_safe_defaults():
    class PlainFeed:
        name = "plain"

        def events(self):
            yield Bar(_dt(0), "A", "custom", {"value": 1})

    exchange = Exchange()
    exchange.add_feed(PlainFeed())
    exchange.add_strategy(Strategy("plain", Broker(initial_cash=1000, mark_price=None)))

    exchange.run()


def test_generic_csv_bar_feed_preserves_kind_and_payload(tmp_path):
    path = tmp_path / "bars.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dt", "symbol", "kind", "data"])
        writer.writeheader()
        writer.writerow(
            {
                "dt": "2026-01-01T00:00:00Z",
                "symbol": "A",
                "kind": "orderbook",
                "data": json.dumps({"bids": [[100.0, 1.0]], "asks": [[100.1, 2.0]]}),
            }
        )

    events = list(CsvBarFeed(path).events())

    assert len(events) == 1
    assert events[0].kind == "orderbook"
    assert dict(events[0].data) == {
        "bids": ((100.0, 1.0),),
        "asks": ((100.1, 2.0),),
    }


def test_generic_csv_end_filter_does_not_hide_out_of_order_rows(tmp_path):
    path = tmp_path / "bars.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dt", "symbol", "kind", "data"])
        writer.writeheader()
        for minute in (0, 10, 5):
            writer.writerow(
                {
                    "dt": f"2026-01-01T00:{minute:02d}:00Z",
                    "symbol": "A",
                    "kind": "price",
                    "data": json.dumps({"value": 100 + minute}),
                }
            )

    with pytest.raises(ValueError, match="not ordered"):
        list(CsvBarFeed(path, start="2026-01-01T00:00:00Z", end="2026-01-01T00:06:00Z").events())


def test_generic_csv_bar_feed_dispatches_custom_bar(tmp_path):
    path = tmp_path / "bars.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dt", "symbol", "kind", "data"])
        writer.writeheader()
        writer.writerow(
            {
                "dt": "2026-01-01T00:00:00Z",
                "symbol": "A",
                "kind": "price",
                "data": json.dumps({"value": 123.4}),
            }
        )

    class Probe(Strategy):
        def on_init(self):
            self.events = []

        def on_bar(self, dt, bar):
            self.events.append((dt, bar.symbol, bar.kind, bar.data["value"]))

    exchange = Exchange()
    exchange.add_feed(CsvBarFeed(path))
    strategy = Probe("csv-bar", Broker(initial_cash=1000, mark_price="price.value"))
    exchange.add_strategy(strategy)
    exchange.run()

    assert strategy.events == [(_dt(0), "A", "price", 123.4)]
    assert strategy.broker.get_last_price("A") == 123.4


def test_generic_iosql_bar_feed_reads_envelope(tmp_path):
    iosql = pytest.importorskip("iosql")
    uri = f"sqlite://{tmp_path / 'bars.iosql'}"
    rows = [
        {
            "id": 1,
            "dt": 1_767_225_600_000,
            "symbol": "A",
            "kind": "orderbook",
            "data": json.dumps({"mid": 100.5}),
        },
        {
            "id": 2,
            "dt": 1_767_225_660_000,
            "symbol": "A",
            "kind": "price",
            "data": json.dumps({"value": 101.0}),
        },
    ]
    with iosql.Database(uri) as db:
        table = db.table(
            "bars",
            pk=["id"],
            time="dt",
            symbol_column="symbol",
            columns={
                "id": "integer",
                "dt": "integer",
                "symbol": "text",
                "kind": "text",
                "data": "text",
            },
            partition="duration(dt,every=1day)",
            order_key="dt",
        )
        table.write(rows)

    feed = IosqlBarFeed(uri, start="2026-01-01", end="2026-01-02")

    events = list(feed.events())

    assert [(event.symbol, event.kind, dict(event.data)) for event in events] == [
        ("A", "orderbook", {"mid": 100.5}),
        ("A", "price", {"value": 101.0}),
    ]
