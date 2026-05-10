"""CapitalReservationRule：呼叫 reserver.reserve 取得 reservation_id。

對應 spec：「CapitalReservationRule 預留資金並注入 reservation_id」。
本規則必須位於規則順序最末位；engine 在組 Decision 時抽其 metadata.reservation_id。
"""

from __future__ import annotations

from risk.decision import Outcome, RuleVerdict
from risk.reservation.reserver import CapitalReserver
from risk.rules.base import RuleContext


class CapitalReservationRule:
    name = "CapitalReservationRule"

    def __init__(self, *, reserver: CapitalReserver) -> None:
        self._reserver = reserver

    async def evaluate_async(self, ctx: RuleContext) -> RuleVerdict:
        """async 版本：因 reserver.reserve 為 async。"""
        price = ctx.intent.price or ctx.market_data.get_last_price(ctx.intent.symbol)
        notional = ctx.current_size * price

        result = await self._reserver.reserve(intent=ctx.intent, notional=notional)

        if not result.ok:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.REJECT,
                before_value=ctx.current_size,
                after_value=None,
                message=f"reservation failed: {result.reason}",
                metadata={
                    "reason": result.reason or "",
                    "available": str(result.available) if result.available else "",
                },
            )

        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message=f"reserved {notional}",
            metadata={
                "reservation_id": str(result.reservation_id),
                "notional": str(notional),
            },
        )

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        """同步版本：本規則必須以 async 呼叫；提供 evaluate 拋例外避免誤用。"""
        raise RuntimeError(
            "CapitalReservationRule.evaluate must be called via evaluate_async; "
            "ensure RuleEngine dispatches async rules accordingly."
        )


def is_async_rule(rule: object) -> bool:
    """簡易判斷：規則是否須以 async 呼叫（透過 evaluate_async 屬性偵測）。"""
    return hasattr(rule, "evaluate_async") and callable(rule.evaluate_async)
