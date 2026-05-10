"""StateMachine：FSM Layer 1 引擎。

對應 spec：
- 啟動讀回 + 立即首次 tick
- 每 60 秒週期 tick（自動轉換）
- KILL_SWITCH 觸發自動全平 + 4 小時冷靜期
- 人工 reset / enter_maintenance / exit_maintenance
- 冷靜期內 reset 拒絕並回傳剩餘時間
- 所有狀態變更發布 StateChanged + 必要時 EmergencyFlattenRequested
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from risk.config import FsmThresholds
from risk.events import EmergencyFlattenRequested, StateChanged
from risk.ports import Clock, EventPublisher, StateStore
from risk.state.states import SystemState
from risk.state.transitions import evaluate_transition

MetricsProvider = Callable[[], Awaitable[tuple[float, float]]]
"""async callable 回傳 (daily_pnl_ratio, api_error_rate)。"""


@dataclass(frozen=True, kw_only=True)
class ResetResult:
    """人工 reset 指令的回傳結果。

    冷靜期內：ok=False、cooling_remaining_seconds 為剩餘秒數。
    成功：ok=True、cooling_remaining_seconds=None。
    """

    ok: bool
    cooling_remaining_seconds: float | None
    message: str | None = None


class StateMachine:
    """FSM Layer 1 引擎；單例（全系統共用）。

    建構時從 StateStore 讀回狀態（無則 NORMAL）。
    所有時間相依透過注入的 Clock，便於測試。
    """

    def __init__(
        self,
        *,
        clock: Clock,
        store: StateStore,
        publisher: EventPublisher,
        thresholds: FsmThresholds,
        cooling_seconds: int,
        tick_interval_seconds: int = 60,
    ) -> None:
        self._clock = clock
        self._store = store
        self._publisher = publisher
        self._thresholds = thresholds
        self._cooling_seconds = cooling_seconds
        self._tick_interval = tick_interval_seconds

        loaded = store.load_state()
        self._state: SystemState = (
            SystemState.NORMAL if loaded is None else SystemState(loaded)
        )

        # 進入 KILL_SWITCH 當下的 monotonic 時間，用於計算冷靜期
        self._kill_switch_entered_monotonic: float | None = None
        self._task: asyncio.Task[None] | None = None

    @property
    def state(self) -> SystemState:
        return self._state

    async def tick(self, daily_pnl_ratio: float, api_error_rate: float) -> None:
        """單次 tick：依 metrics 計算轉換並執行。

        外部呼叫者（如 start() 主循環）應每隔 tick_interval_seconds 呼叫一次。
        """
        target = evaluate_transition(
            self._state,
            daily_pnl_ratio=daily_pnl_ratio,
            api_error_rate=api_error_rate,
            thresholds=self._thresholds,
        )
        if target != self._state:
            await self._transition(
                target,
                reason=f"daily_pnl_ratio={daily_pnl_ratio:.4f},api_error_rate={api_error_rate:.4f}",
            )

    async def reset(self, target: SystemState = SystemState.NORMAL) -> ResetResult:
        """人工 reset 指令；HALTED 與 KILL_SWITCH 唯一的解鎖路徑。

        KILL_SWITCH 冷靜期內 SHALL 拒絕並回傳剩餘時間。
        """
        if self._state == SystemState.KILL_SWITCH:
            remaining = self._cooling_remaining()
            if remaining > 0:
                return ResetResult(
                    ok=False,
                    cooling_remaining_seconds=remaining,
                    message=f"KILL_SWITCH 冷靜期內，剩餘 {remaining:.0f} 秒",
                )
            self._kill_switch_entered_monotonic = None

        await self._transition(target, reason="manual_reset")
        return ResetResult(ok=True, cooling_remaining_seconds=None)

    async def enter_maintenance(self) -> None:
        """人工進入維護模式；無視 metrics 與冷靜期。"""
        await self._transition(SystemState.MAINTENANCE, reason="manual_enter_maintenance")

    async def exit_maintenance(self, target: SystemState = SystemState.NORMAL) -> None:
        """人工離開維護模式；只能從 MAINTENANCE 呼叫。"""
        if self._state != SystemState.MAINTENANCE:
            raise RuntimeError(f"not in MAINTENANCE: current={self._state}")
        await self._transition(target, reason="manual_exit_maintenance")

    async def start(self, metrics_provider: MetricsProvider) -> None:
        """啟動 tick 主循環：立即執行首次 tick，之後每 tick_interval 執行一次。

        對應 spec：「啟動後立即執行 tick，不等 60 秒週期」。
        """
        if self._task is not None:
            raise RuntimeError("StateMachine already started")
        self._task = asyncio.create_task(self._run_loop(metrics_provider))

    async def stop(self) -> None:
        """優雅停機：取消 tick 主循環。"""
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _run_loop(self, metrics_provider: MetricsProvider) -> None:
        # 啟動立即首次 tick
        await self._do_tick_safe(metrics_provider)
        while True:
            await asyncio.sleep(self._tick_interval)
            await self._do_tick_safe(metrics_provider)

    async def _do_tick_safe(self, metrics_provider: MetricsProvider) -> None:
        try:
            pnl, err = await metrics_provider()
        except Exception:
            # metrics 失敗不應拖垮 tick 循環；觀察性事件留給後續 change
            return
        await self.tick(pnl, err)

    async def _transition(self, target: SystemState, *, reason: str) -> None:
        old = self._state
        self._state = target
        self._store.save_state(target.value)

        await self._publisher.publish(
            StateChanged(
                at=self._clock.now(),
                from_state=old.value,
                to_state=target.value,
                reason=reason,
            )
        )

        if target == SystemState.KILL_SWITCH:
            # 紀錄進入時間（用於冷靜期計算）+ 廣播全平請求
            self._kill_switch_entered_monotonic = self._clock.monotonic()
            await self._publisher.publish(
                EmergencyFlattenRequested(at=self._clock.now())
            )

    def _cooling_remaining(self) -> float:
        """KILL_SWITCH 冷靜期剩餘秒數；非 KILL_SWITCH 或已過冷靜期回傳 0。"""
        if self._kill_switch_entered_monotonic is None:
            return 0.0
        elapsed = self._clock.monotonic() - self._kill_switch_entered_monotonic
        remaining = self._cooling_seconds - elapsed
        return max(remaining, 0.0)
