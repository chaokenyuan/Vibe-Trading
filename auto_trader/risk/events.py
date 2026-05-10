"""事件基底與具體事件型別。

對應 spec：「所有風控決策與狀態變更須發布事件供審計」。
所有事件 SHALL 為不可變、可序列化、附 event_id (UUID) 與 at (datetime)。

事件清單（spec 列舉）：
- StateChanged：FSM 狀態變遷
- EmergencyFlattenRequested：KILL_SWITCH 觸發後的全平請求
- DecisionEmitted：每筆 RuleEngine 判決
- ReservationCreated / ReservationReleased：資金預留變化
- ConfigLoaded：配置載入
- DailyPnlReset：跨日 P&L 重置
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, cast
from uuid import UUID, uuid4

from risk._serialize import to_json_safe
from risk.decision import Decision


@dataclass(frozen=True, kw_only=True)
class Event:
    """事件基底。

    透過 kw_only=True 讓子類可自由新增有預設值的欄位而不違反 dataclass 排序限制。
    event_id 預設 uuid4 即時生成；at 必填，由發布者注入的 Clock 決定。
    """

    at: datetime
    event_id: UUID = field(default_factory=uuid4)

    def to_dict(self) -> dict[str, Any]:
        """序列化為純資料 dict，可直接被 json.dumps 接受。"""
        return cast(dict[str, Any], to_json_safe(asdict(self)))


@dataclass(frozen=True, kw_only=True)
class StateChanged(Event):
    """FSM 狀態變遷。

    state 以字串表達，避免本檔案依賴 SystemState 列舉（仍未在第 5/6 章建立）。
    StateMachine 負責 SystemState ↔ str 編解碼。
    """

    from_state: str
    to_state: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class EmergencyFlattenRequested(Event):
    """KILL_SWITCH 觸發後對下游請求全平。order-execution capability 消費此事件。"""


@dataclass(frozen=True, kw_only=True)
class DecisionEmitted(Event):
    """每筆 RuleEngine 判決事件。decision 為完整 Decision 物件。"""

    decision: Decision


@dataclass(frozen=True, kw_only=True)
class ReservationCreated(Event):
    """資金預留成功。"""

    reservation_id: UUID
    strategy_id: str
    symbol: str
    qty: Decimal


@dataclass(frozen=True, kw_only=True)
class ReservationReleased(Event):
    """資金預留釋放。"""

    reservation_id: UUID


@dataclass(frozen=True, kw_only=True)
class ConfigLoaded(Event):
    """配置載入完成。params_hash 為配置內容 SHA-256，供審計與 drift 偵測。"""

    params_hash: str


@dataclass(frozen=True, kw_only=True)
class DailyPnlReset(Event):
    """跨日 P&L 重置（依配置時區，預設 UTC 0:00）。"""
