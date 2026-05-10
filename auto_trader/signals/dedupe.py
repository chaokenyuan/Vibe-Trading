"""SignalDedupe：以 signal_id 為主鍵的 LRU + TTL 快取。

對應 spec：「SignalDedupe 為 LRU + TTL 快取」。
TTL 基於注入的 Clock.monotonic()，與 wall-clock 時鐘調整解耦。
"""

from __future__ import annotations

from collections import OrderedDict

from risk.ports import Clock


class SignalDedupe:
    """signal_id 去重快取。

    用法：
        dedupe = SignalDedupe(clock=clock, ttl_seconds=300, max_entries=100_000)
        if dedupe.is_duplicate(signal_id):
            return  # already seen within TTL
        # 處理新訊號

    注意：is_duplicate 同時是 read-and-record；命中後不會重複插入。
    """

    def __init__(
        self,
        *,
        clock: Clock,
        ttl_seconds: int = 300,
        max_entries: int = 100_000,
    ) -> None:
        self._clock = clock
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._cache: OrderedDict[str, float] = OrderedDict()

    def is_duplicate(self, signal_id: str) -> bool:
        """判斷 signal_id 是否在 TTL 內已出現過。

        命中視為 duplicate 回 True 不更新時間戳；
        未命中或已過期視為新訊號回 False 並寫入快取。
        """
        now = self._clock.monotonic()

        existing = self._cache.get(signal_id)
        if existing is not None:
            age = now - existing
            if age <= self._ttl_seconds:
                return True
            del self._cache[signal_id]

        self._cache[signal_id] = now
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)
        return False

    @property
    def size(self) -> int:
        return len(self._cache)
