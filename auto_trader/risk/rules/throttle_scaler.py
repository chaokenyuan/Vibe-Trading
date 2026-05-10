"""ThrottleScaler：預設 no-op；保留供未來動態 scaler 擴展。

與 SystemStateRule 互補：SystemStateRule 已在 THROTTLED 時縮量 50%，
本規則預設不再額外縮放（避免複合縮量造成過度保守）。
配置 `scaler` < 1.0 時主動 CLAMP（操作員明確選擇額外縮量）。
"""

from __future__ import annotations

from decimal import Decimal

from risk.decision import Outcome, RuleVerdict
from risk.rules.base import RuleContext


class ThrottleScaler:
    name = "ThrottleScaler"

    def __init__(self, *, scaler: Decimal = Decimal("1.0")) -> None:
        self._scaler = scaler

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        if self._scaler >= Decimal("1.0"):
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message="scaler=1.0 (no-op)",
            )
        scaled = ctx.current_size * self._scaler
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.CLAMP,
            before_value=ctx.current_size,
            after_value=scaled,
            message=f"scaled by {self._scaler}",
            metadata={"scaler": str(self._scaler)},
        )
