"""DIP 邊界：SignalSource / SignalConsumer / StrategyRegistryProtocol。

設計：
- SignalSource 為長生命週期 adapter（async start/stop）；webhook adapter 是 no-op，
  scanner 是 cron loop，stdin reader 等情境會 spawn task
- SignalConsumer 為下游接收器（strategy-host 後續實作）
- StrategyRegistry 在本 capability 為 stub；strategy-host change 提供完整版本
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from signals.types import Signal, StrategyMetadata


@runtime_checkable
class SignalSource(Protocol):
    """訊號來源 adapter 抽象。"""

    async def start(self) -> None: ...
    """啟動 adapter（webhook 為 no-op、scanner 啟 cron task、stdin 啟 reader task）。"""

    async def stop(self) -> None: ...
    """優雅停機。"""


@runtime_checkable
class SignalConsumer(Protocol):
    """訊號下游消費者抽象。

    主要實作者：strategy-host capability（後續 change）。
    觀察性消費（audit log）可作為次要 consumer 旁路接收。
    """

    async def on_signal(self, signal: Signal) -> None: ...


@runtime_checkable
class StrategyRegistryProtocol(Protocol):
    """策略註冊表唯讀介面。

    本 capability 提供 InMemoryStrategyRegistry 實作；
    完整版本（含註冊／生命週期管理）由 strategy-host change 提供。
    """

    def get_strategy_metadata(self, strategy_id: str) -> StrategyMetadata | None: ...
