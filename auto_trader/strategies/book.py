"""LogicalBook：每策略持倉視角 + realized PnL 累積。

由 Reconciliation capability 在收到 Fill 時呼叫 apply_fill 更新；
StrategyHost 與 Strategy 視為 read-only。
"""

from __future__ import annotations

from decimal import Decimal

from risk.types import Side
from strategies.types import Fill, LogicalPosition


class LogicalBook:
    """單策略內部帳本（含 realized PnL）。"""

    def __init__(self, strategy_id: str) -> None:
        self._strategy_id = strategy_id
        self._positions: dict[str, LogicalPosition] = {}
        self._realized_pnl: Decimal = Decimal("0")
        self._fees_paid: Decimal = Decimal("0")

    @property
    def strategy_id(self) -> str:
        return self._strategy_id

    @property
    def realized_pnl(self) -> Decimal:
        """累積已實現損益（含手續費）。"""
        return self._realized_pnl - self._fees_paid

    @property
    def realized_pnl_gross(self) -> Decimal:
        """毛利（不扣手續費）。"""
        return self._realized_pnl

    @property
    def fees_paid(self) -> Decimal:
        return self._fees_paid

    def get_position(self, symbol: str) -> LogicalPosition | None:
        return self._positions.get(symbol)

    def list_positions(self) -> list[LogicalPosition]:
        return list(self._positions.values())

    def apply_fill(self, fill: Fill, *, signal_id: str = "") -> None:
        """套用 fill：依 side/qty 增減持倉，更新加權平均成本與 realized PnL。

        signal_id 為建倉首筆訊號 ID；既有部位平倉再開倉時將更新此值。
        """
        # 累積手續費（不論 open / close 都收）
        self._fees_paid += fill.fees

        existing = self._positions.get(fill.symbol)
        delta_qty = fill.qty if fill.side == Side.BUY else -fill.qty

        if existing is None:
            # 全新部位
            self._positions[fill.symbol] = LogicalPosition(
                strategy_id=self._strategy_id,
                symbol=fill.symbol,
                qty=delta_qty,
                avg_entry=fill.price,
                opened_at=fill.at,
                open_signal_id=signal_id,
            )
            return

        # 計算 realized PnL（若這筆 fill 是「反向」對既有部位）
        is_reduction = (existing.qty > 0 and delta_qty < 0) or (
            existing.qty < 0 and delta_qty > 0
        )
        if is_reduction:
            close_qty = min(abs(delta_qty), abs(existing.qty))
            if existing.qty > 0:
                # long close: 賺 (close_price - entry) * qty
                realized = (fill.price - existing.avg_entry) * close_qty
            else:
                # short close: 賺 (entry - close_price) * qty
                realized = (existing.avg_entry - fill.price) * close_qty
            self._realized_pnl += realized

        new_qty = existing.qty + delta_qty

        # 平倉
        if new_qty == 0:
            del self._positions[fill.symbol]
            return

        # 同方向加倉：加權平均
        same_direction = (existing.qty > 0 and delta_qty > 0) or (
            existing.qty < 0 and delta_qty < 0
        )
        if same_direction:
            new_avg = (
                existing.qty * existing.avg_entry + delta_qty * fill.price
            ) / new_qty
            self._positions[fill.symbol] = LogicalPosition(
                strategy_id=existing.strategy_id,
                symbol=existing.symbol,
                qty=new_qty,
                avg_entry=new_avg,
                opened_at=existing.opened_at,
                open_signal_id=existing.open_signal_id,
            )
            return

        # 反向但未歸零：部位仍以原方向、qty 減少；avg_entry 保留
        # （已在上方計算 realized PnL）
        # 反向超過原部位（翻倉）：avg_entry 改為新方向的價格
        if (existing.qty > 0 and new_qty < 0) or (existing.qty < 0 and new_qty > 0):
            # 翻倉
            self._positions[fill.symbol] = LogicalPosition(
                strategy_id=existing.strategy_id,
                symbol=existing.symbol,
                qty=new_qty,
                avg_entry=fill.price,
                opened_at=fill.at,
                open_signal_id=signal_id,
            )
            return

        self._positions[fill.symbol] = LogicalPosition(
            strategy_id=existing.strategy_id,
            symbol=existing.symbol,
            qty=new_qty,
            avg_entry=existing.avg_entry,
            opened_at=existing.opened_at,
            open_signal_id=existing.open_signal_id,
        )

    def total_position_count(self) -> int:
        return len(self._positions)
