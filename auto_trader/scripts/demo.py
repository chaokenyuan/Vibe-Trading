"""vibe-auto-trader 端到端 demo。

不需真交易所、不需 TradingView 帳號；全部組件以 Mock 串起來，逐步印出
每階段發生了什麼。執行：

    python scripts/demo.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

# 確保可從任何 cwd 執行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from execution.adapters.mock import MockExecutionAdapter
from execution.sink import ExchangeOrderSink
from observability.adapters.logging_sink import LoggingAlertSink
from observability.alert_router import AlertRouter
from observability.audit_log import AuditLogWriter
from reconciliation.adapters.mock import MockFillSource
from reconciliation.processor import FillProcessor
from reservation_bridge.bridge import ReservationBridge
from risk.adapters.in_memory_publisher import InMemoryEventPublisher
from risk.config import RiskConfig
from risk.gate import RiskGate
from risk.reservation.ledger import ReservationLedger
from risk.state.persistence import InMemoryStateStore
from risk.types import Side
from signals.adapters.tradingview import (
    TradingViewWebhookAdapter,
    create_tradingview_app,
)
from signals.config import TradingViewConfig
from signals.dedupe import SignalDedupe
from signals.router import SignalRouter
from strategies.host import StrategyHost
from strategies.registry import StrategyRegistry
from strategies.strategies.passthrough import PassthroughStrategy
from strategies.types import Fill, StrategyState

UTC = UTC
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ---------- demo 的 Mock 實作（讓 RiskGate 開心；非生產） ----------


class _NopPositions:
    def get_position(self, sid: str, sym: str) -> Any:
        return None

    def list_positions(self) -> list[Any]:
        return []


class _ConstMarket:
    def get_last_price(self, sym: str) -> Decimal:
        return Decimal("65000")


class _NopConfig:
    def get(self, k: str) -> Any:
        return None


# ---------- pretty print helpers ----------


def banner(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def step(n: int, desc: str) -> None:
    print(f"\n[STEP {n}] {desc}")


def show(label: str, value: Any) -> None:
    print(f"  {label}: {value}")


# ---------- main ----------


async def main() -> None:
    banner("vibe-auto-trader demo — 端到端訊號到下單再到對帳")

    # ============================================================
    # 1. 建構共用基礎設施
    # ============================================================
    step(1, "建立共用 publisher / clock / ledger")

    publisher = InMemoryEventPublisher()
    # 為了示範用真實時鐘（生產情境）。測試用 FrozenClock。
    from risk.adapters.system_clock import SystemClock

    clock = SystemClock()

    ledger = ReservationLedger(
        total_equity=Decimal("100000"),
        strategy_budgets={"vibe_btc_v1": Decimal("50000")},
        symbol_caps={"BTCUSDT": Decimal("40000")},
    )
    show("total_equity", ledger.total_equity)
    show("strategy A budget", ledger.strategy_available("vibe_btc_v1"))
    show("BTCUSDT concentration cap", ledger.symbol_available("BTCUSDT"))

    # ============================================================
    # 2. RiskGate（雙層風控）
    # ============================================================
    step(2, "建構 RiskGate（FSM + RuleEngine + CapitalReserver）")

    # 使用一個簡化的 rules.enabled 清單以避免 PerOrderSizeCap 把 demo 量縮為 0
    risk_config = RiskConfig.from_yaml(PROJECT_ROOT / "config" / "risk.yaml")
    risk_config = risk_config.model_copy(
        update={
            "rules": risk_config.rules.model_copy(
                update={
                    "enabled": [
                        "SystemStateRule",
                        "IdempotencyRule",
                        "SignalFreshnessRule",
                        "SymbolWhitelistRule",
                        "CapitalReservationRule",  # 取得 reservation_id
                    ],
                    # 縮短 warming_up
                },
            ),
            "warming_up": risk_config.warming_up.model_copy(update={"duration_seconds": 0}),
        }
    )

    risk_gate = RiskGate(
        config=risk_config,
        clock=clock,
        store=InMemoryStateStore(),
        publisher=publisher,
        positions=_NopPositions(),
        market_data=_ConstMarket(),
        config_reader=_NopConfig(),
        ledger=ledger,
    )
    await risk_gate.start()
    show("FSM 初始狀態", risk_gate.state.value)
    show("啟用的規則", [type(r).__name__ for r in risk_gate._engine._rules])

    # ============================================================
    # 3. StrategyRegistry + StrategyHost + ExchangeOrderSink
    # ============================================================
    step(3, "建構 StrategyRegistry + StrategyHost + ExchangeOrderSink")

    registry = StrategyRegistry()
    strategy = PassthroughStrategy(
        strategy_id="vibe_btc_v1",
        strategy_version="1.0.0",
        params_hash="hash_demo",
    )
    registry.register(strategy)
    registry.set_state("vibe_btc_v1", StrategyState.ACTIVE)

    mock_broker = MockExecutionAdapter()
    sink = ExchangeOrderSink(adapter=mock_broker, publisher=publisher, clock=clock)
    host = StrategyHost(registry=registry, risk_gate=risk_gate, order_sink=sink)
    show("strategy_id", strategy.strategy_id)
    show("state", registry.get_state("vibe_btc_v1"))

    # ============================================================
    # 4. SignalRouter + TradingView Webhook FastAPI
    # ============================================================
    step(4, "建構 SignalRouter + TradingView Webhook app")

    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    signal_router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    signal_router.subscribe(host)  # StrategyHost 是 SignalConsumer

    tv_config = TradingViewConfig(secret="demo_secret_8chars", allowed_ips=[])
    tv_adapter = TradingViewWebhookAdapter()
    tv_app = create_tradingview_app(adapter=tv_adapter, router=signal_router, config=tv_config)
    show("webhook URL", "/webhook/tv/demo_secret_8chars/vibe_btc_v1")

    # ============================================================
    # 5. ReservationBridge
    # ============================================================
    step(5, "建構 ReservationBridge（自動釋放預留）")

    bridge = ReservationBridge(
        publisher=publisher,
        reserver=risk_gate.reserver,
        clock=clock,
    )
    bridge.start()
    show("已訂閱事件", "OrderSubmitted / OrderRejectedByBroker / FillProcessed")

    # ============================================================
    # 6. Reconciliation（FillProcessor + MockFillSource）
    # ============================================================
    step(6, "建構 FillProcessor + MockFillSource")

    fill_processor = FillProcessor(
        registry=registry, publisher=publisher, clock=clock
    )
    fill_source = MockFillSource(callback=fill_processor.on_fill)
    await fill_source.start()

    # ============================================================
    # 7. Observability（AuditLog + AlertRouter + Health）
    # ============================================================
    step(7, "建構 AuditLogWriter + AlertRouter")

    audit_path = PROJECT_ROOT / "logs" / "demo_audit.jsonl"
    if audit_path.exists():
        audit_path.unlink()
    audit = AuditLogWriter(publisher=publisher, log_path=audit_path)
    audit.start()

    alert_router = AlertRouter(publisher=publisher, sink=LoggingAlertSink())
    alert_router.start()
    show("audit log 路徑", audit_path)

    # ============================================================
    # 8. 實際送一筆 TradingView 訊號
    # ============================================================
    step(8, "從 TradingView webhook 送入訊號（用 httpx ASGITransport，不啟 uvicorn）")

    bar_time = datetime.now(UTC) - timedelta(seconds=5)  # 確保 freshness 不超過 30s
    payload = {
        "v": 1,
        "strategy_id": "vibe_btc_v1",
        "symbol": "BTCUSDT",
        "side": "BUY",
        "qty": "0.1",
        "price": "65000",
        "bar_time": bar_time.isoformat(),
        "interval": "60",
        "comment": "demo signal",
    }
    show("payload", json.dumps(payload, ensure_ascii=False))

    transport = httpx.ASGITransport(app=tv_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        response = await client.post(
            "/webhook/tv/demo_secret_8chars/vibe_btc_v1", json=payload
        )

    show("webhook 回應", f"{response.status_code} {response.json()}")

    # 給 publisher fan-out 一些時間
    await asyncio.sleep(0.05)

    # ============================================================
    # 9. 觀察結果：訊號被路由 → 策略 → 風控 → 下單
    # ============================================================
    step(9, "觀察執行結果")

    show("MockExecutionAdapter 收到訂單數", len(mock_broker.submitted))
    if mock_broker.submitted:
        record = mock_broker.submitted[0]
        show("  client_order_id", record.client_order_id)
        show("  broker_order_id", record.broker_order_id)
        show("  qty", record.intent.qty)

    show("CapitalReserver ledger reserved", ledger.total_reserved)
    show("ReservationBridge mapping size", bridge.mapping_size)

    # ============================================================
    # 10. 模擬交易所回報成交
    # ============================================================
    step(10, "模擬交易所回報成交（透過 MockFillSource）")

    submitted = mock_broker.submitted[0]
    fill = Fill(
        fill_id=uuid4(),
        client_order_id=submitted.client_order_id,
        broker_order_id=submitted.broker_order_id or "bo-demo",
        symbol="BTCUSDT",
        side=Side.BUY,
        qty=Decimal("0.1"),
        price=Decimal("65000"),
        fees=Decimal("0.5"),
        at=datetime.now(UTC),
    )
    show("fill_id", fill.fill_id)
    await fill_source.push(fill)
    await asyncio.sleep(0.05)

    # ============================================================
    # 11. 觀察 fill 結果：LogicalBook 更新 + reservation 釋放
    # ============================================================
    step(11, "觀察 fill 處理結果")

    book = registry.get_book("vibe_btc_v1")
    if book:
        position = book.get_position("BTCUSDT")
        if position:
            show("LogicalBook BTCUSDT qty", position.qty)
            show("LogicalBook avg_entry", position.avg_entry)

    show("CapitalReserver ledger reserved（應已釋放）", ledger.total_reserved)
    show("ReservationBridge mapping size（應已移除）", bridge.mapping_size)

    # ============================================================
    # 12. 觀察 audit log
    # ============================================================
    step(12, "觀察 audit log（前 5 筆事件）")

    if audit_path.exists():
        lines = audit_path.read_text(encoding="utf-8").splitlines()
        show("總事件數", len(lines))
        for i, line in enumerate(lines[:5], start=1):
            event = json.loads(line)
            event_type = "Event"
            for key in ("from_state", "client_order_id", "params_hash", "fill_id"):
                if key in event:
                    event_type = {
                        "from_state": "StateChanged",
                        "client_order_id": "Order/Fill",
                        "params_hash": "ConfigLoaded",
                        "fill_id": "FillProcessed",
                    }[key]
                    break
            print(f"  #{i:2d} {event_type:18s}  at={event.get('at', '?')}")

    # ============================================================
    # 13. 觀察 FSM 狀態（KILL_SWITCH 模擬）
    # ============================================================
    step(13, "觸發 KILL_SWITCH 看告警")
    await risk_gate.state_machine.tick(daily_pnl_ratio=-0.10, api_error_rate=0.0)
    await asyncio.sleep(0.05)
    show("FSM 狀態", risk_gate.state.value)

    # ============================================================
    # 收尾
    # ============================================================
    await fill_source.stop()
    await risk_gate.shutdown()

    banner("demo 結束")
    print()
    print("這個 demo 沒接真交易所、沒接 TradingView。所有元件以 Mock 串起來，")
    print("驗證 8 個 capability + 23 個 commit 的設計可實際運作。")
    print()
    print("實際部署時：")
    print("  - MockExecutionAdapter → CcxtExecutionAdapter（真 broker）")
    print("  - MockFillSource → CcxtFillSource（broker WebSocket）")
    print("  - ASGITransport → uvicorn 實際 listen")
    print("  - LoggingAlertSink → TelegramAlertSink（真 bot）")
    print()


if __name__ == "__main__":
    asyncio.run(main())
