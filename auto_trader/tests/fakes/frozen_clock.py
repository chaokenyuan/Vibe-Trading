"""FrozenClock：可控制時間流的 Clock 測試替身。

支援：
- set(datetime)：直接設定 wall-clock 至指定時間
- advance(timedelta)：前進指定時間
- monotonic 與 wall-clock 同步前進（advance 同時影響兩者）

對應 spec scenario：「注入測試 Clock 可控制時間流」。
"""

from __future__ import annotations

from datetime import datetime, timedelta


class FrozenClock:
    """凍結時間的 Clock 實作；測試專用。

    結構性符合 risk.ports.Clock Protocol。
    monotonic 從 0.0 開始，每次 advance 同步增加；set 不改 monotonic。
    """

    def __init__(self, initial: datetime) -> None:
        if initial.tzinfo is None:
            raise ValueError("FrozenClock 必須注入帶 tzinfo 的 datetime")
        self._now: datetime = initial
        self._monotonic: float = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def set(self, new_now: datetime) -> None:
        """直接跳到 new_now；monotonic 不變（避免回退語意）。"""
        if new_now.tzinfo is None:
            raise ValueError("set() 必須帶 tzinfo")
        self._now = new_now

    def advance(self, delta: timedelta) -> None:
        """前進 delta；wall-clock 與 monotonic 同步增加。"""
        if delta.total_seconds() < 0:
            raise ValueError("advance 不接受負時間（時間不能倒流）")
        self._now = self._now + delta
        self._monotonic = self._monotonic + delta.total_seconds()
