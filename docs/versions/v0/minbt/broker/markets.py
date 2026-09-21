from .market import Market


DEFAULT = Market(name="Default")

CRYPTO = Market(name="Crypto")

A_STOCK = Market(
    name="AStock",
    allow_short=False,
    t_plus=1,
    lot_size=100,
    tick_size=0.01,
    require_dt=True,
    weekdays_only=True,
    trading_sessions=(("09:30", "11:30"), ("13:00", "15:00")),
    allow_daily_bar=True,
)
