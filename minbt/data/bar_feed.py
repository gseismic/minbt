"""通用 Bar 的 CSV/iosql 读取实现。

通用存储只约定 `dt`、`symbol`、`kind`、`data` 四个字段。`data` 可以是任意可被 JSON
表示的载荷；本模块不解释 Kline、OrderBook 或其他 kind 的字段。
"""

import csv
import json
from collections.abc import Iterable, Iterator, Mapping
from operator import index
from pathlib import Path

from .model import Bar, datetime_key, normalize_datetime


def _normalize_symbols(symbols):
    if symbols is None:
        return None
    if isinstance(symbols, (str, bytes)):
        symbols = [symbols]
    try:
        result = [str(symbol).strip().upper() for symbol in symbols]
    except TypeError as exc:
        raise TypeError("symbols must be a symbol string or an iterable of symbols") from exc
    if not result or any(not symbol for symbol in result):
        raise ValueError("symbols must not be empty")
    if len(set(result)) != len(result):
        raise ValueError("symbols must not contain duplicates")
    return result


def _normalize_storage_datetime(value):
    """支持 CSV 中常见的数字时间戳文本，同时保留 ISO 时间文本。"""

    if isinstance(value, str):
        text = value.strip()
        if text:
            try:
                numeric = float(text)
            except (TypeError, ValueError):
                pass
            else:
                if numeric.is_integer():
                    numeric = int(numeric)
                return normalize_datetime(numeric)
    return normalize_datetime(value)


class _BarRowFeed:
    """把通用存储行转换为 `Bar`，不解释 `kind` 的字段。"""

    supports_preload = True
    supports_incremental = True
    ordered = True
    replayable = True

    def events(self) -> Iterable[Bar]:
        if not getattr(self, "_prepared", False):
            self.prepare()

        row_stream = iter(self._row_stream())
        previous_key = None
        previous_dt = None
        try:
            for raw_row in row_stream:
                event = self._normalize_row(raw_row)
                current_key = datetime_key(event.dt)
                if previous_key is not None and current_key < previous_key:
                    raise ValueError(
                        f"{self.name} data is not ordered by dt: "
                        f"{event.dt!r} came after {previous_dt!r}"
                    )
                previous_key = current_key
                previous_dt = event.dt
                yield event
        finally:
            close = getattr(row_stream, "close", None)
            if callable(close):
                close()

    def _normalize_row(self, raw_row: Mapping) -> Bar:
        if not isinstance(raw_row, Mapping):
            raise TypeError(f"{self.name} row must be a mapping")
        missing = [field for field in ("symbol", "kind", "data") if field not in raw_row]
        if "dt" not in raw_row and "dt_ms" not in raw_row:
            missing.append("dt")
        if missing:
            raise ValueError(f"{self.name} row missing fields: {missing}")

        value = raw_row.get("dt", raw_row.get("dt_ms"))
        try:
            dt = _normalize_storage_datetime(value)
            if raw_row["symbol"] is None:
                raise ValueError("symbol must not be None")
            symbol = str(raw_row["symbol"]).strip().upper()
            if not symbol:
                raise ValueError("symbol must not be empty")
            if raw_row["kind"] is None:
                raise ValueError("kind must not be None")
            kind = str(raw_row["kind"]).strip().lower()
            if not kind:
                raise ValueError("kind must not be empty")
            data = raw_row["data"]
            if isinstance(data, (str, bytes, bytearray)):
                data = json.loads(data)
            return Bar(dt=dt, symbol=symbol, kind=kind, data=data)
        except (TypeError, ValueError, OverflowError, json.JSONDecodeError) as exc:
            raise ValueError(f"{self.name} row contains invalid Bar values: {raw_row!r}") from exc

    def prepare(self) -> None:
        self._prepared = True

    def close(self) -> None:
        return None


