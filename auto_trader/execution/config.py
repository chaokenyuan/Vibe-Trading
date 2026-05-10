"""ExecutionConfig：YAML 配置 pydantic 模型。"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ExecutionConfig(BaseModel):
    """訂單執行層配置。"""

    model_config = ConfigDict(extra="forbid")

    broker: str = Field(default="mock", description="broker 名稱：mock / binance / okx 等")
    testnet: bool = Field(default=True, description="是否使用測試網")
    api_key_env: str = Field(
        default="VIBE_BROKER_API_KEY",
        description="API key 的環境變數名稱（不直接寫入配置）",
    )
    api_secret_env: str = Field(default="VIBE_BROKER_API_SECRET")

    @classmethod
    def from_yaml(cls, path: str | Path) -> ExecutionConfig:
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"YAML 根層必須為 mapping: {path}")
        return cls.model_validate(raw)
