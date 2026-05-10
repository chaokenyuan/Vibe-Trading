"""RuleContext + RiskRule Protocol + 兩個 marker subprotocol。

對應 spec：「規則引擎採短路評估」、「未實作規則須提供契約 stub」。
所有規則 SHALL 為 stateless 計算（內部快取允許），透過 ctx 取得即時依賴。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from risk.decision import RuleVerdict
from risk.ports import Clock, ConfigReader, MarketDataReader, PositionReader
from risk.types import OrderIntent


@dataclass(frozen=True, kw_only=True)
class RuleContext:
    """單筆 OrderIntent 評估上下文。

    每條規則執行時，engine 重建 RuleContext 並注入「累積 clamp 後的 current_size」。
    所有 ports 為 read-only 視圖。
    """

    intent: OrderIntent
    current_size: Decimal
    current_price: Decimal | None
    positions: PositionReader
    market_data: MarketDataReader
    config: ConfigReader
    clock: Clock


@runtime_checkable
class RiskRule(Protocol):
    """單條風控規則。

    name 為規則識別字串（建議與類別名相同），engine 用於日誌與 RuleVerdict.rule_name。
    evaluate 為純粹計算（除非為 idempotency 等內部快取）；不發布事件、不寫狀態。
    """

    name: str

    def evaluate(self, ctx: RuleContext) -> RuleVerdict: ...


@runtime_checkable
class RejectRule(RiskRule, Protocol):
    """Marker subprotocol：預期回傳 PASS 或 REJECT。

    Engine 短路評估時把此類規則放前段，REJECT 即終止整個評估流程。
    """


@runtime_checkable
class ClampRule(RiskRule, Protocol):
    """Marker subprotocol：預期回傳 PASS 或 CLAMP（極端情況可 REJECT）。

    Engine 累積階段套用此類規則，after_value 必須單調遞減（不增大 size）。
    """
