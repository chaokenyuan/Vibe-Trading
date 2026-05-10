"""SymbolConcentrationCap：依標的集中度可用額 clamp。"""

from __future__ import annotations

import logging
from decimal import Decimal

from risk.decision import Outcome, RuleVerdict
from risk.ports import ReservationLedgerReader
from risk.rules.base import RuleContext

logger = logging.getLogger(__name__)


class SymbolConcentrationCap:
    """qty 上限 = ledger.symbol_available / price。"""

    name = "SymbolConcentrationCap"

    def __init__(self, *, ledger_reader: ReservationLedgerReader) -> None:
        self._ledger = ledger_reader

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        price = ctx.intent.price or ctx.market_data.get_last_price(ctx.intent.symbol)
        if price <= 0:
            logger.warning("non-positive price: %s", price)
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.CLAMP,
                before_value=ctx.current_size,
                after_value=Decimal("0"),
                message=f"non-positive price={price}",
            )

        available = self._ledger.symbol_available(ctx.intent.symbol)
        if available == Decimal("Infinity"):
            # 未列入 caps 的 symbol 視為無限額；不 clamp
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message="symbol unbounded (not in caps)",
            )

        qty_cap = available / price
        if ctx.current_size > qty_cap:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.CLAMP,
                before_value=ctx.current_size,
                after_value=qty_cap,
                message=f"symbol_available={available}, qty_cap={qty_cap}",
                metadata={"symbol_available": str(available)},
            )
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message=f"size within symbol concentration (avail={available})",
        )
