"""ObservabilityConfig：YAML 配置 pydantic 模型。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AuditLogConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    path: str = Field(default="logs/audit.jsonl", description="JSON Lines 輸出路徑")


class TelegramConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    bot_token_env: str = Field(default="VIBE_TELEGRAM_BOT_TOKEN")
    chat_id_env: str = Field(default="VIBE_TELEGRAM_CHAT_ID")


class HealthConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_name: str = "vibe-auto-trader"
    version: str = "0.0.1"


class ObservabilityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_log: AuditLogConfig = Field(default_factory=AuditLogConfig)
    telegram: TelegramConfig = Field(default_factory=TelegramConfig)
    health: HealthConfig = Field(default_factory=HealthConfig)

    @classmethod
    def from_yaml(cls, path: str | Path) -> ObservabilityConfig:
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"YAML 根層必須為 mapping: {path}")
        return cls.model_validate(raw)
