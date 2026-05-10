"""SignalIngestionConfig：YAML 配置 pydantic v2 模型。

對應 spec：「配置以 YAML 表達且啟動時驗證」。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

# TradingView 官方 webhook 來源 IP（截至 2026 年；變動時請更新）
DEFAULT_TV_IPS = [
    "52.89.214.238",
    "34.212.75.30",
    "54.218.53.128",
    "52.32.178.7",
]


class TradingViewConfig(BaseModel):
    """TradingView Webhook adapter 配置。"""

    model_config = ConfigDict(extra="forbid")

    secret: str = Field(..., min_length=8, description="URL secret token")
    allowed_ips: list[str] = Field(
        default_factory=lambda: list(DEFAULT_TV_IPS),
        description="允許的 client IP 清單；空清單代表全部接受（測試用）",
    )


class DedupeConfig(BaseModel):
    """SignalDedupe 配置。"""

    model_config = ConfigDict(extra="forbid")

    ttl_seconds: int = Field(default=300, ge=1)
    max_entries: int = Field(default=100_000, ge=1)


class WebhookConfig(BaseModel):
    """Webhook 服務配置。"""

    model_config = ConfigDict(extra="forbid")

    rate_limit_per_second: int = Field(default=10, ge=1)


class ScannerConfig(BaseModel):
    """VibeShadowScannerAdapter 配置（stub 不使用）。"""

    model_config = ConfigDict(extra="forbid")

    schedule: str = Field(default="0 0 * * *")


class SignalIngestionConfig(BaseModel):
    """signal-ingestion 整體配置。"""

    model_config = ConfigDict(extra="forbid")

    tradingview: TradingViewConfig
    dedupe: DedupeConfig = Field(default_factory=DedupeConfig)
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)
    scanner: ScannerConfig = Field(default_factory=ScannerConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> SignalIngestionConfig:
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"YAML 根層必須為 mapping: {path}")
        return cls.model_validate(raw)
