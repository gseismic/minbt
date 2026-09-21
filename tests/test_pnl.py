import pytest

from minbt import Broker


@pytest.mark.parametrize(
    "qty, entry_price, exit_price, fee_rate, expected_pnl",
    [
        (1.0, 100.0, 120.0, 0.0, 20.0),
        (-1.0, 100.0, 90.0, 0.0, 10.0),
        (1.0, 100.0, 100.05, 0.001, -0.15005),
    ],
)
def test_broker_round_trip_equity_matches_hand_calculated_pnl(
    qty, entry_price, exit_price, fee_rate, expected_pnl
):
    """从 Broker 公共接口验证多空方向和往返手续费后的总权益。"""
    initial_cash = 1000.0
    broker = Broker(initial_cash=initial_cash, fee_rate=fee_rate)

    entry = broker.submit_market_order(
        "TEST",
        qty=qty,
        price=entry_price,
        price_dt="2026-01-01",
    )
    exit_order = broker.close_position(
        "TEST",
        price=exit_price,
        price_dt="2026-01-02",
    )

    gross_pnl = qty * (exit_price - entry_price)
    fees = abs(qty) * (entry_price + exit_price) * fee_rate

    assert entry.status == "filled"
    assert exit_order.status == "filled"
    assert broker.get_position_size("TEST") == 0
    assert broker.get_total_equity() == pytest.approx(initial_cash + gross_pnl - fees)
    assert broker.get_total_equity() == pytest.approx(initial_cash + expected_pnl)
