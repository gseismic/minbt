"""交易数值的纯校验函数，供账户与退出入口在修改状态前复用。"""

import math
from numbers import Real


def finite_number(value, name: str) -> float:
    """只接受有限实数，避免布尔值、字符串及 NaN 进入账本。"""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def positive_number(value, name: str) -> float:
    """校验价格和金额等要求大于零的有限实数。"""
    result = finite_number(value, name)
    if result <= 0:
        raise ValueError(f"{name} must be positive, got {value}")
    return result
