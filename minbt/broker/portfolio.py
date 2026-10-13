from math import fsum
from typing import Callable, Dict, List, Literal, Optional, Tuple
import copy
import numpy as np
from ..logger import logger as default_logger
from .struct import Position, Cash, DateType, _require
from .pnl import Pnl, PnlReason, PnlRecord, _sum_pnl
from .._validation import _finite_sum, finite_number, positive_number
from ..data.model import normalize_symbol


class _PreviewLogger:
    def __getattr__(self, name):
        return lambda *args, **kwargs: None


class Portfolio:
    
    def __init__(self, 
                 initial_cash: float,
                 fee_rate: float,
                 leverage: float = 1.0,
                 margin_mode: Literal['cross', 'isolated'] = 'cross',
                 warning_margin_level: float = 0.2,
                 min_margin_level: float = 0.1 ,
                 logger=None,
                 *,
                 name: str = "main"):
        """
        初始化Portfolio
        
        Args:
            initial_cash: 初始现金, >0
            fee_rate: 手续费率, 0 <= fee_rate < 1
            leverage: 杠杆倍数, >=1.0
            margin_mode: 保证金模式, cross[全仓]或isolated[逐仓]
            warning_margin_level: 警告保证金水平, 0-1
            min_margin_level: 最小保证金水平, 0-1s
            name: 记账所属分仓名称，独立使用时默认为 main
        """
        initial_cash = positive_number(initial_cash, "initial_cash")
        fee_rate = finite_number(fee_rate, "fee_rate")
        leverage = finite_number(leverage, "leverage")
        warning_margin_level = finite_number(warning_margin_level, "warning_margin_level")
        min_margin_level = finite_number(min_margin_level, "min_margin_level")
        _require(0 <= fee_rate < 1, f'fee_rate must be between 0 and 1, got {fee_rate}')
        _require(leverage >= 1, f'leverage must be greater than or equal to 1, got {leverage}')
        _require(margin_mode in ['cross', 'isolated'], f'margin_mode must be either cross or isolated, got {margin_mode}')
        _require(0 <= min_margin_level < 1, f'min_margin_level must be between 0 and 1, got {min_margin_level}')
        _require(0 <= warning_margin_level < 1, f'warning_margin_level must be between 0 and 1, got {warning_margin_level}')
        _require(
            min_margin_level < warning_margin_level,
            f'min_margin_level must be less than warning_margin_level, got {min_margin_level=} and {warning_margin_level=}',
        )
        if not isinstance(name, str):
            raise TypeError("portfolio name must be a string")
        if not name.strip():
            raise ValueError("portfolio name must not be empty")
        self.initial_cash = initial_cash
        self.fee_rate = fee_rate
        self.leverage = leverage
        self.margin_mode = margin_mode
        self.warning_margin_level = warning_margin_level
        self.min_margin_level = min_margin_level
        self.logger = logger or default_logger
        self.name = name  # 记账所属分仓名称，独立 Portfolio 默认使用 main。
        # Broker 接入实际记账日志；预检副本禁用此回调，避免污染真实记录。
        self._pnl_record_sink: Optional[Callable[[PnlRecord], None]] = None
        self.reset()
            
    def reset(self):
        """重置独立分仓的资金、持仓和统计；Broker 管理的分仓由 Broker 统一维护。"""
        self.last_prices = {}
        self.last_prices_dt = {}
        self._bankrupt = False
        self._current_cash = Cash(self.initial_cash, self.initial_cash)
        self._positions: Dict[str, Position] = {}
        self._booked_pnl: Dict[Optional[str], Pnl] = {}  # 按标的累计已结算盈亏，不保存未实现盈亏。
        self._pnl_records: List[PnlRecord] = []  # 本分仓实际记账明细，重置时清空。

    def _record_pnl(
        self,
        *,
        symbol: Optional[str],
        qty: float,
        price: Optional[float],
        realized_pnl: float,
        fees: float = 0.0,
        settlement_adjustment: float = 0.0,
        order_id: Optional[str] = None,
        reason: PnlReason = "trade",
        dt: Optional[DateType] = None,
    ) -> None:
        """仅记录已经提交的成交或结算，汇总和明细使用同一份实际金额。"""
        record = PnlRecord(
            portfolio=self.name,
            symbol=symbol,
            qty=qty,
            price=price,
            realized_pnl=realized_pnl,
            fees=fees,
            settlement_adjustment=settlement_adjustment,
            order_id=order_id,
            reason=reason,
            dt=dt,
        )
        self._booked_pnl[symbol] = _sum_pnl((
            self._booked_pnl.get(symbol, Pnl()),
            Pnl(realized_pnl=realized_pnl, fees=fees, settlement_adjustment=settlement_adjustment),
        ))
        self._pnl_records.append(record)
        if self._pnl_record_sink is not None:
            self._pnl_record_sink(record)

    def get_pnl(self, symbol: Optional[str] = None) -> Pnl:
        """查询本生命周期累计盈亏；未知标的返回零值，不创建持仓。"""
        if symbol is not None:
            symbol = normalize_symbol(symbol)
        if symbol is None:
            booked = _sum_pnl(self._booked_pnl.values())
            unrealized_pnl = fsum(position.unrealized_pnl for position in self._positions.values())
        else:
            booked = self._booked_pnl.get(symbol, Pnl())
            position = self._positions.get(symbol)
            unrealized_pnl = 0.0 if position is None else position.unrealized_pnl
        return Pnl(
            realized_pnl=booked.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            fees=booked.fees,
            settlement_adjustment=booked.settlement_adjustment,
        )

    def get_pnl_records(self, symbol: Optional[str] = None) -> List[PnlRecord]:
        """返回本生命周期明细的新列表，记录本身不可变。"""
        if symbol is not None:
            symbol = normalize_symbol(symbol)
        return [record for record in self._pnl_records if symbol is None or record.symbol == symbol]

    def _mark_position_bankrupt(self, symbol: str, dt: Optional[DateType] = None) -> None:
        """逐仓穿仓只清零该仓位保证金，用结算调整保留毛亏损和实际损失。"""
        position = self._positions[symbol]
        qty, price = -position.size, position.last_price
        realized_pnl = position.unrealized_pnl
        settlement_adjustment = -position.equity
        position.mark_bankrupt()
        self._record_pnl(
            symbol=symbol,
            qty=qty,
            price=price,
            realized_pnl=realized_pnl,
            settlement_adjustment=settlement_adjustment,
            reason="bankruptcy",
            dt=dt if dt is not None else self.last_prices_dt.get(symbol),
        )
    
    def mark_bankrupt(self, dt: Optional[DateType] = None) -> None:
        """全仓清零并保留毛盈亏与账户结算调整，重复调用不重复记账。"""
        if self._bankrupt:
            return
        equity_before = self.get_portfolio_equity()
        for symbol, position in self._positions.items():
            if not position.is_empty():
                self._record_pnl(
                    symbol=symbol,
                    qty=-position.size,
                    price=position.last_price,
                    realized_pnl=position.unrealized_pnl,
                    reason="bankruptcy",
                    dt=dt if dt is not None else self.last_prices_dt.get(symbol),
                )
        if equity_before != 0:
            # 全仓清零是账户结算，不把债务减免或资产核销归到某个标的。
            self._record_pnl(
                symbol=None,
                qty=0.0,
                price=None,
                realized_pnl=0.0,
                settlement_adjustment=-equity_before,
                reason="bankruptcy_settlement",
                dt=dt,
            )
        self._bankrupt = True
        self._positions.clear()
        self._current_cash = Cash(0.0, 0.0)
        
    def get_all_positions_total_margin(self) -> float:
        return _finite_sum((position.margin for position in self._positions.values()), "portfolio margin")
    
    def get_all_positions_total_equity(self) -> float:
        return _finite_sum((position.equity for position in self._positions.values()), "positions equity")

    def get_portfolio_margin_level(self) -> float:
        if self._bankrupt:
            return -1.0
        total_margin = self.get_all_positions_total_margin()
        if total_margin == 0:
            return 1.0
        if self.margin_mode == 'cross':
            equity = self.get_portfolio_equity()
        else:
            equity = self.get_all_positions_total_equity()
        return equity / total_margin

    def get_portfolio_equity(self) -> float:
        return _finite_sum((self.get_all_positions_total_equity(), self.total_cash), "portfolio equity")

    def _preview_mark_prices(self, prices):
        """验证一组行情影响的候选持仓与账户金额，不先写行情或推进风险。"""
        positions = []
        for symbol, position in self._positions.items():
            candidate = position
            if symbol in prices and not position.is_empty():
                candidate = copy.copy(position)
                candidate.update_price_and_pnl(prices[symbol])
            positions.append(candidate)
        _finite_sum((p.margin for p in positions), "portfolio margin")
        positions_equity = _finite_sum((p.equity for p in positions), "positions equity")
        equity = _finite_sum((self.total_cash, positions_equity), "portfolio equity")
        if self.margin_mode == "isolated":
            # 逐仓穿仓清掉负权益，不能在此后才发现账户总金额溢出。
            return _finite_sum((self.total_cash, *(max(0, p.equity) for p in positions)), "portfolio equity")
        return max(0, equity)
    
    def on_new_price(self, 
                     symbol: str, 
                     price: float, 
                     dt: Optional[DateType] = None,
                     *, risk_dt: Optional[DateType] = None) -> Tuple[bool, bool, float]:
        """
        更新价格，更新各仓位的未实现盈亏，并检查保证金水平
        
        Args:
            symbol: 标的代码
            price: 最新价格
            risk_dt: 实际风险结算时间；省略时使用报价时间 dt
        
        Returns:
            bankrupt: 是否穿仓
                当为逐仓模式时，指的是单个仓位穿仓，不会导致账户破产
                当为全仓模式时，指的是账户穿仓，会导致账户破产
            liquidated: 是否达到强平水平
            margin_level: 保证金水平
        """
        symbol = normalize_symbol(symbol)
        price = positive_number(price, "price")
        risk_dt = dt if risk_dt is None else risk_dt
        if self._bankrupt:
            return True, False, 0.0

        self._preview_mark_prices({symbol: price})
        
        liquidated, bankrupt = False, False
        self.last_prices[symbol] = price
        self.last_prices_dt[symbol] = dt
        margin_level = self._update_pnl_get_margin_level(symbol, price, dt)
        if margin_level < 0:
            bankrupt, liquidated = True, True
            self.logger.error(f'[{self.margin_mode}] {symbol} bankrupt, margin_level: {margin_level}')
            if self.margin_mode == 'isolated':
                position = self.get_position(symbol)
                self._mark_position_bankrupt(symbol, risk_dt)
                _require(position.size == 0, f'{symbol} is not closed after bankruptcy', RuntimeError)
            else:
                self.mark_bankrupt(risk_dt)
        elif margin_level <= self.min_margin_level:
            liquidated = True
            if self.margin_mode == 'isolated':
                self.logger.warning(f'[{self.margin_mode}] {symbol} reach liquidation, margin_level: {margin_level}')
                self._pure_close_position(symbol, dt=risk_dt) # price 已经在_update_pnl_get_margin_level更新过了
                _require(self.get_position(symbol).size == 0, f'{symbol} is not closed', RuntimeError)
            else:
                self.logger.warning(f'[{self.margin_mode}] Reach liquidation, close all positions')
                self._pure_close_all_positions(dt=risk_dt)
                _require(self.get_all_positions_total_equity() == 0, 'All positions are not closed', RuntimeError)
        elif margin_level <= self.warning_margin_level:
            self.logger.warning(f'[{self.margin_mode}] margin level is too low, margin_level: {margin_level}')

        return bankrupt, liquidated, margin_level

    def update_market_batch(
        self,
        prices: Dict[str, float],
        dt: Optional[DateType] = None,
    ) -> Tuple[bool, bool, float]:
        """批量更新同一时间点的所有市场价格。

        先更新所有仓位，再计算组合保证金，避免全仓模式下结果依赖 symbol 的
        迭代顺序。单价入口 `on_new_price` 仍服务订单内部的显式价格处理。
        """

        normalized = {normalize_symbol(symbol): positive_number(price, "price") for symbol, price in prices.items()}
        if self._bankrupt:
            return True, False, 0.0
        self._preview_mark_prices(normalized)
        for symbol, price in normalized.items():
            self.last_prices[symbol] = price
            self.last_prices_dt[symbol] = dt

        for symbol, position in self._positions.items():
            price = normalized.get(symbol)
            if price is not None and not position.is_empty():
                position.update_price_and_pnl(price, dt)

        if self.margin_mode == 'isolated':
            bankrupt = False
            liquidated = False
            lowest_margin_level = float('inf')
            for symbol, position in list(self._positions.items()):
                if position.is_empty():
                    continue
                margin_level = position.margin_level
                lowest_margin_level = min(lowest_margin_level, margin_level)
                if margin_level < 0:
                    self.logger.error(f'[{self.margin_mode}] {symbol} bankrupt, margin_level: {margin_level}')
                    self._mark_position_bankrupt(symbol, dt)
                    bankrupt = True
                    liquidated = True
                    continue
                if margin_level <= self.min_margin_level:
                    self.logger.warning(
                        f'[{self.margin_mode}] {symbol} reach liquidation, margin_level: {margin_level}'
                    )
                    self._pure_close_position(symbol, normalized.get(symbol), dt=dt)
                    liquidated = True
                    continue
                if margin_level <= self.warning_margin_level:
                    self.logger.warning(
                        f'[{self.margin_mode}] margin level is too low, margin_level: {margin_level}'
                    )
            if bankrupt or liquidated:
                return bankrupt, liquidated, lowest_margin_level
            return False, False, self.get_portfolio_margin_level()

        margin_level = self.get_portfolio_margin_level()
        if margin_level < 0:
            self.logger.error(f'[{self.margin_mode}] portfolio bankrupt, margin_level: {margin_level}')
            self.mark_bankrupt(dt)
            return True, True, margin_level
        if margin_level <= self.min_margin_level:
            self.logger.warning(f'[{self.margin_mode}] Reach liquidation, close all positions')
            self._pure_close_all_positions(normalized, dt=dt)
            return False, True, margin_level
        if margin_level <= self.warning_margin_level:
            self.logger.warning(f'[{self.margin_mode}] margin level is too low, margin_level: {margin_level}')
        return False, False, margin_level
    
    def _update_pnl_get_margin_level(self, 
                                     symbol: str, 
                                     last_price: float, 
                                     dt: Optional[DateType] = None) -> float:
        """
        更新最小仓位收益并获取保证金水平
        
        Args:
            symbol: 标的代码
            last_price: 最新价格
        
        Returns:
            margin_level: 保证金水平
        """
        position = self.get_position(symbol, create_if_missing=False)
        if position is None:
            return self.get_portfolio_margin_level() if self.margin_mode == 'cross' else 1.0
        position.update_price_and_pnl(last_price, dt)
        if self.margin_mode == 'isolated':
            margin_level = position.margin_level
        else:
            margin_level = self.get_portfolio_margin_level()
        return margin_level

    @staticmethod
    def _validate_pnl_totals(booked, unrealized):
        """预检完整记账结果，汇总溢出必须发生在成交提交之前。"""
        totals = [
            _finite_sum((getattr(pnl, name) for pnl in booked), name)
            for name in ("realized_pnl", "fees", "settlement_adjustment")
        ]
        _finite_sum((totals[0], unrealized, -totals[1], totals[2]), "net pnl")

    def _preview_order(self, symbol, qty, price, leverage, mark_price, mark_dt=None):
        """完整计算候选成交，不修改行情、现金、持仓或盈亏账本。"""
        position = self.get_position(symbol, create_if_missing=False)
        candidate = Position(symbol=symbol) if position is None else copy.deepcopy(position)
        finite_number(abs(qty) * price, "order notional")
        fee = finite_number(self.calculate_fee(symbol, leverage, qty, price), "order fee")
        _, released_margin, realized_pnl = candidate.commit_order(price, qty=qty, leverage=leverage)
        finite_number(released_margin, "released margin")
        finite_number(realized_pnl, "realized pnl")
        candidate.update_price_and_pnl(mark_price, mark_dt)
        for name in ("size", "cost_price", "margin", "unrealized_pnl", "equity"):
            finite_number(getattr(candidate, name), f"position {name}")
        _finite_sum((candidate.margin, *(p.margin for s, p in self._positions.items() if s != symbol)), "portfolio margin")
        released_cash = _finite_sum((released_margin, realized_pnl, -fee), "released cash")
        free_cash, total_cash = self._current_cash._preview_change_cash(released_cash)
        positions_equity = _finite_sum((
            candidate.equity,
            *(p.equity for s, p in self._positions.items() if s != symbol),
        ), "positions equity")
        equity = _finite_sum((total_cash, positions_equity), "portfolio equity")
        # 连同累计统计验证，避免成交已经提交后才在记账求和时溢出。
        booked = list(self._booked_pnl.values())
        booked.append(Pnl(realized_pnl=realized_pnl, fees=fee))
        self._validate_pnl_totals((self._booked_pnl.get(symbol, Pnl()), booked[-1]), 0)
        unrealized = _finite_sum((
            candidate.unrealized_pnl,
            *(p.unrealized_pnl for s, p in self._positions.items() if s != symbol),
        ), "unrealized pnl")
        self._validate_pnl_totals(booked, unrealized)
        return candidate, fee, realized_pnl, released_cash, free_cash, equity

    def _validate_order_values(self, symbol, qty, price, leverage=None, mark_price=None):
        """供 Broker 在报价、订单和时钟副作用之前检查派生值。"""
        if qty != 0:
            self._preview_order(
                symbol, qty, price, self.leverage if leverage is None else leverage,
                price if mark_price is None else mark_price,
            )

    def submit_order(self, symbol: str, qty: float, price: float, leverage: Optional[float] = None, price_dt: Optional[DateType] = None, *, order_id: Optional[str] = None, mark_price: Optional[float] = None, mark_dt: Optional[DateType] = None) -> bool:
        """提交订单
        
        Args:
            symbol: 标的代码
            qty: 数量，可正可负
            price: 价格
            leverage: 杠杆倍数，如果为None，使用默认杠杆
            order_id: Broker 实际订单 ID，仅在成交成功后关联到盈亏记录
            mark_price: 当前市场估值价；省略时使用成交价，供独立 Portfolio 使用
            mark_dt: 市场报价时间，与 price_dt 成交时间分开保存
        
        依次进行:
            1. 按市场价估值并检查风险，成交价只用于交易结算
            2. 计算新开仓所需保证金和手续费，检查是否充足
            3. 提交订单，更新仓位和现金
        """
        symbol = normalize_symbol(symbol)
        qty = finite_number(qty, "qty")
        price = positive_number(price, "price")
        leverage = self.leverage if leverage is None else finite_number(leverage, "leverage")
        _require(leverage >= 1, f'leverage must be greater than or equal to 1, got {leverage}')
        if mark_price is None:
            mark_price, mark_dt = price, price_dt
        else:
            mark_price = positive_number(mark_price, "mark_price")
        if qty == 0:
            self.logger.warning(f'Submit order with qty=0, symbol: {symbol}, leverage: {leverage}, qty: {qty}, price: {price}')
            return False
        if self._bankrupt:
            self.logger.error('Portfolio bankrupt, cannot submit order')
            return False

        self._validate_order_values(symbol, qty, price, leverage, mark_price)
        
        # 更新价格并检查保证金（可能触发强平）
        bankrupt, liquidated, _ = self.on_new_price(symbol, mark_price, mark_dt, risk_dt=price_dt)
        if bankrupt or liquidated:
            return False

        # 检查保证金是否充足。新标的先使用临时仓位，避免失败订单污染 positions。
        position = self.get_position(symbol, create_if_missing=False)
        is_new_position = position is None
        if position is None:
            position = Position(symbol=symbol)
        candidate, required_fee, realized_pnl, released_cash, remaining_cash, equity = self._preview_order(
            symbol, qty, price, leverage, mark_price, mark_dt,
        )
        reduce_only = position.size != 0 and (position.size > 0) != (qty > 0) and abs(qty) <= abs(position.size)
        allow_debt = self.margin_mode == 'cross' and reduce_only and equity >= 0
        if (remaining_cash < 0 and not allow_debt) or (self.free_cash < 0 and not reduce_only):
            self.logger.error(
                f"Insufficient free cash to open position({symbol}, qty={qty}, price={price}). "
                f"Required free cash: {-released_cash}, Free cash: {self.free_cash}"
            )
            return False
        
        # 候选持仓和现金均已验证；保留 Position 身份，一次提交派生状态。
        self._current_cash._change_cash(released_cash, allow_negative=allow_debt)
        position.__dict__.update(candidate.__dict__)
        if is_new_position:
            self._positions[symbol] = position
        self.logger.info(f'Submit order: {symbol}, qty={qty}, price={price}, fee={required_fee}')
        self._record_pnl(
            symbol=symbol,
            qty=qty,
            price=price,
            realized_pnl=realized_pnl,
            fees=required_fee,
            order_id=order_id,
            dt=price_dt,
        )
        
        self.logger.debug(
            f'Submit order: {symbol}, qty={qty}, price={price}, new_position_size={position.size}, '
            f'released_cash={released_cash}, realized_pnl={realized_pnl}'
        )
        # 成交后的浮亏与手续费可能立即触发风险，必须在本批次内结算。
        self.on_new_price(symbol, mark_price, mark_dt, risk_dt=price_dt)
        return True

    def _preview_close_orders(self, orders):
        """全平计划汇总所有现金与费用，组内不触发单笔风险或现金约束。"""
        plan = []
        candidates = {}
        booked = list(self._booked_pnl.values())
        for order in orders:
            symbol = order["symbol"]
            if symbol in candidates:
                raise ValueError(f"duplicate symbol in close plan: {symbol}")
            qty = -self.get_position_size(symbol)
            if qty == 0:
                continue
            candidate, fee, pnl, released_cash, _, _ = self._preview_order(
                symbol, qty, order["price"], self.leverage,
                order.get("mark_price") or order["price"], order.get("mark_dt"),
            )
            candidates[symbol] = candidate
            plan.append({
                **order, "qty": qty, "candidate": candidate,
                "fee": fee, "realized_pnl": pnl, "released_cash": released_cash,
            })
            booked.append(Pnl(realized_pnl=pnl, fees=fee))
        released_cash = _finite_sum((row["released_cash"] for row in plan), "close plan cash")
        _, total_cash = self._current_cash._preview_change_cash(released_cash)
        remaining = [candidates.get(symbol, position) for symbol, position in self._positions.items()]
        _finite_sum((total_cash, *(p.equity for p in remaining)), "portfolio equity")
        self._validate_pnl_totals(booked, _finite_sum((p.unrealized_pnl for p in remaining), "unrealized pnl"))
        return plan, released_cash

    def _commit_close_orders(self, plan, released_cash):
        """提交已验证的整组全平，持仓、现金和账本使用同一份候选金额。"""
        self._current_cash.change_cash(released_cash)
        for row in plan:
            self._positions[row["symbol"]].__dict__.update(row["candidate"].__dict__)
        for row in plan:
            self._record_pnl(
                symbol=row["symbol"], qty=row["qty"], price=row["price"],
                realized_pnl=row["realized_pnl"], fees=row["fee"],
                order_id=row.get("order_id"), dt=row.get("price_dt"),
            )

    def can_submit_orders(self, orders, *, close_positions: bool = False) -> Tuple[bool, Optional[int]]:
        """普通订单按顺序模拟，全平计划按最终现金一次预检。"""
        if close_positions:
            _, released_cash = self._preview_close_orders(orders)
            accepted = self._current_cash.can_change_cash(released_cash)
            return accepted, None if accepted else 0
        preview = copy.copy(self)
        preview.last_prices = self.last_prices.copy()
        preview.last_prices_dt = self.last_prices_dt.copy()
        preview._current_cash = copy.deepcopy(self._current_cash)
        preview._positions = copy.deepcopy(self._positions)
        preview._booked_pnl = self._booked_pnl.copy()
        # 预检只模拟新增记账，不复制历史日志，也不通知真实 Broker。
        preview._pnl_records = []
        preview._pnl_record_sink = None
        preview.logger = _PreviewLogger()

        for index, order in enumerate(orders):
            qty = order["qty"]
            if not preview.submit_order(
                order["symbol"],
                qty,
                price=order["price"],
                leverage=order.get("leverage"),
                price_dt=order.get("price_dt"),
                mark_price=order.get("mark_price"),
                mark_dt=order.get("mark_dt"),
            ):
                return False, index
        return True, None
    
    def close_position(self, symbol: str, last_price: Optional[float] = None) -> bool:
        """平仓: 提交与当前持仓方向相反、数量相同的订单"""
        symbol = normalize_symbol(symbol)
        if last_price is not None:
            last_price = positive_number(last_price, "last_price")
        position = self.get_position(symbol, create_if_missing=False)
        if position is None or position.is_empty():
            self.logger.warning(f'Cannot close empty position: {symbol}')
            return False
        quote_dt = None
        if last_price is None:
            last_price = self.last_prices.get(symbol, position.last_price)
            quote_dt = self.last_prices_dt.get(symbol)
        if last_price is None:
            self.logger.error(f'Cannot close position {symbol}: no price available')
            return False
        self.on_new_price(symbol, last_price, quote_dt)
        position = self.get_position(symbol)
        if position is None or position.is_empty():
            return False
        return self.submit_order(symbol, -position.size, price=last_price, price_dt=quote_dt)
    
    def close_all_positions(self, last_prices: Optional[Dict[str, float]] = None) -> None:
        for symbol in list(self._positions.keys()):
            position = self._positions.get(symbol)
            if position is None or position.is_empty():
                continue
            if last_prices is None:
                self.close_position(symbol)
            else:
                self.close_position(symbol, last_prices.get(symbol))
        _require(np.allclose(self.get_all_positions_total_equity(), 0), 'All positions are not closed', RuntimeError)
        _require(
            np.allclose(self.get_portfolio_equity(), self.total_cash),
            'Portfolio equity is not equal to total cash',
            RuntimeError,
        )

    def _pure_close_position(self, symbol: str, last_price: Optional[float] = None, *, dt: Optional[DateType] = None) -> Optional[Position]:
        if symbol not in self._positions:
            return None
        position = self._positions[symbol]
        if position.is_empty():
            return position
        qty = -position.size
        # 先在副本上预检现金，失败时不清空实际持仓。
        preview = copy.deepcopy(position)
        released_margin, realized_pnl = preview.commit_close_all(last_price)
        released_cash = released_margin + realized_pnl
        _require(
            self._current_cash.can_change_cash(released_cash),
            f'Cannot close position {symbol}: released cash would make free cash negative',
            RuntimeError,
        )
        position.commit_close_all(preview.last_price)
        self._current_cash.change_cash(released_cash)
        self._record_pnl(
            symbol=symbol,
            qty=qty,
            price=position.last_price,
            realized_pnl=realized_pnl,
            reason="liquidation",
            dt=dt if dt is not None else self.last_prices_dt.get(symbol),
        )
        return position
    
    def _pure_close_all_positions(self, last_prices: Optional[Dict[str, float]] = None, *, dt: Optional[DateType] = None) -> None:
        """全仓强平按账户一次结算，允许单个持仓释放负现金。"""
        plan = []
        for symbol, position in self._positions.items():
            if position.is_empty():
                continue
            preview = copy.deepcopy(position)
            price = None if last_prices is None else last_prices.get(symbol)
            released_margin, realized_pnl = preview.commit_close_all(price)
            plan.append((symbol, -position.size, preview.last_price, released_margin, realized_pnl))
        released_cash = fsum(margin + pnl for _, _, _, margin, pnl in plan)
        _require(
            self._current_cash.can_change_cash(released_cash),
            "Cannot close all positions: released cash would make free cash negative",
            RuntimeError,
        )
        for symbol, _, price, _, _ in plan:
            self._positions[symbol].commit_close_all(price)
        self._current_cash.change_cash(released_cash)
        for symbol, qty, price, _, realized_pnl in plan:
            self._record_pnl(
                symbol=symbol, qty=qty, price=price, realized_pnl=realized_pnl,
                reason="liquidation", dt=dt if dt is not None else self.last_prices_dt.get(symbol),
            )
    
    def get_position(self, symbol: str, create_if_missing: bool = False) -> Optional[Position]:
        """查询持仓；默认只读查询，需要初始化空仓时显式传 ``create_if_missing=True``。"""
        symbol = normalize_symbol(symbol)
        if symbol not in self._positions:
            if not create_if_missing:
                return None
            self._positions[symbol] = Position(symbol=symbol)
        return self._positions[symbol]
    
    def get_position_size(self, symbol: str) -> float:
        position = self.get_position(symbol, create_if_missing=False)
        if position is None:
            return 0
        return position.size
    
    def get_positions(self) -> Dict[str, Position]:
        """返回 symbol 到 Position 的浅快照，修改字典不会改动 Portfolio 索引。"""
        return self._positions.copy()
    
    def get_position_sizes(self) -> Dict[str, float]:
        return {symbol: pos.size for symbol, pos in self._positions.items() if not pos.is_empty()}
    
    def get_total_cash(self) -> float:
        return self._current_cash.total_cash
    
    def get_cash(self, include_locked: bool = False) -> float:
        if include_locked:
            return self.total_cash
        else:
            return self.free_cash
    
    def get_free_cash(self) -> float:
        return self._current_cash.free_cash
    
    def get_locked_cash(self) -> float:
        return self._current_cash.locked_cash
    
    def get_equity(self) -> float:
        return self.get_portfolio_equity()
    
    def get_position_equity(self, symbol: str) -> float:
        position = self.get_position(symbol, create_if_missing=False)
        if position is None:
            return 0
        return position.equity
    
    def calculate_fee(self, symbol: str, leverage: float, qty: float, price: float) -> float:
        """计算手续费"""
        return abs(qty) * price * self.fee_rate
    
    @property
    def cash(self) -> float:
        return self._current_cash.total_cash
    
    @property
    def free_cash(self) -> float:
        return self._current_cash.free_cash
    
    @property
    def locked_cash(self) -> float:
        return self._current_cash.locked_cash
    
    @property
    def total_cash(self) -> float:
        return self._current_cash.total_cash
    
    @property
    def positions(self) -> Dict[str, Position]:
        return self._positions.copy()

    @property
    def bankrupt(self) -> bool:
        return self._bankrupt
