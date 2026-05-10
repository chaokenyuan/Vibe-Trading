"""StrategyRegistry 測試。"""

from __future__ import annotations

import pytest

from signals.ports import StrategyRegistryProtocol
from strategies.registry import StrategyRegistry
from strategies.strategies.passthrough import PassthroughStrategy
from strategies.types import StrategyState


def _strategy(strategy_id: str = "A") -> PassthroughStrategy:
    return PassthroughStrategy(
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        params_hash="hash",
    )


def test_register_creates_loaded_state_and_book() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    assert registry.get_state("A") == StrategyState.LOADED
    assert registry.get_book("A") is not None


def test_set_state_updates() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    registry.set_state("A", StrategyState.ACTIVE)
    assert registry.get_state("A") == StrategyState.ACTIVE


def test_set_state_unknown_raises() -> None:
    registry = StrategyRegistry()
    with pytest.raises(KeyError):
        registry.set_state("X", StrategyState.ACTIVE)


def test_get_strategy_unknown_returns_none() -> None:
    registry = StrategyRegistry()
    assert registry.get_strategy("X") is None
    assert registry.get_book("X") is None
    assert registry.get_state("X") is None


def test_list_strategies() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    registry.register(_strategy("B"))
    assert sorted(registry.list_strategies()) == ["A", "B"]


def test_satisfies_strategy_registry_protocol() -> None:
    """spec scenario：registry 滿足 signal-ingestion StrategyRegistryProtocol。"""
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    assert isinstance(registry, StrategyRegistryProtocol)


def test_get_strategy_metadata_returns_metadata() -> None:
    registry = StrategyRegistry()
    registry.register(_strategy("A"))
    md = registry.get_strategy_metadata("A")
    assert md is not None
    assert md.strategy_id == "A"
    assert md.strategy_version == "1.0.0"


def test_get_strategy_metadata_unknown_returns_none() -> None:
    registry = StrategyRegistry()
    assert registry.get_strategy_metadata("X") is None
