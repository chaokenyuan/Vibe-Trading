"""CapitalReserver：單一 actor 序列化處理資金預留請求。

對應 spec：「CapitalReserver 為單一 actor 序列化處理預留」、
       「FCFS 順序保證」、「重複釋放冪等」。

設計（D-5 凍結）：
- 內部 asyncio.Queue 序列化所有請求
- 單一 worker task 處理（actor 模式）
- 對外 API 為 async reserve / release
- ReservationLedger 三道檢查 + 原子 apply
- 預留成功發布 ReservationCreated；釋放發布 ReservationReleased
- release 對未知 reservation_id 為 no-op（冪等）
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID, uuid4

from risk.events import ReservationCreated, ReservationReleased
from risk.ports import Clock, EventPublisher
from risk.reservation.ledger import Reservation, ReservationLedger
from risk.types import OrderIntent, ReservationResult


@dataclass
class _ReserveRequest:
    intent: OrderIntent
    notional: Decimal
    future: asyncio.Future[ReservationResult]


@dataclass
class _ReleaseRequest:
    reservation_id: UUID
    future: asyncio.Future[None]


_Request = _ReserveRequest | _ReleaseRequest


class CapitalReserver:
    """資金預留 actor。

    對外 API：
      async reserve(intent, notional) -> ReservationResult
      async release(reservation_id) -> None
      async start() / async stop()
    """

    def __init__(
        self,
        *,
        ledger: ReservationLedger,
        clock: Clock,
        publisher: EventPublisher,
    ) -> None:
        self._ledger = ledger
        self._clock = clock
        self._publisher = publisher
        self._queue: asyncio.Queue[_Request] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task is not None:
            raise RuntimeError("CapitalReserver already started")
        self._task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def reserve(
        self,
        *,
        intent: OrderIntent,
        notional: Decimal,
    ) -> ReservationResult:
        """請求預留 notional 金額。actor 序列化保證 FCFS。"""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[ReservationResult] = loop.create_future()
        req = _ReserveRequest(intent=intent, notional=notional, future=future)
        await self._queue.put(req)
        return await future

    async def release(self, reservation_id: UUID) -> None:
        """釋放指定 reservation_id；未知 id 為 no-op（冪等）。"""
        loop = asyncio.get_event_loop()
        future: asyncio.Future[None] = loop.create_future()
        req = _ReleaseRequest(reservation_id=reservation_id, future=future)
        await self._queue.put(req)
        await future

    async def _worker(self) -> None:
        while True:
            request = await self._queue.get()
            try:
                if isinstance(request, _ReserveRequest):
                    result = await self._handle_reserve(request)
                    request.future.set_result(result)
                else:
                    await self._handle_release(request)
                    request.future.set_result(None)
            except Exception as exc:
                request.future.set_exception(exc)

    async def _handle_reserve(self, req: _ReserveRequest) -> ReservationResult:
        check = self._ledger.check(
            strategy_id=req.intent.strategy_id,
            symbol=req.intent.symbol,
            notional=req.notional,
        )
        if not check.ok:
            return ReservationResult(
                ok=False,
                reservation_id=None,
                reason=check.reason,
                available=check.available,
            )

        reservation_id = uuid4()
        reservation = Reservation(
            reservation_id=reservation_id,
            strategy_id=req.intent.strategy_id,
            symbol=req.intent.symbol,
            qty=req.intent.qty,
            notional=req.notional,
            created_at=self._clock.now(),
        )
        self._ledger.apply(reservation)

        await self._publisher.publish(
            ReservationCreated(
                at=self._clock.now(),
                reservation_id=reservation_id,
                strategy_id=req.intent.strategy_id,
                symbol=req.intent.symbol,
                qty=req.intent.qty,
            )
        )
        return ReservationResult(
            ok=True,
            reservation_id=reservation_id,
            reason=None,
            available=None,
        )

    async def _handle_release(self, req: _ReleaseRequest) -> None:
        reservation = self._ledger.revert(req.reservation_id)
        if reservation is None:
            # 冪等：未知 id 為 no-op
            return
        await self._publisher.publish(
            ReservationReleased(
                at=self._clock.now(),
                reservation_id=req.reservation_id,
            )
        )
