"""RuleEngine：Layer 2 規則引擎編排器。

對應 spec：
- 「規則引擎採短路評估」（reject 短路 + clamp 累積）
- 「Decision 與 RuleVerdict 為不可變值物件」
- 「所有風控決策與狀態變更須發布事件供審計」（DecisionEmitted）
"""

from __future__ import annotations

import logging
import os
from decimal import Decimal
from uuid import UUID

from risk.decision import Decision, Outcome, RuleVerdict, Verdict
from risk.events import DecisionEmitted
from risk.ports import (
    Clock,
    ConfigReader,
    EventPublisher,
    MarketDataReader,
    PositionReader,
)
from risk.rules.base import RiskRule, RuleContext
from risk.types import OrderIntent

logger = logging.getLogger(__name__)


class RuleEngine:
    """規則引擎。

    建構時注入規則清單（順序即執行順序）+ ports；對外主介面 async evaluate(intent)。
    Debug 模式下，clamp 規則違反「after_value 必須單調遞減」會拋例外；
    Production 模式下，記錄錯誤並忽略該規則的修正值。

    Debug 模式由環境變數 RISK_GATE_DEBUG 開啟（"1" / "true"）。
    """

    def __init__(
        self,
        *,
        rules: list[RiskRule],
        publisher: EventPublisher,
        clock: Clock,
        positions: PositionReader,
        market_data: MarketDataReader,
        config: ConfigReader,
        debug_mode: bool | None = None,
    ) -> None:
        self._rules = list(rules)  # defensive copy
        self._publisher = publisher
        self._clock = clock
        self._positions = positions
        self._market_data = market_data
        self._config = config
        if debug_mode is None:
            self._debug = os.environ.get("RISK_GATE_DEBUG", "").lower() in ("1", "true")
        else:
            self._debug = debug_mode

    async def evaluate(self, intent: OrderIntent) -> Decision:
        """對單筆 OrderIntent 執行完整評估流程。

        流程：
        1. 依 self._rules 順序逐條呼叫 evaluate(ctx)
        2. 收集 RuleVerdict 至 reasons
        3. 任一 REJECT 短路（回傳 verdict=REJECT 的 Decision）
        4. CLAMP 累積套用：current_size 取 min(current_size, after_value)
        5. 全部通過 → Decision(verdict=APPROVE, final_size=current_size)
        6. 發布 DecisionEmitted 事件
        """
        current_size = intent.qty
        current_price = intent.price
        reasons: list[RuleVerdict] = []

        for rule in self._rules:
            ctx = RuleContext(
                intent=intent,
                current_size=current_size,
                current_price=current_price,
                positions=self._positions,
                market_data=self._market_data,
                config=self._config,
                clock=self._clock,
            )
            # 支援 async-only 規則（如 CapitalReservationRule）：偵測 evaluate_async
            if hasattr(rule, "evaluate_async") and callable(rule.evaluate_async):
                verdict = await rule.evaluate_async(ctx)
            else:
                verdict = rule.evaluate(ctx)
            reasons.append(verdict)

            if verdict.outcome == Outcome.REJECT:
                decision = Decision(
                    verdict=Verdict.REJECT,
                    final_size=Decimal(0),
                    final_price=None,
                    reasons=reasons,
                    reservation_id=None,
                    evaluated_at=self._clock.now(),
                )
                await self._publisher.publish(
                    DecisionEmitted(at=self._clock.now(), decision=decision)
                )
                return decision

            if verdict.outcome == Outcome.CLAMP:
                current_size = self._apply_clamp(verdict, current_size, rule.name)

        # 從最後一條 RuleVerdict.metadata 抽 reservation_id（CapitalReservationRule 注入）
        reservation_id = self._extract_reservation_id(reasons)

        decision = Decision(
            verdict=Verdict.APPROVE,
            final_size=current_size,
            final_price=current_price,
            reasons=reasons,
            reservation_id=reservation_id,
            evaluated_at=self._clock.now(),
        )
        await self._publisher.publish(
            DecisionEmitted(at=self._clock.now(), decision=decision)
        )
        return decision

    @staticmethod
    def _extract_reservation_id(reasons: list[RuleVerdict]) -> UUID | None:
        """從規則判決鏈中抽 reservation_id（最後一條規則的 metadata）。"""
        if not reasons:
            return None
        last = reasons[-1]
        rid = last.metadata.get("reservation_id")
        if not rid:
            return None
        if isinstance(rid, UUID):
            return rid
        try:
            return UUID(str(rid))
        except (ValueError, TypeError):
            logger.warning("invalid reservation_id in metadata: %r", rid)
            return None

    def _apply_clamp(
        self,
        verdict: RuleVerdict,
        current_size: Decimal,
        rule_name: str,
    ) -> Decimal:
        """執行 CLAMP 修正並驗證單調遞減 invariant。"""
        after = verdict.after_value
        if after is None:
            msg = f"clamp 規則 {rule_name} 必須提供 after_value"
            if self._debug:
                raise ValueError(msg)
            logger.error(msg)
            return current_size

        if after > current_size:
            msg = (
                f"clamp 規則 {rule_name} 違反單調遞減："
                f"current_size={current_size}, after_value={after}"
            )
            if self._debug:
                raise ValueError(msg)
            logger.error(msg)
            return current_size

        return after
