"""啟動 vibe-auto-trader webhook server（uvicorn）。

不需真交易所——broker 仍用 MockExecutionAdapter；但 webhook 是真實 HTTP server，
可被 curl / Postman / TradingView 打到。

用法：
    # 1. 設定 secret（自行產強隨機值）
    export VIBE_TV_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"

    # 2. 啟動
    python scripts/run_server.py

    # 3. 另一個 terminal 用 curl 測試
    curl -X POST "http://localhost:8000/webhook/tv/$VIBE_TV_SECRET/vibe_btc_v1" \\
      -H "Content-Type: application/json" \\
      -d '{"v":1,"strategy_id":"vibe_btc_v1","symbol":"BTCUSDT",
           "side":"BUY","qty":"0.1","price":"65000",
           "bar_time":"2026-05-10T12:00:00+00:00","interval":"60","comment":null}'

    # 4. Ctrl+C 結束（會優雅停機）

實際接 TradingView 時：
- 把 server 部署到有公開 IP 的機器
- 透過 reverse proxy（Cloudflare/Caddy）配 TLS
- TradingView Pine alert 的 webhook URL 設為 https://your-domain/webhook/tv/{secret}/{strategy_id}
- config/signal_ingestion.yaml 的 allowed_ips 改成 TV 4 個官方 IP
- 把 MockExecutionAdapter 換成 CcxtExecutionAdapter（後續 change 實作）
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

# 確保可從任何 cwd 執行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uvicorn  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from execution.adapters.mock import MockExecutionAdapter  # noqa: E402
from execution.sink import ExchangeOrderSink  # noqa: E402
from observability.adapters.logging_sink import LoggingAlertSink  # noqa: E402
from observability.alert_router import AlertRouter  # noqa: E402
from observability.audit_log import AuditLogWriter  # noqa: E402
from observability.health import create_health_app  # noqa: E402
from reconciliation.processor import FillProcessor  # noqa: E402
from reservation_bridge.bridge import ReservationBridge  # noqa: E402
from risk.adapters.in_memory_publisher import InMemoryEventPublisher  # noqa: E402
from risk.adapters.system_clock import SystemClock  # noqa: E402
from risk.config import RiskConfig  # noqa: E402
from risk.gate import RiskGate  # noqa: E402
from risk.reservation.ledger import ReservationLedger  # noqa: E402
from risk.state.persistence import InMemoryStateStore  # noqa: E402
from signals.adapters.tradingview import (  # noqa: E402
    TradingViewWebhookAdapter,
    create_tradingview_app,
)
from signals.config import TradingViewConfig  # noqa: E402
from signals.dedupe import SignalDedupe  # noqa: E402
from signals.router import SignalRouter  # noqa: E402
from strategies.host import StrategyHost  # noqa: E402
from strategies.registry import StrategyRegistry  # noqa: E402
from strategies.strategies.passthrough import PassthroughStrategy  # noqa: E402
from strategies.types import StrategyState  # noqa: E402

UTC = timezone.utc
PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ===== API request models（module level：避免 FastAPI 在 from __future__ annotations
#       下對 nested class 解析失敗，誤判為 query 參數）=====


class StrategyStateChange(BaseModel):
    state: str


class MaintenanceAction(BaseModel):
    action: str  # "enter" or "exit"


class TickArgs(BaseModel):
    daily_pnl_ratio: float
    api_error_rate: float


class StrategyCreate(BaseModel):
    strategy_id: str
    strategy_version: str = "1.0.0"
    params_hash: str = ""

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
)
logger = logging.getLogger("vibe.server")


# ---------- demo 用的 mock ports ----------


class _NopPositions:
    def get_position(self, sid: str, sym: str) -> Any:
        return None

    def list_positions(self) -> list[Any]:
        return []


class _RandomWalkMarket:
    """模擬市場：每次呼叫 get_last_price 在前次價格附近隨機漫步。

    用於 demo K 線；同時讓 PnL 不為 0。
    """

    def __init__(self) -> None:
        import random as _random

        self._random = _random.Random(42)
        self._prices: dict[str, Decimal] = {
            "BTCUSDT": Decimal("65000"),
            "ETHUSDT": Decimal("3000"),
        }
        # 每 symbol 保留最近 200 個 candle（{at, open, high, low, close}）
        self._candles: dict[str, list[dict[str, Any]]] = {
            "BTCUSDT": [],
            "ETHUSDT": [],
        }

    def get_last_price(self, sym: str) -> Decimal:
        if sym not in self._prices:
            self._prices[sym] = Decimal("100")
            self._candles.setdefault(sym, [])
        # ±0.3% 隨機漫步
        delta_pct = (self._random.random() - 0.5) * 0.006
        new = self._prices[sym] * (Decimal("1") + Decimal(str(delta_pct)))
        self._prices[sym] = new.quantize(Decimal("0.01"))
        return self._prices[sym]

    def append_candle(self, sym: str, ts_iso: str) -> None:
        """每秒呼叫一次：從當前 last_price 取一個 OHLC（高低為微擾）。"""
        last = self.get_last_price(sym)
        # 簡化：open=high=low=close=last（實務需收集多 tick）
        # 這裡用前次收盤當 open，本次當 close，high/low 用 close ± 0.1%
        candles = self._candles.setdefault(sym, [])
        prev_close = candles[-1]["close"] if candles else float(last)
        candle = {
            "at": ts_iso,
            "open": float(prev_close),
            "high": float(last) * 1.001,
            "low": float(last) * 0.999,
            "close": float(last),
        }
        candles.append(candle)
        if len(candles) > 200:
            candles.pop(0)

    def candles(self, sym: str) -> list[dict[str, Any]]:
        return list(self._candles.get(sym, []))


class _NopConfig:
    def get(self, k: str) -> Any:
        return None


# ---------- 主流程 ----------


def _read_secret() -> str:
    secret = os.environ.get("VIBE_TV_SECRET", "").strip()
    if not secret:
        sys.stderr.write(
            "ERROR: VIBE_TV_SECRET 環境變數未設定。\n"
            "請執行：export VIBE_TV_SECRET=\"$(python -c 'import secrets; "
            "print(secrets.token_urlsafe(24))')\"\n"
        )
        sys.exit(1)
    if len(secret) < 8:
        sys.stderr.write("ERROR: VIBE_TV_SECRET 長度需 >= 8 字元。\n")
        sys.exit(1)
    return secret


def build_app() -> tuple[FastAPI, RiskGate, MockExecutionAdapter]:
    """組合所有元件並回傳：(combined FastAPI app, risk gate, mock broker)。"""
    secret = _read_secret()

    publisher = InMemoryEventPublisher()
    clock = SystemClock()

    # === risk-gate ===
    risk_config = RiskConfig.from_yaml(PROJECT_ROOT / "config" / "risk.yaml")
    # 本地 demo：縮短 warming_up，啟用核心規則
    risk_config = risk_config.model_copy(
        update={
            "rules": risk_config.rules.model_copy(
                update={
                    "enabled": [
                        "SystemStateRule",
                        "IdempotencyRule",
                        "SignalFreshnessRule",
                        "SymbolWhitelistRule",
                        "CapitalReservationRule",
                    ],
                }
            ),
            "warming_up": risk_config.warming_up.model_copy(
                update={"duration_seconds": 0},
            ),
        }
    )

    ledger = ReservationLedger(
        total_equity=Decimal("100000"),
        strategy_budgets={"vibe_btc_v1": Decimal("50000")},
        symbol_caps={"BTCUSDT": Decimal("40000")},
    )

    market = _RandomWalkMarket()

    risk_gate = RiskGate(
        config=risk_config,
        clock=clock,
        store=InMemoryStateStore(),
        publisher=publisher,
        positions=_NopPositions(),
        market_data=market,
        config_reader=_NopConfig(),
        ledger=ledger,
    )

    # === strategies ===
    registry = StrategyRegistry()
    strategy = PassthroughStrategy(
        strategy_id="vibe_btc_v1",
        strategy_version="1.0.0",
        params_hash=f"server_run_{uuid4().hex[:8]}",
    )
    registry.register(strategy)
    registry.set_state("vibe_btc_v1", StrategyState.ACTIVE)

    # === order-execution（仍 Mock，未接真 broker） ===
    mock_broker = MockExecutionAdapter()
    sink = ExchangeOrderSink(adapter=mock_broker, publisher=publisher, clock=clock)
    host = StrategyHost(registry=registry, risk_gate=risk_gate, order_sink=sink)

    # === signal-ingestion ===
    dedupe = SignalDedupe(clock=clock, ttl_seconds=300)
    signal_router = SignalRouter(clock=clock, registry=registry, dedupe=dedupe)
    signal_router.subscribe(host)

    tv_config = TradingViewConfig(
        secret=secret,
        # 本機開發接受所有 IP；production 改 TV 4 IP
        allowed_ips=[],
    )
    tv_adapter = TradingViewWebhookAdapter()
    tv_app = create_tradingview_app(
        adapter=tv_adapter, router=signal_router, config=tv_config
    )

    # === reservation-release bridge ===
    bridge = ReservationBridge(
        publisher=publisher, reserver=risk_gate.reserver, clock=clock
    )
    bridge.start()

    # === reconciliation（沒接真 fill source；fill 由 /test/fill 端點注入） ===
    fill_processor = FillProcessor(
        registry=registry, publisher=publisher, clock=clock
    )

    # === observability ===
    audit_path = PROJECT_ROOT / "logs" / "server_audit.jsonl"
    audit = AuditLogWriter(publisher=publisher, log_path=audit_path)
    audit.start()

    alert_router = AlertRouter(publisher=publisher, sink=LoggingAlertSink())
    alert_router.start()

    # === health endpoint ===
    health_app = create_health_app(clock=clock)

    # === 把 health endpoint mount 到 webhook app（同一 server 兩條路由） ===
    tv_app.mount("/_health", health_app)

    # === 提供 /test/fill 端點：手動模擬 fill 進來（方便 demo） ===
    from fastapi import HTTPException

    from risk.types import Side
    from strategies.types import Fill

    @tv_app.post("/test/fill/{client_order_id}")
    async def test_fill(client_order_id: str) -> dict[str, Any]:
        """測試端點：根據 client_order_id 找 mock_broker 的 record 並推 fill。"""
        record = next(
            (r for r in mock_broker.submitted if r.client_order_id == client_order_id),
            None,
        )
        if record is None or record.broker_order_id is None:
            raise HTTPException(404, f"unknown client_order_id: {client_order_id}")
        fill = Fill(
            fill_id=uuid4(),
            client_order_id=client_order_id,
            broker_order_id=record.broker_order_id,
            symbol=record.intent.symbol,
            side=record.intent.side
            if record.intent.side != Side.CLOSE
            else Side.SELL,
            qty=record.intent.qty,
            price=record.intent.price or Decimal("65000"),
            fees=Decimal("0"),
            at=clock.now(),
        )
        await fill_processor.on_fill(fill)
        return {"status": "fill_processed", "fill_id": str(fill.fill_id)}

    @tv_app.get("/test/state")
    async def test_state() -> dict[str, Any]:
        """別名為 /api/state；保留舊路徑相容。"""
        return _state_snapshot()

    def _build_strategies_snapshot() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for sid in registry.list_strategies():
            state = registry.get_state(sid)
            md = registry.get_strategy_metadata(sid)
            out.append({
                "strategy_id": sid,
                "state": state.value if state is not None else "UNKNOWN",
                "version": md.strategy_version if md is not None else None,
                "params_hash": md.params_hash if md is not None else None,
            })
        return out

    def _build_books_snapshot() -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        for sid in registry.list_strategies():
            book = registry.get_book(sid)
            out[sid] = [p.to_dict() for p in book.list_positions()] if book else []
        return out

    def _state_snapshot() -> dict[str, Any]:
        """系統狀態快照（dashboard / settings UI 共用）。"""
        from datetime import timezone as _tz
        from datetime import datetime as _dt
        return {
            "fsm_state": risk_gate.state.value,
            "started_at": getattr(_state_snapshot, "_started_at", None),
            "now": _dt.now(_tz.utc).isoformat(),
            "enabled_rules": [type(r).__name__ for r in risk_gate._engine._rules],
            "ledger": {
                "total_equity": str(ledger.total_equity),
                "total_reserved": str(ledger.total_reserved),
                "total_free": str(ledger.total_free),
            },
            "broker_orders": [
                {
                    "client_order_id": r.client_order_id,
                    "broker_order_id": r.broker_order_id,
                    "qty": str(r.intent.qty),
                    "symbol": r.intent.symbol,
                }
                for r in mock_broker.submitted
            ],
            "strategies": _build_strategies_snapshot(),
            "logical_books": _build_books_snapshot(),
            "reservation_bridge_mapping_size": bridge.mapping_size,
        }

    # ===== Dashboard / Settings UI =====
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    static_dir = PROJECT_ROOT / "static"
    if static_dir.exists():
        tv_app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @tv_app.get("/")
    async def dashboard_page() -> FileResponse:
        return FileResponse(static_dir / "dashboard.html")

    @tv_app.get("/settings")
    async def settings_page() -> FileResponse:
        return FileResponse(static_dir / "settings.html")

    # ===== JSON API =====
    @tv_app.get("/api/state")
    async def api_state() -> dict[str, Any]:
        return _state_snapshot()

    @tv_app.get("/api/config")
    async def api_config() -> dict[str, Any]:
        return risk_config.model_dump()

    @tv_app.post("/api/strategies/{strategy_id}/state")
    async def api_set_strategy_state(strategy_id: str, body: StrategyStateChange) -> dict[str, Any]:
        try:
            new_state = StrategyState(body.state)
        except ValueError as exc:
            raise HTTPException(400, f"invalid state: {body.state}") from exc
        try:
            registry.set_state(strategy_id, new_state)
        except KeyError as exc:
            raise HTTPException(404, f"unknown strategy: {strategy_id}") from exc
        return {"strategy_id": strategy_id, "state": new_state.value}

    @tv_app.post("/api/risk/reset")
    async def api_risk_reset() -> dict[str, Any]:
        result = await risk_gate.state_machine.reset()
        return {
            "ok": result.ok,
            "cooling_remaining_seconds": result.cooling_remaining_seconds,
            "message": result.message,
            "fsm_state": risk_gate.state.value,
        }

    @tv_app.post("/api/risk/maintenance")
    async def api_maintenance(body: MaintenanceAction) -> dict[str, Any]:
        if body.action == "enter":
            await risk_gate.state_machine.enter_maintenance()
        elif body.action == "exit":
            await risk_gate.state_machine.exit_maintenance()
        else:
            raise HTTPException(400, "action must be 'enter' or 'exit'")
        return {"fsm_state": risk_gate.state.value}

    @tv_app.post("/api/risk/tick")
    async def api_risk_tick(body: TickArgs) -> dict[str, Any]:
        await risk_gate.state_machine.tick(
            daily_pnl_ratio=body.daily_pnl_ratio,
            api_error_rate=body.api_error_rate,
        )
        return {"fsm_state": risk_gate.state.value}

    @tv_app.get("/api/audit")
    async def api_audit(limit: int = 50) -> list[dict[str, Any]]:
        if not audit_path.exists():
            return []
        lines = audit_path.read_text(encoding="utf-8").splitlines()[-limit:]
        out = []
        for line in lines:
            try:
                import json
                out.append(json.loads(line))
            except Exception:
                continue
        return out

    # ===== PnL / 多策略 / 圖表 =====
    from observability.pnl import PnLCalculator

    pnl_calc = PnLCalculator(registry=registry, market_data=market)

    # equity ring buffer（每 1 秒 sample 一次，最多保留 200 點）
    equity_buffer: list[dict[str, Any]] = []
    EQUITY_BUFFER_SIZE = 200

    @tv_app.get("/api/pnl")
    async def api_pnl() -> dict[str, Any]:
        snap = pnl_calc.account_pnl()
        return {
            "total_realized": str(snap.total_realized),
            "total_unrealized": str(snap.total_unrealized),
            "total_fees": str(snap.total_fees),
            "total_pnl": str(snap.total_pnl),
            "strategies": [
                {
                    "strategy_id": s.strategy_id,
                    "realized_pnl": str(s.realized_pnl),
                    "unrealized_pnl": str(s.unrealized_pnl),
                    "fees_paid": str(s.fees_paid),
                    "total_pnl": str(s.total_pnl),
                    "positions": [
                        {
                            "symbol": p.symbol,
                            "qty": str(p.qty),
                            "avg_entry": str(p.avg_entry),
                            "last_price": str(p.last_price),
                            "unrealized_pnl": str(p.unrealized_pnl),
                            "notional": str(p.notional),
                        }
                        for p in s.positions
                    ],
                }
                for s in snap.strategies
            ],
        }

    @tv_app.get("/api/equity-history")
    async def api_equity_history() -> list[dict[str, Any]]:
        return list(equity_buffer)

    @tv_app.get("/api/kline/{symbol}")
    async def api_kline(symbol: str) -> list[dict[str, Any]]:
        return market.candles(symbol)

    @tv_app.post("/api/strategies/register")
    async def api_register_strategy(body: StrategyCreate) -> dict[str, Any]:
        if registry.get_strategy(body.strategy_id) is not None:
            raise HTTPException(409, f"strategy already exists: {body.strategy_id}")
        params_hash = body.params_hash or f"ui_{uuid4().hex[:8]}"
        new_strategy = PassthroughStrategy(
            strategy_id=body.strategy_id,
            strategy_version=body.strategy_version,
            params_hash=params_hash,
        )
        registry.register(new_strategy)
        # 預設新策略為 LOADED；若希望立即接訊號，呼叫 set_state(ACTIVE)
        return {
            "strategy_id": body.strategy_id,
            "state": "LOADED",
            "version": body.strategy_version,
            "params_hash": params_hash,
        }

    @tv_app.post("/api/strategies/{strategy_id}/unregister")
    async def api_unregister_strategy(strategy_id: str) -> dict[str, Any]:
        ok = registry.unregister(strategy_id)
        if not ok:
            raise HTTPException(404, f"unknown strategy: {strategy_id}")
        return {"strategy_id": strategy_id, "removed": True}

    # 背景任務：每秒 snapshot equity + 推 K 線 candle
    async def _equity_sampler() -> None:
        while True:
            try:
                ts = clock.now().isoformat()
                snap = pnl_calc.account_pnl()
                equity_buffer.append({
                    "at": ts,
                    "total_equity": str(ledger.total_equity),
                    "total_reserved": str(ledger.total_reserved),
                    "total_pnl": str(snap.total_pnl),
                    "realized": str(snap.total_realized),
                    "unrealized": str(snap.total_unrealized),
                })
                if len(equity_buffer) > EQUITY_BUFFER_SIZE:
                    equity_buffer.pop(0)
                # 同步推 candle（demo K 線）
                for sym in ("BTCUSDT", "ETHUSDT"):
                    market.append_candle(sym, ts)
            except Exception:
                logger.exception("equity sampler failed")
            await asyncio.sleep(1.0)

    # 把 sampler task 掛到 tv_app 屬性上，由 _async_main 啟停
    tv_app.state.equity_sampler = _equity_sampler  # type: ignore[attr-defined]

    # 紀錄啟動時間（state snapshot 用）
    _state_snapshot._started_at = clock.now().isoformat()  # type: ignore[attr-defined]

    return tv_app, risk_gate, mock_broker


async def _async_main() -> None:
    app, risk_gate, mock_broker = build_app()
    secret = os.environ["VIBE_TV_SECRET"]

    # 啟動 RiskGate（含 reserver actor）
    await risk_gate.start()

    # 啟動背景 equity sampler
    sampler_coro = app.state.equity_sampler  # type: ignore[attr-defined]
    sampler_task = asyncio.create_task(sampler_coro())

    # banner
    print()
    print("=" * 70)
    print("  vibe-auto-trader webhook server")
    print("=" * 70)
    print(f"  Dashboard   : http://localhost:8000/")
    print(f"  Settings UI : http://localhost:8000/settings")
    print(f"  Webhook URL : http://localhost:8000/webhook/tv/{secret}/vibe_btc_v1")
    print("  Health      : http://localhost:8000/_health/health")
    print("  API state   : http://localhost:8000/api/state")
    print("  Broker      : MockExecutionAdapter（demo 用，非真交易所）")
    print()
    print("  測試 webhook（另一 terminal）：")
    print("    curl -X POST http://localhost:8000/webhook/tv/$VIBE_TV_SECRET/vibe_btc_v1 \\")
    print("      -H 'Content-Type: application/json' \\")
    print("      -d '{\"v\":1,\"strategy_id\":\"vibe_btc_v1\",\"symbol\":\"BTCUSDT\",")
    print("           \"side\":\"BUY\",\"qty\":\"0.1\",\"price\":\"65000\",")
    print("           \"bar_time\":\"2026-05-10T12:00:00+00:00\",\"interval\":\"60\",\"comment\":null}'")
    print()
    print("  模擬交易所回報 fill（用 webhook 的 client_order_id）：")
    print("    curl -X POST http://localhost:8000/test/fill/<client_order_id>")
    print()
    print("  Ctrl+C 結束")
    print("=" * 70)
    print()

    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info", lifespan="off")
    server = uvicorn.Server(config)

    # 優雅停機：SIGINT/SIGTERM
    loop = asyncio.get_running_loop()

    def _shutdown() -> None:
        logger.info("shutdown signal received")
        server.should_exit = True

    for sig_name in ("SIGINT", "SIGTERM"):
        try:
            loop.add_signal_handler(getattr(signal, sig_name), _shutdown)
        except NotImplementedError:
            # Windows 不支援
            pass

    try:
        await server.serve()
    finally:
        logger.info("shutting down RiskGate...")
        sampler_task.cancel()
        try:
            await sampler_task
        except (asyncio.CancelledError, Exception):
            pass
        await risk_gate.shutdown()
        logger.info("server stopped. Mock broker submitted %d order(s)", len(mock_broker.submitted))


def main() -> None:
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
