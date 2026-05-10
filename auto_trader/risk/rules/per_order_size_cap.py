"""PerOrderSizeCap：限制單筆訂單佔總權益比例。"""

from __future__ import annotations

import logging
from decimal import Decimal

from risk.decision import Outcome, RuleVerdict
from risk.ports import EquityReader
from risk.rules.base import RuleContext

logger = logging.getLogger(__name__)


class PerOrderSizeCap:
    """qty 上限 = (max_pct_of_equity × equity) / price。"""

    name = "PerOrderSizeCap"

    def __init__(
        self,
        *,
        equity_reader: EquityReader,
        max_pct_of_equity: Decimal = Decimal("0.05"),
    ) -> None:
        self._equity_reader = equity_reader
        self._max_pct = max_pct_of_equity

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        price = ctx.intent.price
        if price is None:
            price = ctx.market_data.get_last_price(ctx.intent.symbol)

        if price <= 0:
            logger.warning(
                "non-positive price for %s: %s; clamping to 0",
                ctx.intent.symbol,
                price,
            )
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.CLAMP,
                before_value=ctx.current_size,
                after_value=Decimal("0"),
                message=f"non-positive price={price}",
            )

        equity = self._equity_reader.total_equity
        notional_cap = equity * self._max_pct
        qty_cap = notional_cap / price

        if ctx.current_size > qty_cap:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.CLAMP,
                before_value=ctx.current_size,
                after_value=qty_cap,
                message=(
                    f"size capped: max_pct={self._max_pct}, equity={equity}, "
                    f"price={price}, qty_cap={qty_cap}"
                ),
                metadata={
                    "max_pct_of_equity": str(self._max_pct),
                    "equity": str(equity),
                },
            )
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message=f"size {ctx.current_size} within cap {qty_cap}",
        )
