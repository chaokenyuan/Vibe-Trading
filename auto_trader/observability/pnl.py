"""PnLCalculator：統一計算每策略 / 每持倉 PnL（unrealized + realized）。

read-only：從 LogicalBook 與 MarketDataReader 派生，不持狀態。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from risk.ports import MarketDataReader
from strategies.registry import StrategyRegistry


@dataclass(frozen=True, kw_only=True)
class PositionPnL:
    """單一持倉的 PnL 快照。"""

    strategy_id: str
    symbol: str
    qty: Decimal
    avg_entry: Decimal
    last_price: Decimal
    unrealized_pnl: Decimal
    notional: Decimal


@dataclass(frozen=True, kw_only=True)
class StrategyPnL:
    """單策略 PnL 快照。"""

    strategy_id: str
    realized_pnl: Decimal
    fees_paid: Decimal
    unrealized_pnl: Decimal
    total_pnl: Decimal
    positions: list[PositionPnL]


@dataclass(frozen=True, kw_only=True)
class AccountPnL:
    """全帳戶 PnL 快照（多策略加總）。"""

    total_realized: Decimal
    total_unrealized: Decimal
    total_fees: Decimal
    total_pnl: Decimal
    strategies: list[StrategyPnL]


class PnLCalculator:
    """從 StrategyRegistry + MarketDataReader 計算所有 PnL。"""

    def __init__(
        self,
        *,
        registry: StrategyRegistry,
        market_data: MarketDataReader,
    ) -> None:
        self._registry = registry
        self._market_data = market_data

    def position_pnl(
        self, strategy_id: str, symbol: str
    ) -> PositionPnL | None:
        book = self._registry.get_book(strategy_id)
        if book is None:
            return None
        position = book.get_position(symbol)
        if position is None:
            return None
        last = self._market_data.get_last_price(symbol)
        # long: (last - entry) * qty   |   short: (entry - last) * |qty|
        if position.qty >= 0:
            unrealized = (last - position.avg_entry) * position.qty
        else:
            unrealized = (position.avg_entry - last) * (-position.qty)
        notional = abs(position.qty) * last
        return PositionPnL(
            strategy_id=strategy_id,
            symbol=symbol,
            qty=position.qty,
            avg_entry=position.avg_entry,
            last_price=last,
            unrealized_pnl=unrealized,
            notional=notional,
        )

    def strategy_pnl(self, strategy_id: str) -> StrategyPnL | None:
        book = self._registry.get_book(strategy_id)
        if book is None:
            return None
        positions: list[PositionPnL] = []
        unrealized_total = Decimal("0")
        for pos in book.list_positions():
            p_pnl = self.position_pnl(strategy_id, pos.symbol)
            if p_pnl is None:
                continue
            positions.append(p_pnl)
            unrealized_total += p_pnl.unrealized_pnl
        realized = book.realized_pnl
        fees = book.fees_paid
        return StrategyPnL(
            strategy_id=strategy_id,
            realized_pnl=realized,
            fees_paid=fees,
            unrealized_pnl=unrealized_total,
            total_pnl=realized + unrealized_total,
            positions=positions,
        )

    def account_pnl(self) -> AccountPnL:
        per_strategy: list[StrategyPnL] = []
        total_realized = Decimal("0")
        total_unrealized = Decimal("0")
        total_fees = Decimal("0")
        for sid in self._registry.list_strategies():
            sp = self.strategy_pnl(sid)
            if sp is None:
                continue
            per_strategy.append(sp)
            total_realized += sp.realized_pnl
            total_unrealized += sp.unrealized_pnl
            total_fees += sp.fees_paid
        return AccountPnL(
            total_realized=total_realized,
            total_unrealized=total_unrealized,
            total_fees=total_fees,
            total_pnl=total_realized + total_unrealized,
            strategies=per_strategy,
        )
