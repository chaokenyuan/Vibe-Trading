"""IdempotencyRule：以 signal_id 為主鍵的 5 分鐘 TTL 去重。

對應 spec scenario：
- 首次出現的 signal_id 通過
- 5 分鐘內重送被拒絕
- 5 分鐘後重送視為新訊號
- 快取達上限觸發 LRU 淘汰

凍結決策：D6 signal_id 5 min TTL。
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta

from risk.decision import Outcome, RuleVerdict
from risk.ports import Clock
from risk.rules.base import RuleContext


class IdempotencyRule:
    """signal_id 去重快取。

    TTL：預設 300 秒（5 分鐘），可由建構參數覆寫。
    上限：預設 100,000 筆，達上限時透過 OrderedDict 從前端淘汰最舊條目。
    內部記錄首次出現的 monotonic 時間，供 TTL 計算（與 wall-clock 解耦避免時鐘調整誤刪）。
    """

    name = "IdempotencyRule"

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
        # signal_id -> 首次插入時的 monotonic 秒數
        self._cache: OrderedDict[str, float] = OrderedDict()

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        signal_id = ctx.intent.signal_id
        now = self._clock.monotonic()

        # 若存在且未過期：拒絕
        existing = self._cache.get(signal_id)
        if existing is not None:
            age = now - existing
            if age <= self._ttl_seconds:
                return RuleVerdict(
                    rule_name=self.name,
                    outcome=Outcome.REJECT,
                    before_value=ctx.current_size,
                    after_value=None,
                    message=f"duplicate signal_id within TTL (age={age:.0f}s)",
                    metadata={
                        "signal_id": signal_id,
                        "ttl_seconds": self._ttl_seconds,
                        "age_seconds": age,
                    },
                )
            # 已過期：當作新訊號處理（覆寫條目）
            del self._cache[signal_id]

        # 寫入快取
        self._cache[signal_id] = now
        # 達上限觸發 LRU 淘汰
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.PASS,
            before_value=ctx.current_size,
            after_value=ctx.current_size,
            message="signal_id accepted",
            metadata={"signal_id": signal_id},
        )

    @property
    def ttl(self) -> timedelta:
        """供測試與 observability 取得當前 TTL 設定。"""
        return timedelta(seconds=self._ttl_seconds)

    @property
    def cache_size(self) -> int:
        return len(self._cache)
