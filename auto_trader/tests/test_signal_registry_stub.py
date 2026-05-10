"""InMemoryStrategyRegistry 測試。"""

from __future__ import annotations

from signals.ports import StrategyRegistryProtocol
from signals.registry_stub import InMemoryStrategyRegistry
from signals.types import StrategyMetadata


def test_registered_strategy_returns_metadata() -> None:
    """spec scenario：已註冊的 strategy 回傳 metadata。"""
    registry = InMemoryStrategyRegistry()
    metadata = StrategyMetadata(
        strategy_id="A", strategy_version="1.0.0", params_hash="hash"
    )
    registry.register(metadata)

    result = registry.get_strategy_metadata("A")
    assert result == metadata


def test_unknown_strategy_returns_none() -> None:
    """spec scenario：未註冊回傳 None。"""
    registry = InMemoryStrategyRegistry()
    assert registry.get_strategy_metadata("X") is None


def test_register_overwrites_existing() -> None:
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1.0.0", params_hash="h1")
    )
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="2.0.0", params_hash="h2")
    )
    result = registry.get_strategy_metadata("A")
    assert result is not None
    assert result.strategy_version == "2.0.0"


def test_known_strategy_ids_lists_all() -> None:
    registry = InMemoryStrategyRegistry()
    registry.register(
        StrategyMetadata(strategy_id="A", strategy_version="1", params_hash="h")
    )
    registry.register(
        StrategyMetadata(strategy_id="B", strategy_version="1", params_hash="h")
    )
    assert sorted(registry.known_strategy_ids) == ["A", "B"]


def test_satisfies_strategy_registry_protocol() -> None:
    assert isinstance(InMemoryStrategyRegistry(), StrategyRegistryProtocol)
