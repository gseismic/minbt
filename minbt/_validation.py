"""交易数值的纯校验函数，供账户与退出入口在修改状态前复用。"""

import math
import sys
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


def _float_ulp(value: float) -> float:
    """返回浮点间距，兼容没有 math.ulp 的 Python 3.8。"""
    if value == 0:
        return float.fromhex("0x0.0000000000001p-1022")
    _, exponent = math.frexp(abs(value))
    return max(
        float.fromhex("0x0.0000000000001p-1022"),
        math.ldexp(1.0, exponent - sys.float_info.mant_dig),
    )


def _cash_balance(balance: float, amount: float) -> float:
    """检查候选现金有限性，只归零加减运算的少量浮点尾差。"""
    result = finite_number(balance + amount, "cash balance")
    tolerance = 4 * max(_float_ulp(balance), _float_ulp(amount))
    return 0.0 if abs(result) <= tolerance else result


def _finite_sum(values, name: str) -> float:
    """在真实提交前验证汇总结果，溢出统一按非法数值报告。"""
    try:
        result = math.fsum(values)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite") from exc
    return finite_number(result, name)
