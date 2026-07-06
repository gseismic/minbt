from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass
class ExitContext:
    order_id: str
    symbol: str
    portfolio: str
    dt: Any
    price: float
    position: Any
    broker: Any
    data: Any = None
    state: Optional[Dict] = None


@dataclass
class ExitRule:
    name: str
    condition: Callable[[ExitContext], bool]
    state: Dict = field(default_factory=dict)

    def get_state(self):
        return self.state


@dataclass
class ExitConfig:
    order_id: str
    symbol: str
    portfolio: str
    active: bool = False
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    trailing_stop_amount: Optional[float] = None
    trailing_anchor: Optional[float] = None
    custom_rules: Tuple[str, ...] = ()


@dataclass
class _ExitState:
    order_id: str
    symbol: str
    portfolio: str
    active: bool = False
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    trailing_stop_pct: Optional[float] = None
    trailing_stop_amount: Optional[float] = None
    trailing_anchor: Optional[float] = None
    custom_rules: List[ExitRule] = field(default_factory=list)

    def refresh_active(self) -> None:
        self.active = any(
            value is not None
            for value in (
                self.stop_loss_price,
                self.take_profit_price,
                self.trailing_stop_pct,
                self.trailing_stop_amount,
            )
        ) or bool(self.custom_rules)

    def to_config(self) -> ExitConfig:
        return ExitConfig(
            order_id=self.order_id,
            symbol=self.symbol,
            portfolio=self.portfolio,
            active=self.active,
            stop_loss_price=self.stop_loss_price,
            take_profit_price=self.take_profit_price,
            trailing_stop_pct=self.trailing_stop_pct,
            trailing_stop_amount=self.trailing_stop_amount,
            trailing_anchor=self.trailing_anchor,
            custom_rules=tuple(rule.name for rule in self.custom_rules),
        )


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


def stop_loss_price(price: float, name: Optional[str] = None) -> ExitRule:
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")

    def condition(ctx: ExitContext) -> bool:
        if ctx.position.size > 0:
            return ctx.price <= price
        if ctx.position.size < 0:
            return ctx.price >= price
        return False

    return ExitRule(name=name or f"stop_loss_price_{price}", condition=condition)


def take_profit_price(price: float, name: Optional[str] = None) -> ExitRule:
    if price <= 0:
        raise ValueError(f"price must be positive, got {price}")

    def condition(ctx: ExitContext) -> bool:
        if ctx.position.size > 0:
            return ctx.price >= price
        if ctx.position.size < 0:
            return ctx.price <= price
        return False

    return ExitRule(name=name or f"take_profit_price_{price}", condition=condition)
