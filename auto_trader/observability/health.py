"""HealthEndpoint：FastAPI 提供 /health 與 /readyz 端點。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from fastapi import FastAPI

from risk.ports import Clock


def create_health_app(
    *,
    clock: Clock,
    service_name: str = "vibe-auto-trader",
    version: str = "0.0.1",
    is_ready: Callable[[], bool] | None = None,
) -> FastAPI:
    """建構含 /health 與 /readyz 的 FastAPI app。

    is_ready: 可選的就緒回呼；None 代表永遠 ready。
    """
    app = FastAPI(title=f"{service_name} health")
    started_at = clock.now()

    @app.get("/health")
    async def health() -> dict[str, Any]:
        now = clock.now()
        return {
            "status": "ok",
            "service": service_name,
            "version": version,
            "started_at": started_at.isoformat(),
            "now": now.isoformat(),
        }

    @app.get("/readyz")
    async def readyz() -> dict[str, Any]:
        ready = True if is_ready is None else is_ready()
        if not ready:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="not ready",
            )
        return {"ready": True}

    return app


def _signal_started_at_used(_: datetime) -> None:
    """避免 datetime 未使用警告（type hint 用途）。"""
    return None
