import csv as csv_module
from contextlib import ExitStack
from datetime import timedelta
import heapq
from pathlib import Path
import re
from typing import Iterator

from .kline import (
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


def _iter_months(first: str, last: str) -> Iterator[str]:
    """按月递增迭代 ["YYYY-MM", "YYYY-MM"] 闭区间。"""
    year, month = int(first[:4]), int(first[5:7])
    last_year, last_month = int(last[:4]), int(last[5:7])
    while (year, month) <= (last_year, last_month):
        yield f"{year:04d}-{month:02d}"
        month += 1
        if month > 12:
            year += 1
            month = 1


class BinanceKlineCsvFeed(_KlineRowFeed):
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
        feed_priority=0,
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
        self.feed_priority = int(feed_priority)

    def _default_name(self) -> str:
        symbols = ",".join(self.symbols) if self.symbols else "all"
        return f"csv:binance:kline:{self.root.name}:{symbols}"

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

        if self.requested_symbols is not None:
            missing_symbols = sorted(set(self.requested_symbols) - discovered_symbols)
            if missing_symbols:
                raise FileNotFoundError(
                    f"no CSV files matched requested symbols {missing_symbols!r} "
                    f"for interval={self.interval!r} under root={self.root}"
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
        first_requested_month = (
            self.start_dt.strftime("%Y-%m") if self.start_dt is not None else None
        )
        last_requested_month = (
            (self.end_dt - timedelta(milliseconds=1)).strftime("%Y-%m")
            if self.end_dt is not None
            else None
        )
        self._files_by_month = {
            month: entries
            for month, entries in sorted(files_by_month.items())
            if (first_requested_month is None or month >= first_requested_month)
            and (last_requested_month is None or month <= last_requested_month)
        }
        self._validate_matching_rows()
        self._validate_month_files(set(self._files_by_month))
        self._prepared = True

    def _validate_matching_rows(self) -> None:
        """在回放前确认每个目标 symbol 在请求区间内至少有一行。"""
        matched_symbols = set()
        for entries in self._files_by_month.values():
            for symbol, path in entries:
                if symbol in matched_symbols:
                    continue
                with path.open("r", newline="", encoding="utf-8") as handle:
                    rows = self._iter_file_rows(handle, path, symbol)
                    try:
                        next(rows)
                    except StopIteration:
                        continue
                    finally:
                        rows.close()
                matched_symbols.add(symbol)

        missing_symbols = sorted(set(self.symbols) - matched_symbols)
        if missing_symbols:
            raise ValueError(
                f"no CSV rows matched requested range for symbols {missing_symbols!r}; "
                f"root={self.root}, interval={self.interval!r}, "
                f"start={self.start_dt!r}, end={self.end_dt!r}"
            )

    def _validate_month_files(self, discovered_months: set) -> None:
        """按时间边界推导应有月份；月份文件空洞直接失败。"""
        if not discovered_months:
            return
        first = (
            self.start_dt.strftime("%Y-%m")
            if self.start_dt is not None
            else min(discovered_months)
        )
        last = (
            (self.end_dt - timedelta(milliseconds=1)).strftime("%Y-%m")
            if self.end_dt is not None
            else max(discovered_months)
        )
        if first > last:
            return

        files_by_pair = {
            (symbol, month)
            for month, entries in self._files_by_month.items()
            for symbol, _ in entries
        }
        missing = [
            f"{symbol}@{month}"
            for month in _iter_months(first, last)
            for symbol in self.symbols
            if (symbol, month) not in files_by_pair
        ]
        if missing:
            raise FileNotFoundError(
                f"missing CSV month files for requested range: {missing!r}; "
                f"root={self.root}, interval={self.interval!r}"
            )

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
                # 文件内已保证 open_time 升序，越过 end 后无需继续扫描
                break
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
