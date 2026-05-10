"""StrategyHost：SignalConsumer 串接 RiskGate 與 OrderSink。

對應 spec：「StrategyHost 為 SignalConsumer 串接 RiskGate 與 OrderSink」。
"""

from __future__ import annotations

import logging

from risk.decision import Verdict
from risk.gate import RiskGate
from signals.types import Signal
from strategies.ports import OrderSink
from strategies.registry import StrategyRegistry
from strategies.types import StrategyState

logger = logging.getLogger(__name__)


class StrategyHost:
    """策略主機編排器；同時為 SignalConsumer。"""

    def __init__(
        self,
        *,
        registry: StrategyRegistry,
        risk_gate: RiskGate,
        order_sink: OrderSink,
    ) -> None:
        self._registry = registry
        self._risk_gate = risk_gate
        self._order_sink = order_sink

    async def on_signal(self, signal: Signal) -> None:
        """SignalConsumer 主入口。"""
        strategy = self._registry.get_strategy(signal.strategy_id)
        if strategy is None:
            logger.warning(
                "strategy not registered: signal_id=%s strategy_id=%s",
                signal.signal_id,
                signal.strategy_id,
            )
            return

        state = self._registry.get_state(signal.strategy_id)
        if state != StrategyState.ACTIVE:
            logger.info(
                "strategy not ACTIVE, skip: state=%s strategy_id=%s",
                state,
                signal.strategy_id,
            )
            return

        # 呼叫 strategy.on_signal，故障即標 FAILED
        try:
            intents = await strategy.on_signal(signal)
        except Exception:
            logger.exception(
                "strategy crashed on_signal: strategy_id=%s signal_id=%s",
                signal.strategy_id,
                signal.signal_id,
            )
            self._registry.set_state(signal.strategy_id, StrategyState.FAILED)
            return

        # 對每個 OrderIntent 走風控閘 + submit
        for seq, intent in enumerate(intents, start=1):
            client_order_id = self._encode_client_order_id(
                strategy_id=signal.strategy_id,
                signal_id=signal.signal_id,
                seq=seq,
            )

            decision = await self._risk_gate.evaluate(intent)

            if decision.verdict != Verdict.APPROVE:
                logger.info(
                    "intent rejected by risk-gate: client_order_id=%s verdict=%s",
                    client_order_id,
                    decision.verdict.value,
                )
                continue

            try:
                broker_order_id = await self._order_sink.submit(
                    intent=intent,
                    decision=decision,
                    client_order_id=client_order_id,
                )
                logger.info(
                    "order submitted: client_order_id=%s broker_order_id=%s",
                    client_order_id,
                    broker_order_id,
                )
            except Exception:
                logger.exception(
                    "order_sink.submit failed: client_order_id=%s",
                    client_order_id,
                )

    @staticmethod
    def _encode_client_order_id(
        *,
        strategy_id: str,
        signal_id: str,
        seq: int,
    ) -> str:
        signal_id_short = signal_id[:12]
        return f"{strategy_id}.{signal_id_short}.{seq}"

    @staticmethod
    def decode_strategy_id(client_order_id: str) -> str:
        """從 client_order_id 解出 strategy_id（reconciliation 用）。"""
        return client_order_id.split(".", 1)[0]


# 提供 fan-out helper：StrategyHost 本身作為 SignalConsumer 使用時，這個是公開介面


__all__ = ["StrategyHost"]
