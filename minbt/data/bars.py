"""通用 Bar 数据入口。

`Bar` 的定义位于 `model.py`；Kline 行读取实现位于 `kline.py`，不会把 Kline 当成所有 Bar
的共同字段集合。
"""

from .bar_feed import CsvBarFeed, IosqlBarFeed
from .model import Bar, News


__all__ = ["Bar", "News", "CsvBarFeed", "IosqlBarFeed"]
