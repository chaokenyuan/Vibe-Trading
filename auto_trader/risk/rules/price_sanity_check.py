"""PriceSanityCheck：拒絕偏離 last 價過大的限價單。"""

from __future__ import annotations

from decimal import Decimal

from risk.decision import Outcome, RuleVerdict
from risk.rules.base import RuleContext


class PriceSanityCheck:
    """限價單偏離 last 超過 max_deviation_pct 即 REJECT。市價單一律 PASS。"""

    name = "PriceSanityCheck"

    def __init__(
        self,
        *,
        max_deviation_pct: Decimal = Decimal("0.05"),
    ) -> None:
        self._max_dev = max_deviation_pct

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        if ctx.intent.price is None:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message="market order (no price check)",
            )

        last = ctx.market_data.get_last_price(ctx.intent.symbol)
        if last <= 0:
            # 無法判斷 → 通過（謹慎放行；上層另有風險閘）
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message=f"last price unavailable (last={last})",
            )

        deviation = abs(ctx.intent.price - last) / last
        if deviation > self._max_dev:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.REJECT,
                before_value=ctx.current_size,
                after_value=None,
                message=(
                    f"price deviation {deviation:.4f} > max {self._max_dev}; "
                    f"price={ctx.intent.price}, last={last}"
                ),
                metadata={
                    "deviation": str(deviation),
                    "max_deviation_pct": str(self._max_dev),
                    "last": str(last),
                },
            )
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message=f"price deviation {deviation:.4f} within {self._max_dev}",
        )
