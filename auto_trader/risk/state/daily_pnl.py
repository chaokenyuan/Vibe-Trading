"""日內 P&L 追蹤器，跨日（依配置時區）重置。

對應 spec：「所有時間相依邏輯透過 Clock Protocol 注入」、
       「跨日重置依配置時區」。

E7 凍結決策：跨日重置時點 = UTC 0:00（加密 24×7，業界默認）。
配置可改為其他時區（如 GMT+8）。
"""

from __future__ import annotations

from datetime import date, datetime, tzinfo
from zoneinfo import ZoneInfo

from risk.events import DailyPnlReset
from risk.ports import Clock, EventPublisher


class DailyPnlTracker:
    """日內 P&L 計數器；跨日邊界自動重置並發布 DailyPnlReset 事件。

    用法：
      - 訊號／成交發生 → 呼叫 update(pnl_ratio) 寫入當前值
      - 定時（例如 FSM tick 同步點）→ 呼叫 await maybe_reset()
      - FSM tick 取數 → 呼叫 get() 取當前 pnl_ratio
    """

    def __init__(
        self,
        *,
        clock: Clock,
        publisher: EventPublisher,
        tz: str = "UTC",
    ) -> None:
        self._clock = clock
        self._publisher = publisher
        self._tz: tzinfo = ZoneInfo(tz)
        self._current_date: date = self._date_in_tz(clock.now())
        self._pnl_ratio: float = 0.0

    def update(self, pnl_ratio: float) -> None:
        """設定當前 PnL 比例（佔總權益）。"""
        self._pnl_ratio = pnl_ratio

    def get(self) -> float:
        """取當前 PnL 比例。"""
        return self._pnl_ratio

    @property
    def current_date(self) -> date:
        """當前歸屬的日期（依配置時區）。"""
        return self._current_date

    async def maybe_reset(self) -> bool:
        """偵測跨日：若已過邊界則重置 pnl_ratio 為 0、發布 DailyPnlReset 事件。

        Returns:
            True 表示已重置；False 表示同一天無動作。
        """
        now_date = self._date_in_tz(self._clock.now())
        if now_date == self._current_date:
            return False

        self._current_date = now_date
        self._pnl_ratio = 0.0
        await self._publisher.publish(DailyPnlReset(at=self._clock.now()))
        return True

    def _date_in_tz(self, dt: datetime) -> date:
        return dt.astimezone(self._tz).date()
