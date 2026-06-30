from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class QuietLogger:
    def debug(self, *args, **kwargs):
        pass

    def info(self, *args, **kwargs):
        pass

    def warning(self, *args, **kwargs):
        pass

    def error(self, *args, **kwargs):
        pass


def target_position_value(
    broker,
    symbol: str,
    target_value: float,
    price: float,
    *,
    leverage: float = 1.0,
    min_qty: float = 1e-12,
) -> bool:
    """按目标名义金额调仓，正值做多，负值做空。"""
    current_value = broker.get_position_size(symbol) * price
    if abs(target_value - current_value) <= min_qty * price:
        return False
    order = broker.order_target_value(symbol, target_value=target_value, price=price, leverage=leverage)
    return order.status == "filled"


def flatten_position(broker, symbol: str, price: float, *, min_qty: float = 1e-12) -> bool:
    current_size = broker.get_position_size(symbol)
    if abs(current_size) <= min_qty:
        return False
    order = broker.close_position(symbol, price=price)
    return order.status == "filled"
