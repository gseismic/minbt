from operator import index
from pathlib import Path
from typing import Iterator

from .bars import _KlineRowFeed, datetime_to_ms, normalize_symbols, to_utc_datetime


class _IosqlFeedConfigurationError(ValueError):
    """iosql Feed 可由用户修正的配置或数据范围错误。"""


class IosqlBarsFeed(_KlineRowFeed):
    """读取 iosql Binance K 线表的渐进式 bars Feed。"""

    def __init__(
        self,
        uri,
        interval,
        symbols=None,
        start=None,
        end=None,
        *,
        table=None,
        batch_size=10_000,
        name=None,
    ):
        if isinstance(uri, Path):
            uri = str(uri)
        if not isinstance(uri, str) or "://" not in uri:
            raise ValueError("uri must include an iosql scheme, for example sqlite:///path/to/data.iosql")
        self.uri = uri
        if interval is None:
            raise ValueError("interval must not be empty")
        self.interval = str(interval)
        if not self.interval.strip():
            raise ValueError("interval must not be empty")
        if table is not None and (not isinstance(table, str) or not table.strip()):
            raise ValueError("table must be a non-empty string")
        self.table_name = table or f"kline_{self.interval}"
        self.requested_symbols = normalize_symbols(symbols, allow_none=True)
        self.symbols = list(self.requested_symbols or [])
        self.start_dt = to_utc_datetime(start) if start is not None else None
        self.end_dt = to_utc_datetime(end) if end is not None else None
        self.start_ms = datetime_to_ms(self.start_dt) if self.start_dt is not None else None
        self.end_ms = datetime_to_ms(self.end_dt) if self.end_dt is not None else None
        if self.start_ms is not None and self.end_ms is not None and self.start_ms >= self.end_ms:
            raise ValueError("end must be greater than start")
        try:
            normalized_batch_size = index(batch_size)
        except TypeError as exc:
            raise ValueError("batch_size must be a positive integer") from exc
        if isinstance(batch_size, bool) or normalized_batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        self.batch_size = normalized_batch_size
        self.name = name or self._default_name()
        self._db = None
        self._query = None
        self._prepared = False

    def _default_name(self) -> str:
        symbols = ",".join(self.symbols) if self.symbols else "all"
        return f"iosql:bars:{self.table_name}:{symbols}"

    def prepare(self) -> None:
        if self._prepared:
            return
        try:
            from iosql import Database
        except ImportError as exc:
            raise ImportError(
                "IosqlBarsFeed requires iosql; install iosql v0.3.x or newer"
            ) from exc

        try:
            self._db = Database(self.uri)
            available_tables = sorted(self._db.table_names())
            if self.table_name not in available_tables:
                raise _IosqlFeedConfigurationError(
                    f"iosql table {self.table_name!r} not found for interval={self.interval!r}; "
                    f"available tables: {available_tables!r}"
                )
            table = self._db.table(self.table_name)
            query_kwargs = {"order_by": "open_time"}
            if self.start_ms is not None:
                query_kwargs["start"] = self.start_ms
            if self.end_ms is not None:
                # iosql 的 start/end 是闭区间，minbt 的 end 是半开区间。
                query_kwargs["end"] = self.end_ms - 1

            missing_symbols = []
            if self.requested_symbols is None:
                if not self._query_has_rows(table, query_kwargs):
                    raise _IosqlFeedConfigurationError(
                        f"no iosql rows matched table={self.table_name!r}, "
                        f"interval={self.interval!r}, start={self.start_dt!r}, end={self.end_dt!r}"
                    )
            else:
                for symbol in self.requested_symbols:
                    symbol_query = dict(query_kwargs)
                    symbol_query["symbols"] = [symbol]
                    if not self._query_has_rows(table, symbol_query):
                        missing_symbols.append(symbol)
                if missing_symbols:
                    raise _IosqlFeedConfigurationError(
                        f"no iosql rows matched requested range for symbols {missing_symbols!r}; "
                        f"table={self.table_name!r}, interval={self.interval!r}, "
                        f"start={self.start_dt!r}, end={self.end_dt!r}"
                    )
                query_kwargs["symbols"] = self.requested_symbols

            self._query = table.query(**query_kwargs)
            self._prepared = True
        except _IosqlFeedConfigurationError:
            self.close()
            raise
        except Exception as exc:
            self.close()
            raise ValueError(
                f"failed to query iosql table={self.table_name!r} for interval={self.interval!r}; "
                f"check uri, table, interval, symbols, and time range: {exc}"
            ) from exc

    def _query_has_rows(self, table, query_kwargs) -> bool:
        """用 limit=1 预检查询，避免空数据启动回测。"""
        probe = table.query(**query_kwargs, limit=1)
        rows = iter(probe.iter_rows(batch_size=1))
        try:
            next(rows)
        except StopIteration:
            return False
        finally:
            close = getattr(rows, "close", None)
            if callable(close):
                close()
        return True

    def _row_stream(self) -> Iterator[dict]:
        if not self._prepared:
            self.prepare()
        try:
            for row in self._query.iter_rows(batch_size=self.batch_size):
                normalized = dict(row)
                normalized["dt_ms"] = normalized.pop("open_time")
                yield normalized
        finally:
            # 即使调用方直接关闭 events() 生成器，也释放 Database。
            self.close()

    def close(self) -> None:
        db = self._db
        self._db = None
        self._query = None
        self._prepared = False
        if db is not None:
            db.close()
