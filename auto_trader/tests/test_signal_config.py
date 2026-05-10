"""SignalIngestionConfig 測試。"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from signals.config import DEFAULT_TV_IPS, SignalIngestionConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_YAML = PROJECT_ROOT / "config" / "signal_ingestion.yaml"


def _valid_data() -> dict[str, object]:
    return {
        "tradingview": {
            "secret": "abcdefgh12345678",
            "allowed_ips": ["1.2.3.4"],
        },
        "dedupe": {"ttl_seconds": 300, "max_entries": 100000},
        "webhook": {"rate_limit_per_second": 10},
        "scanner": {"schedule": "0 0 * * *"},
    }


def _write(tmp_path: Path, data: dict[str, object]) -> Path:
    p = tmp_path / "signal.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_default_yaml_loads() -> None:
    """專案預設 config/signal_ingestion.yaml 必須能 schema-load。"""
    cfg = SignalIngestionConfig.from_yaml(DEFAULT_YAML)
    assert cfg.dedupe.ttl_seconds == 300
    assert len(cfg.tradingview.allowed_ips) == 4


def test_minimal_valid_config(tmp_path: Path) -> None:
    p = _write(tmp_path, _valid_data())
    cfg = SignalIngestionConfig.from_yaml(p)
    assert cfg.tradingview.secret == "abcdefgh12345678"


def test_missing_secret_raises(tmp_path: Path) -> None:
    """spec scenario：缺 secret 阻止啟動。"""
    data = _valid_data()
    tv = data["tradingview"]
    assert isinstance(tv, dict)
    del tv["secret"]
    p = _write(tmp_path, data)
    with pytest.raises(ValidationError):
        SignalIngestionConfig.from_yaml(p)


def test_short_secret_rejected(tmp_path: Path) -> None:
    data = _valid_data()
    tv = data["tradingview"]
    assert isinstance(tv, dict)
    tv["secret"] = "short"
    p = _write(tmp_path, data)
    with pytest.raises(ValidationError):
        SignalIngestionConfig.from_yaml(p)


def test_default_allowed_ips_uses_tv_official(tmp_path: Path) -> None:
    """spec scenario：預設 allowed_ips 包含 TV 官方 IP。"""
    data = _valid_data()
    tv = data["tradingview"]
    assert isinstance(tv, dict)
    del tv["allowed_ips"]
    p = _write(tmp_path, data)
    cfg = SignalIngestionConfig.from_yaml(p)
    assert cfg.tradingview.allowed_ips == DEFAULT_TV_IPS


def test_extra_field_rejected(tmp_path: Path) -> None:
    data = _valid_data()
    data["extra_section"] = {"x": 1}
    p = _write(tmp_path, data)
    with pytest.raises(ValidationError):
        SignalIngestionConfig.from_yaml(p)


def test_yaml_root_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        SignalIngestionConfig.from_yaml(p)
