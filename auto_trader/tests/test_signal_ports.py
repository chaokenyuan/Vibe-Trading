"""Signals ports 結構驗證測試。"""

from __future__ import annotations

import pytest

from signals.ports import (
    SignalConsumer,
    SignalSource,
    StrategyRegistryProtocol,
)
from signals.types import Signal, StrategyMetadata


@pytest.mark.parametrize(
    "protocol_cls",
    [SignalSource, SignalConsumer, StrategyRegistryProtocol],
)
def test_protocol_marked_runtime_checkable(protocol_cls: type) -> None:
    assert getattr(protocol_cls, "_is_protocol", False) is True
    assert getattr(protocol_cls, "_is_runtime_protocol", False) is True


def test_signal_source_isinstance_check() -> None:
    class FakeSource:
        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

    assert isinstance(FakeSource(), SignalSource)


def test_signal_consumer_isinstance_check() -> None:
    class FakeConsumer:
        async def on_signal(self, signal: Signal) -> None:
            pass

    assert isinstance(FakeConsumer(), SignalConsumer)


def test_strategy_registry_protocol_isinstance_check() -> None:
    class FakeRegistry:
        def get_strategy_metadata(self, strategy_id: str) -> StrategyMetadata | None:
            return None

    assert isinstance(FakeRegistry(), StrategyRegistryProtocol)


def test_incomplete_signal_source_not_isinstance() -> None:
    class IncompleteSource:
        async def start(self) -> None:
            pass

        # 缺 stop

    assert not isinstance(IncompleteSource(), SignalSource)
