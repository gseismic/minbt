from dataclasses import dataclass
from typing import Callable, Optional, Any, Dict


@dataclass
class ExitContext:
    symbol: str
    dt: Any
    price: float
    position: Any
    broker: Any
    portfolio_id: str
    data: Any = None
    state: Dict = None


@dataclass
class ExitRule:
    name: str
    condition: Callable[[ExitContext], bool]
    state: Any = None

    def get_state(self):
        if callable(self.state):
            return self.state()
        if self.state is None:
            return {}
        return self.state


def stop_loss_pct(pct: float, name: Optional[str] = None) -> ExitRule:
    if pct <= 0:
        raise ValueError(f"pct must be positive, got {pct}")

    def condition(ctx: ExitContext) -> bool:
        if ctx.position.size > 0:
            return ctx.price <= ctx.position.cost_price * (1 - pct)
        if ctx.position.size < 0:
            return ctx.price >= ctx.position.cost_price * (1 + pct)
        return False

    return ExitRule(name=name or f"stop_loss_{pct}", condition=condition)


def take_profit_pct(pct: float, name: Optional[str] = None) -> ExitRule:
    if pct <= 0:
        raise ValueError(f"pct must be positive, got {pct}")

    def condition(ctx: ExitContext) -> bool:
        if ctx.position.size > 0:
            return ctx.price >= ctx.position.cost_price * (1 + pct)
        if ctx.position.size < 0:
            return ctx.price <= ctx.position.cost_price * (1 - pct)
        return False

    return ExitRule(name=name or f"take_profit_{pct}", condition=condition)

