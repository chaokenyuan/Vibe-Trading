"""Signal canonical 值物件 + StrategyMetadata + SignalSourceKind 列舉。

對應 spec：「Signal 為不可變正規化值物件」、
       「StrategyRegistry stub 提供唯讀介面凍結」。
所有值物件 SHALL 為 frozen dataclass。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal, cast

from risk._serialize import to_json_safe

SCHEMA_VERSION_CURRENT = 1


class SignalSourceKind(StrEnum):
    """訊號來源類型。"""

    TRADINGVIEW = "tradingview"
    MT5 = "mt5"
    VIBE_SHADOW = "vibe_shadow"
    MANUAL = "manual"


@dataclass(frozen=True, kw_only=True)
class StrategyMetadata:
    """StrategyRegistry 對外回傳的中繼資料。

    供 SignalRouter 補齊 Signal 的 strategy_version 與 params_hash 欄位，
    支撐回測再現性（同 strategy_id + version + params_hash 可重放）。
    """

    strategy_id: str
    strategy_version: str
    params_hash: str


@dataclass(frozen=True, kw_only=True)
class Signal:
    """canonical Signal：訊號入口層的正規化輸出。

    schema_version: 隨格式演進遞增；當前為 1。
    signal_id: SignalRouter 計算的去重主鍵。
    raw_payload: 來源原始輸入（供審計與重放）。
    """

    schema_version: int
    signal_id: str
    strategy_id: str
    strategy_version: str
    params_hash: str
    symbol: str
    side: Literal["BUY", "SELL", "CLOSE"]
    qty: Decimal
    price: Decimal | None
    bar_time: datetime
    interval: str
    received_at: datetime
    source: SignalSourceKind
    comment: str | None
    raw_payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        """序列化為純資料 dict，可直接被 json.dumps 接受。"""
        return cast(dict[str, Any], to_json_safe(asdict(self)))
