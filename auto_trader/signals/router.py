"""SignalRouter：訊號入口層的核心編排器。

對應 spec：「SignalRouter 集中處理去重與下游分發」、
       「SignalRouter 啟停為 async lifecycle」。

職責：
1. 接收 source 餵進的 raw payload
2. 從 StrategyRegistry 補齊 strategy_version / params_hash
3. 計算 signal_id（sha256 of strategy_id|symbol|side|bar_time|interval）
4. 查 SignalDedupe；命中即拒
5. fan-out 給所有 SignalConsumer，故障隔離
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from risk.ports import Clock
from signals.dedupe import SignalDedupe
from signals.ports import SignalConsumer, SignalSource, StrategyRegistryProtocol
from signals.types import SCHEMA_VERSION_CURRENT, Signal, SignalSourceKind

logger = logging.getLogger(__name__)


class SignalRouter:
    """訊號分發與去重編排器。

    使用方式：
        router = SignalRouter(clock=..., registry=..., dedupe=...)
        router.subscribe(strategy_host)
        router.attach_source(tradingview_adapter)
        await router.start()
        ...
        await router.stop()
    """

    def __init__(
        self,
        *,
        clock: Clock,
        registry: StrategyRegistryProtocol,
        dedupe: SignalDedupe,
    ) -> None:
        self._clock = clock
        self._registry = registry
        self._dedupe = dedupe
        self._consumers: list[SignalConsumer] = []
        self._sources: list[SignalSource] = []
        self._started = False

    def subscribe(self, consumer: SignalConsumer) -> None:
        """註冊下游 consumer；多 consumer 採 fan-out。"""
        self._consumers.append(consumer)

    def attach_source(self, source: SignalSource) -> None:
        """註冊訊號來源；start() 時統一啟動。"""
        self._sources.append(source)

    async def start(self) -> None:
        """啟動所有註冊的 source。"""
        if self._started:
            raise RuntimeError("SignalRouter already started")
        for source in self._sources:
            await source.start()
        self._started = True

    async def stop(self) -> None:
        """優雅停機；冪等。"""
        if not self._started:
            return
        for source in self._sources:
            await source.stop()
        self._started = False

    async def ingest(
        self,
        *,
        strategy_id: str,
        symbol: str,
        side: Literal["BUY", "SELL", "CLOSE"],
        qty: Decimal,
        price: Decimal | None,
        bar_time: datetime,
        interval: str,
        source: SignalSourceKind,
        comment: str | None,
        raw_payload: dict[str, Any],
    ) -> Signal | None:
        """主入口：把 raw 訊號轉為 canonical Signal 並分發。

        Returns:
            Signal: 成功分發的 Signal 物件
            None: 被拒（未知 strategy_id 或 dedupe 命中）
        """
        # 1. 補齊 metadata
        metadata = self._registry.get_strategy_metadata(strategy_id)
        if metadata is None:
            logger.warning("unknown strategy_id rejected: %s", strategy_id)
            return None

        # 2. 計算 signal_id
        signal_id = self._compute_signal_id(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            bar_time=bar_time,
            interval=interval,
        )

        # 3. dedupe
        if self._dedupe.is_duplicate(signal_id):
            logger.info("duplicate signal_id rejected: %s", signal_id)
            return None

        # 4. 建構 Signal
        signal = Signal(
            schema_version=SCHEMA_VERSION_CURRENT,
            signal_id=signal_id,
            strategy_id=strategy_id,
            strategy_version=metadata.strategy_version,
            params_hash=metadata.params_hash,
            symbol=symbol,
            side=side,
            qty=qty,
            price=price,
            bar_time=bar_time,
            interval=interval,
            received_at=self._clock.now(),
            source=source,
            comment=comment,
            raw_payload=raw_payload,
        )

        # 5. fan-out（故障隔離）
        for consumer in self._consumers:
            try:
                await consumer.on_signal(signal)
            except Exception:
                logger.exception(
                    "consumer failed: consumer=%r signal_id=%s",
                    consumer,
                    signal_id,
                )

        return signal

    @staticmethod
    def _compute_signal_id(
        *,
        strategy_id: str,
        symbol: str,
        side: str,
        bar_time: datetime,
        interval: str,
    ) -> str:
        material = f"{strategy_id}|{symbol}|{side}|{bar_time.isoformat()}|{interval}"
        return hashlib.sha256(material.encode("utf-8")).hexdigest()
