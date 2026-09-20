import csv as csv_module
from contextlib import ExitStack
import heapq
from pathlib import Path
import re
from typing import Iterator

from .bars import (
    _KlineRowFeed,
    datetime_to_ms,
    normalize_symbols,
    optional_float,
    optional_int,
    to_utc_datetime,
)


_CSV_NAME_RE = re.compile(
    r"^(?P<symbol>[^-]+)-(?P<interval>[^-]+)-(?P<month>\d{4}-\d{2})\.csv$",
    re.IGNORECASE,
)


class CsvBarsFeed(_KlineRowFeed):
    """读取 crypto.bn_data_sync 月度 Binance K 线 CSV 的渐进式 Feed。"""

    def __init__(
        self,
        root,
        symbols=None,
        start=None,
        end=None,
        *,
        interval=None,
        name=None,
    ):
        self.root = Path(root).expanduser()
        self.requested_symbols = normalize_symbols(symbols, allow_none=True)
        self.start_dt = to_utc_datetime(start) if start is not None else None
        self.end_dt = to_utc_datetime(end) if end is not None else None
        self.start_ms = datetime_to_ms(self.start_dt) if self.start_dt is not None else None
        self.end_ms = datetime_to_ms(self.end_dt) if self.end_dt is not None else None
        if self.start_ms is not None and self.end_ms is not None and self.start_ms >= self.end_ms:
            raise ValueError("end must be greater than start")
        self.interval = str(interval) if interval is not None else None
        self._files_by_month = {}
        self._prepared = False
        self.symbols = list(self.requested_symbols or [])
        self.name = name or self._default_name()

    def _default_name(self) -> str:
        symbols = ",".join(self.symbols) if self.symbols else "all"
        return f"csv:bars:{self.root.name}:{symbols}"

    def prepare(self) -> None:
        if self._prepared:
            return
        if not self.root.exists():
            raise FileNotFoundError(f"CSV root does not exist: {self.root}")

        candidates = [self.root] if self.root.is_file() else sorted(self.root.glob("*.csv"))
        discovered_symbols = set()
        discovered_intervals = set()
        files_by_month = {}

        for path in candidates:
            match = _CSV_NAME_RE.match(path.name)
            if match is None:
                if self.root.is_file():
                    raise ValueError(
                        f"CSV filename must look like SYMBOL-INTERVAL-YYYY-MM.csv: {path.name}"
                    )
                continue
            symbol = match.group("symbol").upper()
            file_interval = match.group("interval")
            month = match.group("month")
            if self.requested_symbols is not None and symbol not in self.requested_symbols:
                continue
            if self.interval is not None and file_interval != self.interval:
                continue
            discovered_symbols.add(symbol)
            discovered_intervals.add(file_interval)
            files_by_month.setdefault(month, []).append((symbol, path))

        if self.interval is None and len(discovered_intervals) > 1:
            raise ValueError(
                f"CSV root contains multiple intervals {sorted(discovered_intervals)!r}; "
                "pass interval explicitly"
            )
        if self.interval is None and discovered_intervals:
            self.interval = next(iter(discovered_intervals))

        if not files_by_month:
            requested = ", ".join(self.requested_symbols or []) or "all symbols"
            raise FileNotFoundError(
                f"no CSV files matched root={self.root}, symbols={requested}, interval={self.interval!r}"
            )

        for month, entries in files_by_month.items():
            entries.sort(key=lambda item: item[0])
            seen_symbols = set()
            for symbol, path in entries:
                if symbol in seen_symbols:
                    raise ValueError(f"duplicate CSV files for {symbol} {month}: {path}")
                seen_symbols.add(symbol)

        if self.requested_symbols is None:
            self.symbols = sorted(discovered_symbols)
        else:
            self.symbols = list(self.requested_symbols)
        self._files_by_month = {
            month: entries for month, entries in sorted(files_by_month.items())
        }
        self._prepared = True

    def _row_stream(self) -> Iterator[dict]:
        if not self._prepared:
            self.prepare()
        for month, entries in self._files_by_month.items():
            with ExitStack() as stack:
                streams = []
                for symbol, path in entries:
                    handle = stack.enter_context(path.open("r", newline="", encoding="utf-8"))
                    streams.append(self._iter_file_rows(handle, path, symbol))
                yield from heapq.merge(
                    *streams,
                    key=lambda row: (row["dt_ms"], row["symbol"]),
                )

    def _iter_file_rows(self, handle, path: Path, symbol: str) -> Iterator[dict]:
        previous_dt_ms = None
        for line_number, raw in enumerate(csv_module.reader(handle), start=1):
            if not raw or not any(field.strip() for field in raw):
                continue
            first = raw[0].strip().lstrip("\ufeff").lower()
            if first == "open_time":
                continue
            if len(raw) < 12:
                raise ValueError(f"{path}:{line_number}: CSV row has fewer than 12 columns")
            try:
                dt_ms = int(raw[0])
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{path}:{line_number}: invalid CSV row: {raw!r}") from exc
            if previous_dt_ms is not None and dt_ms < previous_dt_ms:
                raise ValueError(
                    f"{path}:{line_number}: open_time is not ordered "
                    f"({dt_ms} after {previous_dt_ms})"
                )
            previous_dt_ms = dt_ms
            if self.start_ms is not None and dt_ms < self.start_ms:
                continue
            if self.end_ms is not None and dt_ms >= self.end_ms:
                continue
            try:
                yield {
                    "dt_ms": dt_ms,
                    "symbol": symbol,
                    "open": float(raw[1]),
                    "high": float(raw[2]),
                    "low": float(raw[3]),
                    "close": float(raw[4]),
                    "volume": float(raw[5]),
                    "close_time": optional_int(raw[6]),
                    "volume_quote": optional_float(raw[7]),
                    "num_trades": optional_int(raw[8]),
                    "volume_base_buy": optional_float(raw[9]),
                    "volume_quote_buy": optional_float(raw[10]),
                }
            except (TypeError, ValueError, OverflowError) as exc:
                raise ValueError(f"{path}:{line_number}: invalid CSV row: {raw!r}") from exc
