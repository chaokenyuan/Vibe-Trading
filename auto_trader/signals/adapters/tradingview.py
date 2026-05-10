"""TradingViewWebhookAdapter：FastAPI POST /webhook/tv/{secret}/{strategy_id}。

對應 spec：「TradingViewWebhookAdapter 認證採 URL secret + IP 白名單」、
       「TradingView alert message 解析為 canonical Signal」。

部署時：deployment 層應在 reverse proxy 強制 https；本 adapter 不負責 TLS。
測試時：使用 httpx.ASGITransport 直接打 app，不啟 uvicorn。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, cast

from fastapi import FastAPI, HTTPException, Request, status

from signals.auth import verify_ip, verify_secret
from signals.config import TradingViewConfig
from signals.router import SignalRouter
from signals.types import SCHEMA_VERSION_CURRENT, SignalSourceKind


class TradingViewWebhookAdapter:
    """TradingView Webhook adapter。

    本身的 start/stop 為 no-op；FastAPI app 由 create_tradingview_app factory 建構。
    結構性符合 SignalSource Protocol。
    """

    async def start(self) -> None:
        """no-op：實際路由註冊在 create_tradingview_app 完成。"""

    async def stop(self) -> None:
        """no-op。"""

    @staticmethod
    def parse_payload(raw: dict[str, Any]) -> dict[str, Any]:
        """把 TV alert message 的 raw dict 轉為 ingest 參數。

        驗證 schema_version、必填欄位、Decimal 解析。
        失敗時 raise ValueError（呼叫端轉成 422）。
        """
        version = raw.get("v")
        if version != SCHEMA_VERSION_CURRENT:
            raise ValueError(f"unsupported schema_version: {version}")

        required = ["strategy_id", "symbol", "side", "qty", "bar_time", "interval"]
        missing = [k for k in required if k not in raw]
        if missing:
            raise ValueError(f"missing fields: {missing}")

        side_val = raw["side"]
        if side_val not in ("BUY", "SELL", "CLOSE"):
            raise ValueError(f"invalid side: {side_val}")

        try:
            qty = Decimal(str(raw["qty"]))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError(f"invalid qty: {raw['qty']}") from exc

        price_raw = raw.get("price")
        price: Decimal | None
        if price_raw is None or price_raw == "":
            price = None
        else:
            try:
                price = Decimal(str(price_raw))
            except (InvalidOperation, TypeError) as exc:
                raise ValueError(f"invalid price: {price_raw}") from exc

        try:
            bar_time = datetime.fromisoformat(str(raw["bar_time"]))
        except ValueError as exc:
            raise ValueError(f"invalid bar_time: {raw['bar_time']}") from exc

        return {
            "strategy_id": str(raw["strategy_id"]),
            "symbol": str(raw["symbol"]),
            "side": cast(Literal["BUY", "SELL", "CLOSE"], side_val),
            "qty": qty,
            "price": price,
            "bar_time": bar_time,
            "interval": str(raw["interval"]),
            "comment": raw.get("comment"),
        }


def create_tradingview_app(
    *,
    adapter: TradingViewWebhookAdapter,
    router: SignalRouter,
    config: TradingViewConfig,
) -> FastAPI:
    """建構 TradingView Webhook FastAPI app。

    註冊路由：POST /webhook/tv/{secret}/{strategy_id}

    認證流程：
    1. URL secret constant-time 比對
    2. client IP 白名單比對
    3. JSON parse 失敗 → 422
    4. 任一認證失敗 → 401（不洩漏細節）
    """
    app = FastAPI(title="vibe-auto-trader signal-ingestion (TradingView)")

    @app.post("/webhook/tv/{secret}/{strategy_id}")
    async def webhook(
        secret: str,
        strategy_id: str,
        request: Request,
    ) -> dict[str, Any]:
        # 認證
        if not verify_secret(secret, config.secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )

        client_host = request.client.host if request.client is not None else ""
        if not verify_ip(client_host, config.allowed_ips):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="unauthorized",
            )

        # JSON 解析
        try:
            raw = await request.json()
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"invalid json: {exc}",
            ) from exc

        if not isinstance(raw, dict):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="payload must be json object",
            )

        # URL strategy_id 必須與 payload 一致（防止 secret 被多策略共用時誤路由）
        payload_strategy_id = raw.get("strategy_id")
        if payload_strategy_id != strategy_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="strategy_id mismatch between url and payload",
            )

        # parse + ingest
        try:
            parsed = adapter.parse_payload(raw)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

        signal = await router.ingest(
            **parsed,
            source=SignalSourceKind.TRADINGVIEW,
            raw_payload=raw,
        )

        if signal is None:
            return {"status": "rejected"}
        return {"status": "accepted", "signal_id": signal.signal_id}

    return app
