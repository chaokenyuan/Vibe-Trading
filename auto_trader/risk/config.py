"""風控閘 YAML 配置 pydantic v2 模型。

對應 spec：「配置以 YAML 表達且啟動時驗證」。
配置變更 SHALL 在重啟後生效（D4 凍結，不支援熱載入）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class FsmThresholds(BaseModel):
    """FSM 觸發閾值（自動轉換邏輯依據）。

    PnL 為負值（虧損），表達為 -0.02 = -2%。
    """

    model_config = ConfigDict(extra="forbid")

    daily_pnl_warning: float = Field(..., description="進入 WARNING 的日內 PnL 上界")
    daily_pnl_throttled: float = Field(..., description="進入 THROTTLED 的日內 PnL 上界")
    daily_pnl_halted: float = Field(..., description="進入 HALTED 的日內 PnL 上界")
    daily_pnl_kill: float = Field(..., description="進入 KILL_SWITCH 的日內 PnL 上界")
    api_error_rate_throttled: float = Field(..., ge=0, le=1)
    kill_switch_cooling_seconds: int = Field(..., ge=0, description="KILL_SWITCH 冷靜期")


class FsmConfig(BaseModel):
    """FSM 整體配置。"""

    model_config = ConfigDict(extra="forbid")

    thresholds: FsmThresholds
    tick_interval_seconds: int = Field(default=60, ge=1)


class ClockConfig(BaseModel):
    """Clock / 跨日 P&L 重置配置。"""

    model_config = ConfigDict(extra="forbid")

    tz: str = Field(default="UTC", description="跨日重置時區")


class WarmingUpConfig(BaseModel):
    """啟動暖機期配置。"""

    model_config = ConfigDict(extra="forbid")

    duration_seconds: int = Field(default=30, ge=0)


class RuleParams(BaseModel):
    """規則參數集：key 為規則名稱，value 為該規則的參數 dict。

    使用 extra="allow" 接受任意規則名稱作為動態欄位，方便新增規則時
    無需修改本模型；具體規則於建構時從 for_rule(name) 取參數。
    """

    model_config = ConfigDict(extra="allow")

    def for_rule(self, rule_name: str) -> dict[str, Any]:
        """取得指定規則的參數 dict；不存在回傳空 dict。"""
        dumped = self.model_dump()
        value = dumped.get(rule_name, {})
        if not isinstance(value, dict):
            return {}
        return value


class RulesConfig(BaseModel):
    """規則集合配置。"""

    model_config = ConfigDict(extra="forbid")

    enabled: list[str] = Field(..., description="啟用的規則名稱清單，順序即執行順序")
    params: RuleParams = Field(default_factory=RuleParams)


class RiskConfig(BaseModel):
    """風控閘總配置。對外進入點：from_yaml(path)。"""

    model_config = ConfigDict(extra="forbid")

    fsm: FsmConfig
    clock: ClockConfig = Field(default_factory=ClockConfig)
    warming_up: WarmingUpConfig = Field(default_factory=WarmingUpConfig)
    rules: RulesConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> RiskConfig:
        """從 YAML 檔載入並驗證；驗證失敗 raise pydantic.ValidationError。

        Args:
            path: YAML 配置檔路徑。

        Raises:
            FileNotFoundError: 路徑不存在。
            pydantic.ValidationError: 配置不符合 schema（缺欄位/型別錯/額外欄位）。
            yaml.YAMLError: YAML 語法錯誤。
        """
        p = Path(path)
        with p.open(encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        if not isinstance(raw, dict):
            raise ValueError(f"YAML 根層必須為 mapping，實際為 {type(raw).__name__}: {path}")
        return cls.model_validate(raw)

    def params_hash(self) -> str:
        """配置內容 SHA-256，供啟動審計與後續每筆 Decision 攜帶。

        以 sort_keys + 緊湊分隔符序列化確保確定性
        （同內容必同 hash，欄位順序不影響）。
        """
        canonical = json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
