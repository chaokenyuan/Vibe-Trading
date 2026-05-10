"""ManualCliAdapter：開發測試與緊急人工補單用。

對應 spec：「ManualCliAdapter 直接接受 Signal 物件」。
不啟動長期 process；CLI 工具是外部 wrapper（scripts/submit_signal.py）。
"""

from __future__ import annotations

from signals.router import SignalRouter
from signals.types import Signal, SignalSourceKind


class ManualCliAdapter:
    """直接接受 Signal 物件並推進 router 的 adapter。

    使用情境：
    - 開發測試：構造 Signal 物件直接 submit，繞過 webhook 認證
    - 緊急補單：webhook 失效時人工從歷史資料重建並補送

    結構性符合 SignalSource Protocol。
    """

    def __init__(self, *, router: SignalRouter) -> None:
        self._router = router

    async def start(self) -> None:
        """no-op；無長期 task。"""

    async def stop(self) -> None:
        """no-op。"""

    async def submit(self, signal: Signal) -> None:
        """直接餵 Signal 給 router。source 必須為 manual。"""
        if signal.source != SignalSourceKind.MANUAL:
            raise ValueError(
                f"ManualCliAdapter 只接受 source=manual，實際 source={signal.source}"
            )

        await self._router.ingest(
            strategy_id=signal.strategy_id,
            symbol=signal.symbol,
            side=signal.side,
            qty=signal.qty,
            price=signal.price,
            bar_time=signal.bar_time,
            interval=signal.interval,
            source=signal.source,
            comment=signal.comment,
            raw_payload=signal.raw_payload,
        )
