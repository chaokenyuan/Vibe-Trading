"""SystemClock：使用作業系統真實時間的 Clock 實作。

生產環境預設使用此 Adapter；測試環境注入 FrozenClock。
"""

from __future__ import annotations

import time
from datetime import UTC, datetime


class SystemClock:
    """以 datetime.now(UTC) + time.monotonic() 為後端的 Clock。

    結構性符合 risk.ports.Clock Protocol（不需顯式繼承）。
    所有 wall-clock 一律 UTC，避免本機時區造成跨日 P&L 重置漂移。
    """

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
