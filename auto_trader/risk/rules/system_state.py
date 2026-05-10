"""SystemStateRule：依 FSM 狀態決定門檻。

對應 spec scenario：
- NORMAL/WARNING → PASS
- THROTTLED → CLAMP，final_size 乘以 0.5
- HALTED/KILL_SWITCH/MAINTENANCE → REJECT

啟動時 SHALL 主動同步查詢 FSM 取得初始狀態（建構參數注入），
之後訂閱 EventPublisher 的 StateChanged 事件即時更新快取。
"""

from __future__ import annotations

from decimal import Decimal

from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.decision import Outcome, RuleVerdict
from risk.events import StateChanged
from risk.rules.base import RuleContext


class SystemStateRule:
    """FSM 狀態驅動的訂單閘門。"""

    name = "SystemStateRule"

    # 拒絕進入交易的狀態
    REJECT_STATES = frozenset({"HALTED", "KILL_SWITCH", "MAINTENANCE"})
    # 縮量交易的狀態
    THROTTLED_STATE = "THROTTLED"

    def __init__(
        self,
        *,
        initial_state: str,
        publisher: InMemoryEventPublisher,
        throttled_size_scaler: Decimal = Decimal("0.5"),
    ) -> None:
        self._state = initial_state
        self._scaler = throttled_size_scaler
        publisher.subscribe(StateChanged, self._on_state_changed)

    async def _on_state_changed(self, event: StateChanged) -> None:
        self._state = event.to_state

    @property
    def current_state(self) -> str:
        return self._state

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        if self._state in self.REJECT_STATES:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.REJECT,
                before_value=ctx.current_size,
                after_value=None,
                message=f"system_state={self._state}",
                metadata={"system_state": self._state},
            )

        if self._state == self.THROTTLED_STATE:
            after = ctx.current_size * self._scaler
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.CLAMP,
                before_value=ctx.current_size,
                after_value=after,
                message=f"system_state=THROTTLED scaler={self._scaler}",
                metadata={"system_state": self._state, "scaler": str(self._scaler)},
            )

        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message=f"system_state={self._state}",
            metadata={"system_state": self._state},
        )