class CsvBarFeed(_BarRowFeed):
    """读取通用 Bar CSV 文件。

    文件必须包含 `dt,symbol,kind,data` 列，`data` 使用 JSON 文本表示。
    """

    def __init__(
        self,
        path,
        symbols=None,
        start=None,
        end=None,
        *,
        name=None,
        feed_priority=0,
    ):
        self.path = Path(path).expanduser()
        self.requested_symbols = _normalize_symbols(symbols)
        self.start_dt = normalize_datetime(start) if start is not None else None
        self.end_dt = normalize_datetime(end) if end is not None else None
        if self.start_dt is not None and self.end_dt is not None:
            if datetime_key(self.start_dt) >= datetime_key(self.end_dt):
                raise ValueError("end must be greater than start")
        self.name = name or f"csv:bar:{self.path.name}"
        self.feed_priority = int(feed_priority)
        self._prepared = False

    def prepare(self) -> None:
        if self._prepared:
            return
        if not self.path.is_file():
            raise FileNotFoundError(f"generic Bar CSV file does not exist: {self.path}")
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = set(reader.fieldnames or ())
        missing = sorted({"dt", "symbol", "kind", "data"} - fields)
        if missing:
            raise ValueError(f"{self.name} CSV is missing required columns: {missing}")
        self._prepared = True

    def _row_stream(self) -> Iterator[dict]:
        if not self._prepared:
            self.prepare()
        with self.path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("symbol") is None:
                    yield row
                    continue
                symbol = str(row["symbol"]).strip().upper()
                if self.requested_symbols is not None and symbol not in self.requested_symbols:
                    continue
                dt = _normalize_storage_datetime(row.get("dt"))
                if self.start_dt is not None and datetime_key(dt) < datetime_key(self.start_dt):
                    continue
                if self.end_dt is not None and datetime_key(dt) >= datetime_key(self.end_dt):
                    break
                yield row


class IosqlBarFeed(_BarRowFeed):
    """读取通用 iosql Bar 表。

    表必须包含 `dt`、`symbol`、`kind`、`data` 列；`dt` 按 UTC 毫秒时间戳存储，`data` 使用 JSON
    文本表示。表的主键可以由写入方自行设计，允许同一时间点存在多个 Trade Bar。
    """

    def __init__(
        self,
        uri,
        *,
        table="bars",
        symbols=None,
        start=None,
        end=None,
        batch_size=10_000,
        name=None,
        feed_priority=0,
    ):
        if not isinstance(uri, str) or "://" not in uri:
            raise ValueError("uri must include an iosql scheme, for example sqlite:///path/to/data.iosql")
        if not isinstance(table, str) or not table.strip():
            raise ValueError("table must be a non-empty string")
        try:
            normalized_batch_size = index(batch_size)
        except TypeError as exc:
            raise ValueError("batch_size must be a positive integer") from exc
        if isinstance(batch_size, bool) or normalized_batch_size <= 0:
            raise ValueError("batch_size must be a positive integer")
        self.uri = uri
        self.table_name = table
        self.requested_symbols = _normalize_symbols(symbols)
        self.start_dt = normalize_datetime(start) if start is not None else None
        self.end_dt = normalize_datetime(end) if end is not None else None
        if self.start_dt is not None and self.end_dt is not None:
            if datetime_key(self.start_dt) >= datetime_key(self.end_dt):
                raise ValueError("end must be greater than start")
        self.batch_size = normalized_batch_size
        self.name = name or f"iosql:bar:{self.table_name}"
        self.feed_priority = int(feed_priority)
        self._db = None
        self._query = None
        self._prepared = False

    def prepare(self) -> None:
        if self._prepared:
            return
        try:
            from iosql import Database
        except ImportError as exc:
            raise ImportError("IosqlBarFeed requires iosql; install iosql v0.3.x or newer") from exc

        try:
            self._db = Database(self.uri)
            available_tables = sorted(self._db.table_names())
            if self.table_name not in available_tables:
                raise ValueError(
                    f"iosql table {self.table_name!r} not found; available tables: {available_tables!r}"
                )
            table = self._db.table(self.table_name)
            query_kwargs = {"order_by": "dt"}
            if self.start_dt is not None:
                query_kwargs["start"] = datetime_key(self.start_dt)
            if self.end_dt is not None:
                query_kwargs["end"] = datetime_key(self.end_dt) - 1
            if self.requested_symbols is not None:
                query_kwargs["symbols"] = self.requested_symbols
            if not self._query_has_rows(table, query_kwargs):
                raise ValueError(
                    f"no iosql Bar rows matched table={self.table_name!r}, "
                    f"symbols={self.requested_symbols!r}, start={self.start_dt!r}, end={self.end_dt!r}"
                )
            self._query = table.query(**query_kwargs)
            self._prepared = True
        except Exception:
            self.close()
            raise

    def _query_has_rows(self, table, query_kwargs) -> bool:
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
                yield dict(row)
        finally:
            self.close()

    def close(self) -> None:
        db = self._db
        self._db = None
        self._query = None
        self._prepared = False
        if db is not None:
            db.close()


__all__ = ["CsvBarFeed", "IosqlBarFeed"]
