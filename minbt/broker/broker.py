from collections import Counter, OrderedDict
import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .exit import ExitConfig, ExitContext, ExitRule, _ExitState
from .market import Market
from .order import Order, OrderSource
from .portfolio import Portfolio
from .struct import DateType, Position, _require
from ..logger import logger as default_logger


DEFAULT_PORTFOLIO = "main"


class Broker:
    """
    交易经纪商。

    Broker 负责维护现金、持仓、订单、分仓和退出条件。策略只需要在回调中调用 Broker
    表达交易动作，不需要关心 Exchange 如何推进数据。
    """

    def __init__(
        self,
        initial_cash: float,
        fee_rate: float,
        *,
        leverage: float = 1.0,
        margin_mode: str = "cross",
        warning_margin_level: float = 0.2,
        min_margin_level: float = 0.1,
        market: Optional[Market] = None,
        logger=None,
    ):
        _require(initial_cash > 0, f"initial_cash must be greater than 0, initial_cash: {initial_cash}")
        _require(
            0 <= fee_rate < 1.0,
            f"fee_rate must be between 0 (inclusive) and 1.0 (exclusive), fee_rate: {fee_rate}",
        )
        _require(leverage >= 1.0, f"leverage must be greater than or equal to 1.0, leverage: {leverage}")
        _require(
            margin_mode in ("cross", "isolated"),
            f"margin_mode must be either cross or isolated, margin_mode: {margin_mode}",
        )
        _require(
            0 <= min_margin_level < 1.0,
            f"min_margin_level must be between 0 (inclusive) and 1.0 (exclusive), min_margin_level: {min_margin_level}",
        )
        _require(
            0 <= warning_margin_level < 1.0,
            f"warning_margin_level must be between 0 (inclusive) and 1.0 (exclusive), "
            f"warning_margin_level: {warning_margin_level}",
        )
        _require(
            min_margin_level < warning_margin_level,
            f"min_margin_level must be less than warning_margin_level, "
            f"warning_margin_level: {warning_margin_level}, min_margin_level: {min_margin_level}",
        )

        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.warning_margin_level = warning_margin_level
        self.min_margin_level = min_margin_level
        self._default_market = copy.copy(market) if market is not None else Market(name="Default")
        self._markets: Dict[str, Market] = {}
        self._symbol_market_names: Dict[str, str] = {}
        self._market_name_to_symbols: Dict[str, List[str]] = {}
        self.logger = logger or default_logger
        self.initial_cash = initial_cash

        self.portfolios: Dict[str, Portfolio] = {
            DEFAULT_PORTFOLIO: self._create_portfolio(initial_cash)
        }

        self.last_prices: Dict[str, float] = {}
        self.last_price_dates: Dict[str, DateType] = {}
        self._last_market_dt = None

        self.orders: "OrderedDict[str, Order]" = OrderedDict()
        self._order_seq = 0
        self._pending_order_ids: List[str] = []
        self._pending_exit_params: Dict[str, Dict[str, Any]] = {}

        self._exit_states: Dict[str, _ExitState] = {}
        self._active_exit_order_by_position: Dict[Tuple[str, str], str] = {}
        self._position_order_ids: Dict[Tuple[str, str], set] = {}

    def _create_portfolio(self, initial_cash: float) -> Portfolio:
        return Portfolio(
            initial_cash,
            fee_rate=self.fee_rate,
            leverage=self.leverage,
            margin_mode=self.margin_mode,
            warning_margin_level=self.warning_margin_level,
            min_margin_level=self.min_margin_level,
            logger=self.logger,
        )

    def _require_portfolio(self, portfolio: str) -> None:
        if portfolio not in self.portfolios:
            raise ValueError(f"portfolio not found: {portfolio}")

    def _resolve_portfolio(self, portfolio: Optional[str]) -> str:
        name = DEFAULT_PORTFOLIO if portfolio is None else portfolio
        self._require_portfolio(name)
        return name

    def _known_symbols(self) -> set:
        symbols = set(self.last_prices)
        symbols.update(self.last_price_dates)
        symbols.update(order.symbol for order in self.orders.values())
        for order_id in self._pending_order_ids:
            order = self.orders.get(order_id)
            if order is not None:
                symbols.add(order.symbol)
        for portfolio in self.portfolios.values():
            symbols.update(portfolio.positions)
        return symbols

    def _has_market_route_state(self) -> bool:
        if self.orders or self._pending_order_ids or self.last_prices or self.last_price_dates:
            return True
        return any(portfolio.positions for portfolio in self.portfolios.values())

    def _symbols_for_market(self, market_name: str) -> List[str]:
        return list(self._market_name_to_symbols.get(market_name, ()))

    def _default_market_symbols(self) -> List[str]:
        mapped_symbols = set(self._symbol_market_names)
        return sorted(symbol for symbol in self._known_symbols() if symbol not in mapped_symbols)

    def _market_for(self, symbol: str) -> Market:
        market_name = self._symbol_market_names.get(symbol)
        if market_name is None:
            return self._default_market
        return self._markets[market_name]

    def _on_new_dt(self, dt) -> None:
        for market_name, market in self._markets.items():
            market.on_new_dt(self, dt, symbols=self._symbols_for_market(market_name))
        self._default_market.on_new_dt(self, dt, symbols=self._default_market_symbols())

    def _next_order_id(self) -> str:
        self._order_seq += 1
        return f"order-{self._order_seq}"

    def _side(self, qty: float) -> str:
        if qty > 0:
            return "buy"
        if qty < 0:
            return "sell"
        return "none"

    def _create_order(
        self,
        *,
        symbol: str,
        portfolio: str,
        order_type: str,
        source: OrderSource,
        qty: float,
        status: str,
        requested_price: Optional[float] = None,
        limit_price: Optional[float] = None,
        filled_qty: float = 0.0,
        avg_price: Optional[float] = None,
        reason: Optional[str] = None,
        created_dt=None,
        updated_dt=None,
    ) -> Order:
        order = Order(
            id=self._next_order_id(),
            symbol=symbol,
            portfolio=portfolio,
            order_type=order_type,  # type: ignore[arg-type]
            source=source,
            side=self._side(qty),  # type: ignore[arg-type]
            qty=qty,
            status=status,  # type: ignore[arg-type]
            requested_price=requested_price,
            limit_price=limit_price,
            filled_qty=filled_qty,
            avg_price=avg_price,
            reason=reason,
            created_dt=created_dt,
            updated_dt=updated_dt,
        )
        self.orders[order.id] = order
        return order

    def _update_order(
        self,
        order: Order,
        *,
        status: str,
        filled_qty: Optional[float] = None,
        avg_price: Optional[float] = None,
        reason: Optional[str] = None,
        updated_dt=None,
    ) -> Order:
        order.status = status  # type: ignore[assignment]
        if filled_qty is not None:
            order.filled_qty = filled_qty
        if avg_price is not None:
            order.avg_price = avg_price
        order.reason = reason
        order.updated_dt = updated_dt
        return order

    def _exit_params_provided(
        self,
        *,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> bool:
        return any(
            value is not None
            for value in (
                stop_loss_price,
                take_profit_price,
                trailing_stop_pct,
                trailing_stop_amount,
            )
        )

    def _validate_exit_params(
        self,
        *,
        position_size: float,
        reference_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> None:
        self._validate_exit_values(
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        )
        if position_size == 0:
            return
        if position_size > 0:
            if stop_loss_price is not None and stop_loss_price >= reference_price:
                raise ValueError("stop_loss_price must be lower than reference price for a long position")
            if take_profit_price is not None and take_profit_price <= reference_price:
                raise ValueError("take_profit_price must be higher than reference price for a long position")
        else:
            if stop_loss_price is not None and stop_loss_price <= reference_price:
                raise ValueError("stop_loss_price must be higher than reference price for a short position")
            if take_profit_price is not None and take_profit_price >= reference_price:
                raise ValueError("take_profit_price must be lower than reference price for a short position")

    def _validate_exit_values(
        self,
        *,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> None:
        if trailing_stop_pct is not None and trailing_stop_amount is not None:
            raise ValueError("trailing_stop_pct and trailing_stop_amount cannot both be set")
        if stop_loss_price is not None and stop_loss_price <= 0:
            raise ValueError(f"stop_loss_price must be positive, got {stop_loss_price}")
        if take_profit_price is not None and take_profit_price <= 0:
            raise ValueError(f"take_profit_price must be positive, got {take_profit_price}")
        if trailing_stop_pct is not None and not (0 < trailing_stop_pct < 1):
            raise ValueError(f"trailing_stop_pct must be between 0 and 1, got {trailing_stop_pct}")
        if trailing_stop_amount is not None and trailing_stop_amount <= 0:
            raise ValueError(f"trailing_stop_amount must be positive, got {trailing_stop_amount}")

    def _validate_attached_exit_params(
        self,
        *,
        position_size: float,
        reference_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> None:
        if not self._exit_params_provided(
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        ):
            return
        self._validate_exit_params(
            position_size=position_size,
            reference_price=reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        )

    def _resolve_market_price(self, symbol: str, price: Optional[float], price_dt=None):
        if price is None:
            if price_dt is not None:
                raise ValueError("price_dt must be None when price is omitted")
            resolved_price, resolved_dt = self.get_last_price(symbol, return_dt=True)
            if resolved_price is None:
                raise ValueError(f"market price not found: {symbol}")
            return resolved_price, resolved_dt
        if price <= 0:
            raise ValueError(f"price must be positive, got {price}")
        if price_dt is None:
            price_dt = self.last_price_dates.get(symbol)
        self.on_new_price(symbol, price, price_dt)
        return price, price_dt

    def _clear_position_exit(self, portfolio: str, symbol: str) -> None:
        order_id = self._active_exit_order_by_position.pop((portfolio, symbol), None)
        if order_id is not None and order_id in self._exit_states:
            self._exit_states[order_id].active = False

    def _position_has_active_exit(self, portfolio: str, symbol: str, order_id: str) -> bool:
        return self._active_exit_order_by_position.get((portfolio, symbol)) == order_id

    def _get_or_create_exit_state(self, order: Order) -> _ExitState:
        state = self._exit_states.get(order.id)
        if state is None:
            state = _ExitState(
                order_id=order.id,
                symbol=order.symbol,
                portfolio=order.portfolio,
            )
            self._exit_states[order.id] = state
        return state

    def _activate_exit_state(self, order: Order, state: _ExitState) -> None:
        key = (order.portfolio, order.symbol)
        previous_id = self._active_exit_order_by_position.get(key)
        if previous_id is not None and previous_id != order.id:
            previous = self._exit_states.get(previous_id)
            if previous is not None:
                previous.active = False
        self._active_exit_order_by_position[key] = order.id
        state.refresh_active()

    def _activate_standard_exit(
        self,
        order: Order,
        *,
        reference_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> None:
        if not self._exit_params_provided(
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        ):
            return
        state = self._get_or_create_exit_state(order)
        if stop_loss_price is not None:
            state.stop_loss_price = stop_loss_price
        if take_profit_price is not None:
            state.take_profit_price = take_profit_price
        if trailing_stop_pct is not None:
            state.trailing_stop_pct = trailing_stop_pct
            state.trailing_stop_amount = None
            state.trailing_anchor = reference_price
        if trailing_stop_amount is not None:
            state.trailing_stop_amount = trailing_stop_amount
            state.trailing_stop_pct = None
            state.trailing_anchor = reference_price
        self._activate_exit_state(order, state)

    def _require_current_exit_order(self, order: Order) -> None:
        key = (order.portfolio, order.symbol)
        if order.id not in self._position_order_ids.get(key, set()):
            raise ValueError(f"order is no longer associated with the current position: {order.id}")

    def _after_order_filled(
        self,
        order: Order,
        *,
        old_size: float,
        price: float,
        dt,
        exit_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._market_for(order.symbol).on_order_filled(
            self,
            order.symbol,
            order.qty,
            price,
            dt=dt,
            portfolio=order.portfolio,
            old_size=old_size,
        )

        position = self.get_position(order.symbol, portfolio=order.portfolio)
        new_size = 0.0 if position is None else position.size
        key = (order.portfolio, order.symbol)
        if new_size == 0:
            self._position_order_ids.pop(key, None)
            self._clear_position_exit(order.portfolio, order.symbol)
            return
        if old_size == 0 or old_size * new_size < 0:
            self._position_order_ids[key] = {order.id}
            self._clear_position_exit(order.portfolio, order.symbol)
        else:
            self._position_order_ids.setdefault(key, set()).add(order.id)
        if exit_params and self._exit_params_provided(**exit_params):
            self._activate_standard_exit(order, reference_price=price, **exit_params)

    def _execute_existing_order(
        self,
        order: Order,
        *,
        price: float,
        price_dt=None,
        leverage: Optional[float] = None,
        exit_params: Optional[Dict[str, Any]] = None,
    ) -> Order:
        validation = self._market_for(order.symbol).validate_order(
            self,
            order.symbol,
            order.qty,
            price,
            dt=price_dt,
            portfolio=order.portfolio,
        )
        if not validation.ok:
            self.logger.warning(
                f"Order rejected: {order.symbol}, qty={order.qty}, price={price}, reason={validation.message}"
            )
            return self._update_order(order, status="rejected", reason=validation.message, updated_dt=price_dt)

        old_size = self.get_position_size(order.symbol, portfolio=order.portfolio)
        result = self.portfolios[order.portfolio].submit_order(
            order.symbol,
            order.qty,
            price=price,
            leverage=leverage,
            price_dt=price_dt,
        )
        if not result:
            return self._update_order(
                order,
                status="rejected",
                reason="portfolio rejected order",
                updated_dt=price_dt,
            )

        self._update_order(
            order,
            status="filled",
            filled_qty=order.qty,
            avg_price=price,
            updated_dt=price_dt,
        )
        self._after_order_filled(order, old_size=old_size, price=price, dt=price_dt, exit_params=exit_params)
        return order

    def add_portfolio(self, name: str, cash: float) -> None:
        """从主组合划拨现金创建新组合。"""
        if name in self.portfolios:
            raise ValueError(f"portfolio already exists: {name}")
        _require(cash > 0, f"cash must be greater than 0, cash: {cash}")
        source = self.portfolios[DEFAULT_PORTFOLIO]
        _require(
            cash <= source.free_cash,
            f"cash must be less than or equal to main portfolio free cash, cash: {cash}, free_cash: {source.free_cash}",
        )
        source._current_cash.change_cash(-cash)
        self.portfolios[name] = self._create_portfolio(cash)

    def add_market(self, name: str, market: Market, symbols: Sequence[str]) -> None:
        """为一组 symbol 添加市场规则路由。"""
        if not isinstance(name, str) or not name:
            raise ValueError("market name must be a non-empty string")
        if self._has_market_route_state():
            raise ValueError("add_market must be called before broker has orders, prices, or positions")
        if name == self._default_market.name:
            raise ValueError(f"market name conflicts with default market: {name}")
        if name in self._markets:
            raise ValueError(f"market already exists: {name}")
        if not isinstance(market, Market):
            raise TypeError("market must be a Market instance")
        if isinstance(symbols, (str, bytes)) or symbols is None:
            raise TypeError("symbols must be a non-empty list of strings")
        symbols = list(symbols)
        if not symbols:
            raise ValueError("symbols must be non-empty")
        for symbol in symbols:
            if not isinstance(symbol, str) or not symbol:
                raise ValueError(f"symbol must be a non-empty string: {symbol!r}")
            if symbol in self._symbol_market_names:
                raise ValueError(f"symbol already mapped to market: {symbol}")
        duplicate_symbols = {s for s, count in Counter(symbols).items() if count > 1}
        if duplicate_symbols:
            raise ValueError(f"duplicate symbols in market route: {sorted(duplicate_symbols)}")

        # Market 字段须保持不可变；新增 mutable 字段时改用 copy.deepcopy
        copied_market = copy.copy(market)
        copied_market.name = name
        self._markets[name] = copied_market
        self._market_name_to_symbols[name] = list(symbols)
        for symbol in symbols:
            self._symbol_market_names[symbol] = name

    def get_market(self, symbol: str) -> Market:
        """返回 symbol 当前市场规则的快照。"""
        return copy.copy(self._market_for(symbol))

    def on_new_price(self, symbol: str, price: float, dt: Optional[DateType] = None):
        _require(price > 0, f"price must be positive, price: {price}")
        if dt is not None and dt != self._last_market_dt:
            self._on_new_dt(dt)
            self._last_market_dt = dt
        self.last_prices[symbol] = price
        self.last_price_dates[symbol] = dt
        for portfolio in self.portfolios.values():
            portfolio.on_new_price(symbol, price, dt)

    def get_last_price(self, symbol: str, return_dt: bool = False):
        price = self.last_prices.get(symbol)
        if return_dt:
            return price, self.last_price_dates.get(symbol)
        return price

    def get_market_price(self, symbol: str, return_dt: bool = False):
        return self.get_last_price(symbol, return_dt)

    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> Order:
        return self._submit_market_order(
            symbol,
            qty,
            price,
            leverage=leverage,
            price_dt=price_dt,
            normalize_qty=False,
            portfolio=portfolio,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
            source="submit_market_order",
        )

    def _submit_market_order(
        self,
        symbol: str,
        qty: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        normalize_qty: bool = False,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
        source: OrderSource = "submit_market_order",
    ) -> Order:
        if qty == 0:
            raise ValueError(f"qty must be non-zero, got {qty}")
        portfolio = self._resolve_portfolio(portfolio)
        exec_price, resolved_dt = self._resolve_market_price(symbol, price, price_dt)

        if normalize_qty:
            qty = self._market_for(symbol).normalize_order_qty(self, symbol, qty, price=exec_price, portfolio=portfolio)
            if qty == 0:
                return self._create_order(
                    symbol=symbol,
                    portfolio=portfolio,
                    order_type="market",
                    source=source,
                    qty=0,
                    status="skipped",
                    requested_price=exec_price,
                    reason="target unchanged after quantity normalization",
                    created_dt=resolved_dt,
                    updated_dt=resolved_dt,
                )

        expected_position_size = self.get_position_size(symbol, portfolio=portfolio) + qty
        self._validate_attached_exit_params(
            position_size=expected_position_size,
            reference_price=exec_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        )
        exit_params = {
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "trailing_stop_pct": trailing_stop_pct,
            "trailing_stop_amount": trailing_stop_amount,
        }
        order = self._create_order(
            symbol=symbol,
            portfolio=portfolio,
            order_type="market",
            source=source,
            qty=qty,
            status="pending",
            requested_price=exec_price,
            created_dt=resolved_dt,
        )
        return self._execute_existing_order(
            order,
            price=exec_price,
            price_dt=resolved_dt,
            leverage=leverage,
            exit_params=exit_params,
        )

    def submit_limit_order(
        self,
        symbol: str,
        qty: float,
        limit_price: float,
        *,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> Order:
        if qty == 0:
            raise ValueError(f"qty must be non-zero, got {qty}")
        if limit_price <= 0:
            raise ValueError(f"limit_price must be positive, got {limit_price}")
        portfolio = self._resolve_portfolio(portfolio)
        if price_dt is None:
            price_dt = self.last_price_dates.get(symbol)
        self._validate_exit_values(
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        )
        validation = self._market_for(symbol).validate_order(
            self,
            symbol,
            qty,
            limit_price,
            dt=price_dt,
            portfolio=portfolio,
        )
        order = self._create_order(
            symbol=symbol,
            portfolio=portfolio,
            order_type="limit",
            source="submit_limit_order",
            qty=qty,
            status="pending",
            limit_price=limit_price,
            created_dt=price_dt,
        )
        if not validation.ok:
            return self._update_order(order, status="rejected", reason=validation.message, updated_dt=price_dt)

        can_submit, _ = self.portfolios[portfolio].can_submit_orders(
            [
                {
                    "symbol": symbol,
                    "qty": qty,
                    "price": limit_price,
                    "leverage": None,
                    "price_dt": price_dt,
                }
            ]
        )
        if not can_submit:
            return self._update_order(
                order,
                status="rejected",
                reason="portfolio rejected order during submission precheck",
                updated_dt=price_dt,
            )

        self._pending_order_ids.append(order.id)
        self._pending_exit_params[order.id] = {
            "stop_loss_price": stop_loss_price,
            "take_profit_price": take_profit_price,
            "trailing_stop_pct": trailing_stop_pct,
            "trailing_stop_amount": trailing_stop_amount,
        }
        return order

    def cancel_order(self, order_id: str) -> Order:
        if order_id not in self.orders:
            raise ValueError(f"order not found: {order_id}")
        order = self.orders[order_id]
        if order.status != "pending":
            return order
        self._pending_order_ids = [pending_id for pending_id in self._pending_order_ids if pending_id != order_id]
        self._pending_exit_params.pop(order_id, None)
        self._update_order(order, status="canceled", reason="canceled by user")
        return self._create_order(
            symbol=order.symbol,
            portfolio=order.portfolio,
            order_type=order.order_type,
            source="cancel_order",
            qty=0,
            status="canceled",
            reason=f"order canceled: {order_id}",
            updated_dt=order.updated_dt,
        )

    def process_pending_orders(self, dt=None) -> None:
        for order_id in list(self._pending_order_ids):
            order = self.orders.get(order_id)
            if order is None or order.status != "pending":
                self._pending_order_ids.remove(order_id)
                self._pending_exit_params.pop(order_id, None)
                continue
            current_price = self.last_prices.get(order.symbol)
            if current_price is None:
                continue
            if order.qty > 0:
                should_fill = current_price <= order.limit_price
            else:
                should_fill = current_price >= order.limit_price
            if not should_fill:
                continue
            exit_params = self._pending_exit_params.get(order_id, {})
            expected_position_size = self.get_position_size(
                order.symbol,
                portfolio=order.portfolio,
            ) + order.qty
            try:
                self._validate_attached_exit_params(
                    position_size=expected_position_size,
                    reference_price=order.limit_price,
                    **exit_params,
                )
            except ValueError as exc:
                self._pending_order_ids.remove(order_id)
                self._pending_exit_params.pop(order_id, None)
                self._update_order(
                    order,
                    status="rejected",
                    reason=f"exit conditions invalid at fill: {exc}",
                    updated_dt=dt,
                )
                continue
            self._pending_order_ids.remove(order_id)
            exit_params = self._pending_exit_params.pop(order_id, None)
            fill_dt = dt if dt is not None else self.last_price_dates.get(order.symbol)
            self._execute_existing_order(
                order,
                price=order.limit_price,
                price_dt=fill_dt,
                leverage=None,
                exit_params=exit_params,
            )

    def order_target_size(
        self,
        symbol: str,
        target_size: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> Order:
        return self._order_target_size(
            symbol,
            target_size,
            price,
            leverage=leverage,
            price_dt=price_dt,
            portfolio=portfolio,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
            source="target_size",
        )

    def _order_target_size(
        self,
        symbol: str,
        target_size: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
        source: OrderSource = "target_size",
    ) -> Order:
        portfolio = self._resolve_portfolio(portfolio)
        current_size = self.get_position_size(symbol, portfolio=portfolio)
        qty = target_size - current_size
        if qty == 0:
            return self._create_order(
                symbol=symbol,
                portfolio=portfolio,
                order_type="market",
                source=source,
                qty=0,
                status="skipped",
                reason="target size unchanged",
                created_dt=price_dt,
                updated_dt=price_dt,
            )
        return self._submit_market_order(
            symbol,
            qty=qty,
            price=price,
            leverage=leverage,
            price_dt=price_dt,
            normalize_qty=True,
            portfolio=portfolio,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
            source=source,
        )

    def order_target_value(
        self,
        symbol: str,
        target_value: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> Order:
        return self._order_target_value(
            symbol,
            target_value,
            price,
            leverage=leverage,
            price_dt=price_dt,
            portfolio=portfolio,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
            source="target_value",
        )

    def _order_target_value(
        self,
        symbol: str,
        target_value: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
        source: OrderSource = "target_value",
    ) -> Order:
        portfolio = self._resolve_portfolio(portfolio)
        exec_price, resolved_dt = self._resolve_market_price(symbol, price, price_dt)
        target_size = target_value / exec_price
        return self._order_target_size(
            symbol,
            target_size=target_size,
            price=exec_price,
            leverage=leverage,
            price_dt=resolved_dt,
            portfolio=portfolio,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
            source=source,
        )

    def order_target_percent(
        self,
        symbol: str,
        target_percent: float,
        price: Optional[float] = None,
        *,
        leverage: Optional[float] = None,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> Order:
        portfolio = self._resolve_portfolio(portfolio)
        exec_price, resolved_dt = self._resolve_market_price(symbol, price, price_dt)
        equity = self.get_equity(portfolio=portfolio)
        target_value = equity * target_percent
        return self._order_target_value(
            symbol,
            target_value=target_value,
            price=exec_price,
            leverage=leverage,
            price_dt=resolved_dt,
            portfolio=portfolio,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
            source="target_percent",
        )

    def close_position(
        self,
        symbol: str,
        price: Optional[float] = None,
        *,
        price_dt: Optional[DateType] = None,
        portfolio: Optional[str] = None,
    ) -> Order:
        portfolio = self._resolve_portfolio(portfolio)
        position = self.get_position(symbol, portfolio=portfolio)
        if position is None or position.is_empty():
            return self._create_order(
                symbol=symbol,
                portfolio=portfolio,
                order_type="market",
                source="close_position",
                qty=0,
                status="skipped",
                reason="position is empty",
                created_dt=price_dt,
                updated_dt=price_dt,
            )
        return self._submit_market_order(
            symbol,
            qty=-position.size,
            price=price,
            price_dt=price_dt,
            portfolio=portfolio,
            source="close_position",
        )

    def close_portfolio(self, portfolio: str) -> List[Order]:
        portfolio = self._resolve_portfolio(portfolio)
        close_plan = []
        for symbol, position in list(self.portfolios[portfolio].positions.items()):
            if position is None or position.is_empty():
                continue
            price, price_dt = self.get_last_price(symbol, return_dt=True)
            if price is None:
                return [
                    self._create_order(
                        symbol=symbol,
                        portfolio=portfolio,
                        order_type="market",
                        source="close_portfolio",
                        qty=-position.size,
                        status="rejected",
                        reason=f"market price not found: {symbol}",
                    )
                ]
            validation = self._market_for(symbol).validate_order(
                self,
                symbol,
                -position.size,
                price,
                dt=price_dt,
                portfolio=portfolio,
            )
            if not validation.ok:
                return [
                    self._create_order(
                        symbol=symbol,
                        portfolio=portfolio,
                        order_type="market",
                        source="close_portfolio",
                        qty=-position.size,
                        status="rejected",
                        requested_price=price,
                        reason=validation.message,
                        created_dt=price_dt,
                        updated_dt=price_dt,
                    )
                ]
            close_plan.append((symbol, price, price_dt))

        if not close_plan:
            if portfolio != DEFAULT_PORTFOLIO:
                closed_portfolio = self.portfolios.pop(portfolio)
                self.portfolios[DEFAULT_PORTFOLIO]._current_cash.change_cash(closed_portfolio.total_cash)
            return [
                self._create_order(
                    symbol="*",
                    portfolio=portfolio,
                    order_type="market",
                    source="close_portfolio",
                    qty=0,
                    status="skipped",
                    reason="portfolio has no open positions",
                )
            ]

        preview_orders = []
        for symbol, price, price_dt in close_plan:
            position = self.get_position(symbol, portfolio=portfolio)
            preview_orders.append(
                {
                    "symbol": symbol,
                    "qty": -position.size,
                    "price": price,
                    "leverage": None,
                    "price_dt": price_dt,
                }
            )
        can_close_all, failed_index = self.portfolios[portfolio].can_submit_orders(preview_orders)
        if not can_close_all:
            failed = preview_orders[failed_index]
            return [
                self._create_order(
                    symbol=failed["symbol"],
                    portfolio=portfolio,
                    order_type="market",
                    source="close_portfolio",
                    qty=failed["qty"],
                    status="rejected",
                    requested_price=failed["price"],
                    reason="portfolio rejected atomic close plan",
                    created_dt=failed["price_dt"],
                    updated_dt=failed["price_dt"],
                )
            ]

        orders = []
        for symbol, price, price_dt in close_plan:
            position = self.get_position(symbol, portfolio=portfolio)
            order = self._submit_market_order(
                symbol,
                qty=-position.size,
                price=price,
                price_dt=price_dt,
                portfolio=portfolio,
                source="close_portfolio",
            )
            orders.append(order)

        if portfolio != DEFAULT_PORTFOLIO and all(order.status == "filled" for order in orders):
            closed_portfolio = self.portfolios.pop(portfolio)
            self.portfolios[DEFAULT_PORTFOLIO]._current_cash.change_cash(closed_portfolio.total_cash)
        return orders

    def set_exit(
        self,
        order_id: str,
        *,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        trailing_stop_pct: Optional[float] = None,
        trailing_stop_amount: Optional[float] = None,
    ) -> ExitConfig:
        if not self._exit_params_provided(
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        ):
            raise ValueError("at least one exit condition must be provided")
        if order_id not in self.orders:
            raise ValueError(f"order not found: {order_id}")
        order = self.orders[order_id]
        if order.status != "filled":
            raise ValueError(f"exit can only be set for a filled order, got {order.status}")
        self._require_current_exit_order(order)
        position = self.get_position(order.symbol, portfolio=order.portfolio)
        if position is None or position.is_empty():
            raise ValueError(f"position is empty: {order.symbol}")
        reference_price = self.get_last_price(order.symbol) or order.avg_price
        self._validate_exit_params(
            position_size=position.size,
            reference_price=reference_price,
            stop_loss_price=stop_loss_price,
            take_profit_price=take_profit_price,
            trailing_stop_pct=trailing_stop_pct,
            trailing_stop_amount=trailing_stop_amount,
        )
        state = self._get_or_create_exit_state(order)
        if stop_loss_price is not None:
            state.stop_loss_price = stop_loss_price
        if take_profit_price is not None:
            state.take_profit_price = take_profit_price
        if trailing_stop_pct is not None:
            state.trailing_stop_pct = trailing_stop_pct
            state.trailing_stop_amount = None
            state.trailing_anchor = reference_price
        if trailing_stop_amount is not None:
            state.trailing_stop_amount = trailing_stop_amount
            state.trailing_stop_pct = None
            state.trailing_anchor = reference_price
        self._activate_exit_state(order, state)
        return state.to_config()

    def clear_exit(
        self,
        order_id: str,
        *,
        stop_loss_price: bool = True,
        take_profit_price: bool = True,
        trailing_stop: bool = True,
        custom: bool = True,
    ) -> ExitConfig:
        if not any((stop_loss_price, take_profit_price, trailing_stop, custom)):
            raise ValueError("at least one clear flag must be true")
        if order_id not in self.orders:
            raise ValueError(f"order not found: {order_id}")
        order = self.orders[order_id]
        state = self._exit_states.get(order_id)
        if state is None:
            state = self._get_or_create_exit_state(order)
            return state.to_config()
        if stop_loss_price:
            state.stop_loss_price = None
        if take_profit_price:
            state.take_profit_price = None
        if trailing_stop:
            state.trailing_stop_pct = None
            state.trailing_stop_amount = None
            state.trailing_anchor = None
        if custom:
            state.custom_rules.clear()
        state.refresh_active()
        if not state.active and self._position_has_active_exit(order.portfolio, order.symbol, order_id):
            self._active_exit_order_by_position.pop((order.portfolio, order.symbol), None)
        return state.to_config()

    def get_exit(self, order_id: str) -> Optional[ExitConfig]:
        state = self._exit_states.get(order_id)
        return None if state is None else state.to_config()

    def add_exit(
        self,
        order_id: str,
        *,
        name: Optional[str] = None,
        condition,
        state=None,
    ) -> ExitRule:
        if order_id not in self.orders:
            raise ValueError(f"order not found: {order_id}")
        order = self.orders[order_id]
        if order.status != "filled":
            raise ValueError(f"exit can only be set for a filled order, got {order.status}")
        self._require_current_exit_order(order)
        resolved_state = state() if callable(state) else state
        if resolved_state is None:
            resolved_state = {}
        if not isinstance(resolved_state, dict):
            raise TypeError("state must be a dict, a callable returning dict, or None")
        rule = ExitRule(
            name=name or getattr(condition, "__name__", "exit_rule"),
            condition=condition,
            state=resolved_state,
        )
        exit_state = self._get_or_create_exit_state(order)
        exit_state.custom_rules.append(rule)
        self._activate_exit_state(order, exit_state)
        return rule

    def check_exit_rules(self, dt=None, data=None) -> None:
        for order_id, state in list(self._exit_states.items()):
            if not state.active:
                continue
            order = self.orders.get(order_id)
            if order is None or order.status != "filled":
                state.active = False
                continue
            if not self._position_has_active_exit(order.portfolio, order.symbol, order_id):
                continue
            position = self.get_position(order.symbol, portfolio=order.portfolio)
            if position is None or position.is_empty():
                state.active = False
                key = (order.portfolio, order.symbol)
                self._active_exit_order_by_position.pop(key, None)
                self._position_order_ids.pop(key, None)
                continue
            price = self.get_last_price(order.symbol)
            if price is None:
                continue
            reason = self._exit_trigger_reason(state, order, position, price, dt, data)
            if reason is None:
                continue
            close_order = self.close_position(order.symbol, price=price, price_dt=dt, portfolio=order.portfolio)
            if close_order.status == "filled":
                state.active = False
                self._active_exit_order_by_position.pop((order.portfolio, order.symbol), None)
                self.logger.info(f"Exit triggered: order={order_id}, symbol={order.symbol}, reason={reason}, dt={dt}")
            else:
                self.logger.warning(
                    f"Exit rejected: order={order_id}, symbol={order.symbol}, reason={reason}, dt={dt}, "
                    f"order_status={close_order.status}"
                )

    def _exit_trigger_reason(
        self,
        config: _ExitState,
        order: Order,
        position: Position,
        price: float,
        dt,
        data,
    ) -> Optional[str]:
        if position.size > 0:
            if config.stop_loss_price is not None and price <= config.stop_loss_price:
                return "stop_loss_price"
            if config.take_profit_price is not None and price >= config.take_profit_price:
                return "take_profit_price"
            if config.trailing_stop_pct is not None or config.trailing_stop_amount is not None:
                config.trailing_anchor = price if config.trailing_anchor is None else max(config.trailing_anchor, price)
                if config.trailing_stop_pct is not None:
                    stop_price = config.trailing_anchor * (1 - config.trailing_stop_pct)
                else:
                    stop_price = config.trailing_anchor - config.trailing_stop_amount
                if price <= stop_price:
                    return "trailing_stop"
        else:
            if config.stop_loss_price is not None and price >= config.stop_loss_price:
                return "stop_loss_price"
            if config.take_profit_price is not None and price <= config.take_profit_price:
                return "take_profit_price"
            if config.trailing_stop_pct is not None or config.trailing_stop_amount is not None:
                config.trailing_anchor = price if config.trailing_anchor is None else min(config.trailing_anchor, price)
                if config.trailing_stop_pct is not None:
                    stop_price = config.trailing_anchor * (1 + config.trailing_stop_pct)
                else:
                    stop_price = config.trailing_anchor + config.trailing_stop_amount
                if price >= stop_price:
                    return "trailing_stop"

        for rule in list(config.custom_rules):
            ctx = ExitContext(
                order_id=order.id,
                symbol=order.symbol,
                portfolio=order.portfolio,
                dt=dt,
                price=price,
                position=position,
                broker=self,
                data=data,
                state=rule.get_state(),
            )
            if rule.condition(ctx):
                return rule.name
        return None

    def get_order(self, order_id: str) -> Optional[Order]:
        return self.orders.get(order_id)

    def get_orders(
        self,
        *,
        portfolio: Optional[str] = None,
        symbol: Optional[str] = None,
    ) -> List[Order]:
        if portfolio is not None:
            self._require_portfolio(portfolio)
        return [
            order
            for order in self.orders.values()
            if (portfolio is None or order.portfolio == portfolio)
            and (symbol is None or order.symbol == symbol)
            and order.source != "cancel_order"
        ]

    def get_active_order(self, symbol: str, *, portfolio: Optional[str] = None) -> Optional[Order]:
        portfolio = self._resolve_portfolio(portfolio)
        order_id = self._active_exit_order_by_position.get((portfolio, symbol))
        if order_id is None:
            return None
        return self.orders.get(order_id)

    def get_all_portfolio_equity(self) -> float:
        return sum(portfolio.get_portfolio_equity() for portfolio in self.portfolios.values())

    def get_total_equity(self) -> float:
        return self.get_all_portfolio_equity()

    def get_portfolios(self) -> List[str]:
        return list(self.portfolios.keys())

    def get_portfolio_equity(self, portfolio: Optional[str] = None) -> float:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_portfolio_equity()

    def get_portfolio_initial_cash(self, portfolio: Optional[str] = None) -> float:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].initial_cash

    def get_equity(self, portfolio: Optional[str] = None) -> float:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_portfolio_equity()

    def get_cash(self, portfolio: Optional[str] = None, include_locked: bool = False) -> float:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_cash(include_locked)

    def get_position(
        self,
        symbol: str,
        portfolio: Optional[str] = None,
    ) -> Optional[Position]:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_position(symbol, create_if_missing=False)

    def get_position_size(self, symbol: str, portfolio: Optional[str] = None) -> float:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_position_size(symbol)

    def get_position_sizes(self, portfolio: Optional[str] = None) -> Dict[str, float]:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_position_sizes()

    def get_positions(self, portfolio: Optional[str] = None) -> Dict[str, Position]:
        portfolio = self._resolve_portfolio(portfolio)
        return self.portfolios[portfolio].get_positions()
