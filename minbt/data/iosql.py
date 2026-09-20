from pathlib import Path
from typing import Iterator

from .bars import _KlineRowFeed, datetime_to_ms, normalize_symbols, to_utc_datetime


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
        self.interval = str(interval)
        if not self.interval:
            raise ValueError("interval must not be empty")
        self.table_name = table or f"kline_{self.interval}"
        self.requested_symbols = normalize_symbols(symbols, allow_none=True)
        self.symbols = list(self.requested_symbols or [])
        self.start_dt = to_utc_datetime(start) if start is not None else None
        self.end_dt = to_utc_datetime(end) if end is not None else None
        self.start_ms = datetime_to_ms(self.start_dt) if self.start_dt is not None else None
        self.end_ms = datetime_to_ms(self.end_dt) if self.end_dt is not None else None
        if self.start_ms is not None and self.end_ms is not None and self.start_ms >= self.end_ms:
            raise ValueError("end must be greater than start")
        if isinstance(batch_size, bool) or int(batch_size) <= 0:
            raise ValueError("batch_size must be a positive integer")
        self.batch_size = int(batch_size)
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
            table = self._db.table(self.table_name)
            query_kwargs = {"order_by": "open_time"}
            if self.requested_symbols is not None:
                query_kwargs["symbols"] = self.requested_symbols
            if self.start_ms is not None:
                query_kwargs["start"] = self.start_ms
            if self.end_ms is not None:
                # iosql 的 start/end 是闭区间，minbt 的 end 是半开区间。
                query_kwargs["end"] = self.end_ms - 1
            self._query = table.query(**query_kwargs)
            self._prepared = True
        except Exception:
            self.close()
            raise

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
