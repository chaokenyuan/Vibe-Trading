"""DIP 邊界：風控閘對外的所有 Protocol 介面集中於此。

設計原則：
- 風控閘內部所有元件僅依賴本檔案的 Protocol，不依賴具體 Adapter
- 介面遵循 ISP（介面隔離）：read-only 與 write-only 分開
- 具體 Adapter 實作放在 risk/adapters/ 與測試替身 tests/fakes/

對應 design 決策：D-7 Clock 抽象、D-10 EventBus 解耦。
對應 spec：「風控閘僅依賴 ports 介面與下游互動」。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable

from risk.events import Event
from risk.types import Position


@runtime_checkable
class Clock(Protocol):
    """時間來源抽象。所有時間相依邏輯 SHALL 透過注入的 Clock 取得時間。

    對應 spec：「所有時間相依邏輯透過 Clock Protocol 注入」。
    """

    def now(self) -> datetime: ...
    """當前 wall-clock 時間，必含 tz。"""

    def monotonic(self) -> float: ...
    """單調遞增秒數，用於 timer 與耗時量測。"""


@runtime_checkable
class PositionReader(Protocol):
    """LogicalBook 與 BrokerPosition 的 read-only 視圖。

    寫入操作不在此介面（由 Reconciler / StrategyHost 負責），
    確保風控規則不會誤改持倉。
    """

    def get_position(self, strategy_id: str, symbol: str) -> Position | None: ...
    """取得單一策略對單一標的的持倉；若不存在回傳 None。"""

    def list_positions(self) -> list[Position]: ...
    """列出所有策略所有標的的持倉。"""


@runtime_checkable
class MarketDataReader(Protocol):
    """市價 read-only 視圖（給 PriceSanityCheck 等規則用）。"""

    def get_last_price(self, symbol: str) -> Decimal: ...
    """取得 symbol 的最近成交價。"""


@runtime_checkable
class ConfigReader(Protocol):
    """配置 read-only 介面。底層可為 in-memory dict 或熱重載來源。

    本 capability MVP 不支援熱載入（E3 凍結），但介面預留語意。
    """

    def get(self, key: str) -> Any: ...
    """以點分路徑取值（如 "fsm.thresholds.daily_pnl_kill"）。"""


@runtime_checkable
class EventPublisher(Protocol):
    """事件發布 write-only 介面。

    具體實作（如 InMemoryEventPublisher）負責 fan-out 給訂閱者。
    publish 為 async 以支援未來跨網路或佇列實作；in-memory 實作可立即返回。
    """

    async def publish(self, event: Event) -> None: ...
    """發布事件至所有訂閱者；不保證遞送順序但保證最終遞送。"""


@runtime_checkable
class StateStore(Protocol):
    """FSM 狀態持久化 Protocol。

    本 capability MVP 提供 InMemoryStateStore（重啟即丟失），
    後續 change 加 SqliteStateStore。
    狀態以不透明字串表達；SystemState 與 str 的編解碼由 StateMachine 負責，
    讓 StateStore 與具體狀態列舉解耦。
    """

    def load_state(self) -> str | None: ...
    """讀回上次保存的狀態；若不存在回傳 None。"""

    def save_state(self, state: str) -> None: ...
    """覆寫保存當前狀態。"""


@runtime_checkable
class StrategyStateReader(Protocol):
    """策略狀態 read-only 介面（給 StrategyPausedRule 用）。

    任何具 `get_state(strategy_id) -> str | None` 的物件結構性符合，
    包含 strategies.registry.StrategyRegistry。
    """

    def get_state(self, strategy_id: str) -> str | None: ...


@runtime_checkable
class EquityReader(Protocol):
    """總權益 read-only 介面（給 PerOrderSizeCap 用）。

    結構性可由 ReservationLedger 滿足（其 total_equity 為 property）。
    """

    @property
    def total_equity(self) -> Decimal: ...


@runtime_checkable
class ReservationLedgerReader(Protocol):
    """ReservationLedger 唯讀視圖（給 cap 類規則用）。"""

    def strategy_available(self, strategy_id: str) -> Decimal: ...

    def symbol_available(self, symbol: str) -> Decimal: ...

    @property
    def total_free(self) -> Decimal: ...
