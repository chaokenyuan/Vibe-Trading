"""StrategyPausedRule：拒絕非 ACTIVE 策略訊號。"""

from __future__ import annotations

from risk.decision import Outcome, RuleVerdict
from risk.ports import StrategyStateReader
from risk.rules.base import RuleContext

ACTIVE_STATE = "ACTIVE"


class StrategyPausedRule:
    """讀取 strategy 狀態；非 ACTIVE 即 REJECT。

    與 StrategyHost 內部過濾互補（防禦性）：即使 host 路由錯誤，
    風控閘仍能擋下非 ACTIVE 策略訊號。
    """

    name = "StrategyPausedRule"

    def __init__(self, *, state_reader: StrategyStateReader) -> None:
        self._reader = state_reader

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        state = self._reader.get_state(ctx.intent.strategy_id)
        if state == ACTIVE_STATE:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message=f"strategy state={state}",
                metadata={"strategy_state": state},
            )
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.REJECT,
            before_value=ctx.current_size,
            after_value=None,
            message=f"strategy state={state} not ACTIVE",
            metadata={"strategy_state": state or "UNKNOWN"},
        )
