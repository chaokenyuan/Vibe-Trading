"""SignalFreshnessRule：拒絕過舊訊號。"""

from __future__ import annotations

from risk.decision import Outcome, RuleVerdict
from risk.rules.base import RuleContext


class SignalFreshnessRule:
    """訊號年齡 > max_age_seconds 即 REJECT。"""

    name = "SignalFreshnessRule"

    def __init__(self, *, max_age_seconds: int = 30) -> None:
        self._max_age_seconds = max_age_seconds

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        age_seconds = (ctx.clock.now() - ctx.intent.bar_time).total_seconds()
        if age_seconds > self._max_age_seconds:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.REJECT,
                before_value=ctx.current_size,
                after_value=None,
                message=(
                    f"signal age {age_seconds:.0f}s > threshold "
                    f"{self._max_age_seconds}s"
                ),
                metadata={
                    "age_seconds": age_seconds,
                    "max_age_seconds": self._max_age_seconds,
                },
            )
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message=f"signal age {age_seconds:.0f}s within threshold",
            metadata={"age_seconds": age_seconds},
        )
