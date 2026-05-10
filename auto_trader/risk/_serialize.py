"""共用序列化工具：把 dataclass / 值物件正規化為 JSON 友善 dict。

decision.py 與 events.py 共用，避免重複實作。底線前綴表示模組私有。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID


def to_json_safe(obj: Any) -> Any:
    """遞迴正規化：Decimal/UUID/datetime/StrEnum 轉為可被 json.dumps 接受的型別。"""
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [to_json_safe(x) for x in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, StrEnum):
        return obj.value
    return obj
