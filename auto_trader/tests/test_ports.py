"""Ports（DIP 邊界）結構驗證測試。

對應 spec scenario：
- 注入測試替身可獨立驗證 RuleEngine
- 違反 ISP 應被測試攔截

策略：對每個 Protocol 寫一個最小 fake 實作，以 isinstance 檢查
（透過 @runtime_checkable）確認契約。mypy --strict 在 CI 端把關靜態正確性。
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from risk.events import Event
from risk.ports import (
    Clock,
    ConfigReader,
    EventPublisher,
    MarketDataReader,
    PositionReader,
    StateStore,
)
from risk.types import Position
from tests.fakes.frozen_clock import FrozenClock


def test_position_reader_protocol_runtime_checkable() -> None:
    class FakePositionReader:
        def get_position(self, strategy_id: str, symbol: str) -> Position | None:
            return None

        def list_positions(self) -> list[Position]:
            return []

    assert isinstance(FakePositionReader(), PositionReader)


def test_position_reader_missing_method_fails_isinstance() -> None:
    class IncompleteReader:
        def get_position(self, strategy_id: str, symbol: str) -> Position | None:
            return None

        # 缺少 list_positions

    assert not isinstance(IncompleteReader(), PositionReader)


def test_market_data_reader_protocol() -> None:
    class FakeMarketData:
        def get_last_price(self, symbol: str) -> Decimal:
            return Decimal("65000")

    assert isinstance(FakeMarketData(), MarketDataReader)


def test_config_reader_protocol() -> None:
    class FakeConfig:
        def get(self, key: str) -> Any:
            return None

    assert isinstance(FakeConfig(), ConfigReader)


def test_event_publisher_protocol() -> None:
    class FakePublisher:
        async def publish(self, event: Event) -> None:
            return None

    assert isinstance(FakePublisher(), EventPublisher)


def test_state_store_protocol() -> None:
    class FakeStore:
        def __init__(self) -> None:
            self._state: str | None = None

        def load_state(self) -> str | None:
            return self._state

        def save_state(self, state: str) -> None:
            self._state = state

    assert isinstance(FakeStore(), StateStore)


def test_state_store_load_save_roundtrip() -> None:
    """StateStore 的最簡語意：save 後 load 取回。"""

    class FakeStore:
        def __init__(self) -> None:
            self._state: str | None = None

        def load_state(self) -> str | None:
            return self._state

        def save_state(self, state: str) -> None:
            self._state = state

    store = FakeStore()
    assert store.load_state() is None
    store.save_state("THROTTLED")
    assert store.load_state() == "THROTTLED"


def test_clock_protocol_satisfied_by_frozen_clock() -> None:
    clock = FrozenClock(initial=datetime(2026, 5, 10, tzinfo=UTC))
    assert isinstance(clock, Clock)


def test_clock_protocol_satisfied_by_system_clock() -> None:
    """SystemClock 不需顯式繼承 Protocol，靠結構性 typing。"""
    from risk.adapters.system_clock import SystemClock

    assert isinstance(SystemClock(), Clock)


@pytest.mark.parametrize(
    "protocol_cls",
    [Clock, PositionReader, MarketDataReader, ConfigReader, EventPublisher, StateStore],
)
def test_protocol_marked_as_protocol(protocol_cls: type) -> None:
    """所有 ports 都是 Protocol 類別（而非 ABC 或具體類）。

    透過 typing 內部標記檢查；若某個忘了加 Protocol 基底會失敗。
    """
    assert getattr(protocol_cls, "_is_protocol", False) is True


@pytest.mark.parametrize(
    "protocol_cls",
    [Clock, PositionReader, MarketDataReader, ConfigReader, EventPublisher, StateStore],
)
def test_protocol_runtime_checkable(protocol_cls: type) -> None:
    """所有 ports 都標 @runtime_checkable，支援 isinstance 檢查。"""
    assert getattr(protocol_cls, "_is_runtime_protocol", False) is True
