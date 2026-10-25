"""单标的闭合 K 线实时行情；连接和线程由注入的 SDK 负责。"""

from contextlib import AbstractContextManager
from threading import get_ident
from time import time

from ..._validation import finite_number, positive_number
from ...data.model import normalize_symbol
from ...strategy import Strategy
from ._kline import ms_to_datetime
from .broker import Broker


class Exchange(AbstractContextManager):
    """一次运行一个策略；账户由调用者关闭，行情由本对象关闭。"""

    def __init__(self, *, symbol, interval, environment, sdk_factory, max_delay=10.0):
        self.symbol = normalize_symbol(symbol)
        self.interval = interval
        self.max_delay = positive_number(max_delay, "max_delay")
        self._strategy = None
        self._state = "created"
        self._last_close = None
        self._callback_thread = None
        self.sdk = sdk_factory(on_data=self._on_data, environment=environment)

    def add_strategy(self, strategy: Strategy) -> None:
        if self._state != "created" or self._strategy is not None:
            raise RuntimeError("live Exchange accepts one Strategy before run")
        if not isinstance(strategy, Strategy) or not isinstance(strategy.broker, Broker):
            raise TypeError("live Exchange requires Strategy with binance.Broker")
        broker = strategy.broker
        if broker._exchange is not None or broker.sdk.exchange is not self.sdk:
            raise ValueError("Broker must be unused and linked to this SDK Exchange")
        strategy.set_exchange(self)
        broker._exchange = self
        self._strategy = strategy

    def get_current_dt(self):
        return None if self._last_close is None else ms_to_datetime(self._last_close)

    def run(self) -> None:
        strategy = self._strategy
        if self._state != "created" or strategy is None:
            raise RuntimeError("run requires a fresh Exchange with one Strategy")
        if (
            strategy._run_consumed or strategy.exchange is not self
            or not isinstance(strategy.broker, Broker) or strategy.broker._exchange is not self
        ):
            raise RuntimeError("Strategy or Broker binding changed after registration")
        self._state = "running"
        strategy._run_consumed = True
        try:
            with self:
                self.sdk.on_connection(self._on_connection)
                self.sdk.subscribe(self.symbol, "kline", interval=self.interval)
                mode = strategy.broker.sdk.get_position_mode()["dualSidePosition"]
                if mode is not False and mode != "false":
                    raise ValueError("live Exchange requires one-way position mode")
                if self._state == "running":
                    strategy.on_init()
                if self._state == "running":
                    self.sdk.run()
            strategy.on_finish()
        except BaseException:
            self._state = "failed"
            raise

    def stop(self) -> None:
        if self._state != "failed":
            self._state = "stopped"
        self.sdk.stop()

    def close(self) -> None:
        if self._state != "failed":
            self._state = "stopped"
        self.sdk.close()

    def __exit__(self, exc_type, exc, traceback):
        try:
            self.close()
        except BaseException:
            if exc_type is None:
                raise  # 已有异常时保留原始错误，避免清理失败将其覆盖。

    def _on_connection(self, notice):
        if self._state == "running" and (
            notice["gap"] or notice["state"] in {"disconnected", "reconnecting", "reconnected", "failed"}
        ):
            raise RuntimeError(f"live market connection interrupted: {notice}")

    def _on_data(self, events):
        for event in events:
            if self._state != "running":
                return
            if event.data_type != "kline" or event.symbol != self.symbol:
                raise ValueError("unexpected live market event")
            kline = event.data["k"]
            if kline["s"] != self.symbol or kline["i"] != self.interval:
                raise ValueError("unexpected kline symbol or interval")
            if kline["x"] is not True:
                continue
            opened = _integer(kline["t"], "open_time")
            closed = _integer(kline["T"], "close_time")
            if opened >= closed:
                raise ValueError("kline open_time must precede close_time")
            if self._last_close is not None:
                if closed <= self._last_close:
                    continue
                if opened != self._last_close + 1:
                    raise ValueError("live kline gap or overlap")
            bar = {
                field: finite_number(float(kline[key]), field)
                for field, key in _FIELDS.items()
            }
            bar.update(
                open_time=opened, close_time=closed,
                num_trades=_integer(kline["n"], "num_trades"),
            )
            now = time() * 1000
            for stamp in (event.received_at, event.data["E"], closed):
                if abs(now - _integer(stamp, "market timestamp")) > self.max_delay * 1000:
                    raise ValueError("live kline is stale or ahead of the local clock")
            if self._state != "running":
                return
            self._last_close = closed
            self._callback_thread = get_ident()
            try:
                self._strategy.on_bars(self.get_current_dt(), {self.symbol: bar})
            finally:
                self._callback_thread = None


_FIELDS = {
    "open": "o", "high": "h", "low": "l", "close": "c", "volume": "v",
    "volume_quote": "q", "volume_base_buy": "V", "volume_quote_buy": "Q",
}


def _integer(value, name):
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value
