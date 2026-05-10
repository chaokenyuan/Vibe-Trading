"""RiskConfig YAML 載入、驗證、params_hash 確定性測試。

對應 spec scenario：
- 啟動時配置驗證成功
- 配置缺欄位阻止啟動
- 配置型別錯誤阻止啟動
- params_hash 確定性與內容敏感性
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from risk.config import RiskConfig

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "risk.yaml"


def _write_yaml(tmp_path: Path, data: dict[str, object], name: str = "risk.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p


def _valid_data() -> dict[str, object]:
    return {
        "fsm": {
            "thresholds": {
                "daily_pnl_warning": -0.02,
                "daily_pnl_throttled": -0.03,
                "daily_pnl_halted": -0.05,
                "daily_pnl_kill": -0.07,
                "api_error_rate_throttled": 0.05,
                "kill_switch_cooling_seconds": 14400,
            },
            "tick_interval_seconds": 60,
        },
        "clock": {"tz": "UTC"},
        "warming_up": {"duration_seconds": 30},
        "rules": {
            "enabled": ["SystemStateRule", "IdempotencyRule"],
            "params": {
                "IdempotencyRule": {"ttl_seconds": 300, "max_entries": 100000},
            },
        },
    }


# ===== 合法配置載入 =====


def test_default_config_yaml_loads_successfully() -> None:
    """專案預設 config/risk.yaml 必須能成功載入。"""
    cfg = RiskConfig.from_yaml(DEFAULT_CONFIG)
    assert cfg.fsm.thresholds.daily_pnl_kill == -0.07
    assert cfg.warming_up.duration_seconds == 30
    assert "SystemStateRule" in cfg.rules.enabled


def test_minimal_valid_config_loads(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, _valid_data())
    cfg = RiskConfig.from_yaml(p)
    assert cfg.fsm.tick_interval_seconds == 60


def test_clock_default_when_omitted(tmp_path: Path) -> None:
    data = _valid_data()
    del data["clock"]
    p = _write_yaml(tmp_path, data)
    cfg = RiskConfig.from_yaml(p)
    assert cfg.clock.tz == "UTC"


def test_warming_up_default_when_omitted(tmp_path: Path) -> None:
    data = _valid_data()
    del data["warming_up"]
    p = _write_yaml(tmp_path, data)
    cfg = RiskConfig.from_yaml(p)
    assert cfg.warming_up.duration_seconds == 30


# ===== 缺欄位失敗 =====


def test_missing_fsm_thresholds_field_raises(tmp_path: Path) -> None:
    """spec scenario：缺 fsm.thresholds.daily_pnl_kill 阻止啟動。"""
    data = _valid_data()
    fsm = data["fsm"]
    assert isinstance(fsm, dict)
    thresholds = fsm["thresholds"]
    assert isinstance(thresholds, dict)
    del thresholds["daily_pnl_kill"]
    p = _write_yaml(tmp_path, data)

    with pytest.raises(ValidationError) as exc_info:
        RiskConfig.from_yaml(p)

    err_str = str(exc_info.value)
    assert "daily_pnl_kill" in err_str


def test_missing_rules_enabled_raises(tmp_path: Path) -> None:
    data = _valid_data()
    rules = data["rules"]
    assert isinstance(rules, dict)
    del rules["enabled"]
    p = _write_yaml(tmp_path, data)
    with pytest.raises(ValidationError):
        RiskConfig.from_yaml(p)


# ===== 型別錯誤失敗 =====


def test_wrong_type_daily_pnl_kill_raises(tmp_path: Path) -> None:
    """spec scenario：型別錯誤阻止啟動。"""
    data = _valid_data()
    fsm = data["fsm"]
    assert isinstance(fsm, dict)
    thresholds = fsm["thresholds"]
    assert isinstance(thresholds, dict)
    thresholds["daily_pnl_kill"] = "not_a_number"
    p = _write_yaml(tmp_path, data)

    with pytest.raises(ValidationError) as exc_info:
        RiskConfig.from_yaml(p)

    err_str = str(exc_info.value)
    assert "daily_pnl_kill" in err_str


def test_negative_kill_switch_cooling_seconds_raises(tmp_path: Path) -> None:
    data = _valid_data()
    fsm = data["fsm"]
    assert isinstance(fsm, dict)
    thresholds = fsm["thresholds"]
    assert isinstance(thresholds, dict)
    thresholds["kill_switch_cooling_seconds"] = -100
    p = _write_yaml(tmp_path, data)
    with pytest.raises(ValidationError):
        RiskConfig.from_yaml(p)


def test_extra_field_rejected(tmp_path: Path) -> None:
    """extra='forbid' 確保 typo 不被默默忽略。"""
    data = _valid_data()
    data["unknown_section"] = {"foo": "bar"}
    p = _write_yaml(tmp_path, data)
    with pytest.raises(ValidationError):
        RiskConfig.from_yaml(p)


# ===== 異常路徑 =====


def test_file_not_found_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        RiskConfig.from_yaml(tmp_path / "nonexistent.yaml")


def test_yaml_root_must_be_mapping(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ValueError, match="mapping"):
        RiskConfig.from_yaml(p)


# ===== params_hash 確定性 =====


def test_params_hash_is_deterministic(tmp_path: Path) -> None:
    p1 = _write_yaml(tmp_path, _valid_data(), "a.yaml")
    p2 = _write_yaml(tmp_path, _valid_data(), "b.yaml")
    cfg1 = RiskConfig.from_yaml(p1)
    cfg2 = RiskConfig.from_yaml(p2)
    assert cfg1.params_hash() == cfg2.params_hash()


def test_params_hash_changes_with_content(tmp_path: Path) -> None:
    base = _valid_data()
    p1 = _write_yaml(tmp_path, base, "a.yaml")

    modified = _valid_data()
    fsm = modified["fsm"]
    assert isinstance(fsm, dict)
    thresholds = fsm["thresholds"]
    assert isinstance(thresholds, dict)
    thresholds["daily_pnl_kill"] = -0.08
    p2 = _write_yaml(tmp_path, modified, "b.yaml")

    cfg1 = RiskConfig.from_yaml(p1)
    cfg2 = RiskConfig.from_yaml(p2)
    assert cfg1.params_hash() != cfg2.params_hash()


def test_params_hash_independent_of_yaml_key_order(tmp_path: Path) -> None:
    """同內容、key 順序不同 → 同 hash。"""
    base = _valid_data()
    p1 = _write_yaml(tmp_path, base, "a.yaml")

    # 重新組合產生 key 順序不同的 dict
    reordered = dict(reversed(list(base.items())))
    p2 = _write_yaml(tmp_path, reordered, "b.yaml")

    cfg1 = RiskConfig.from_yaml(p1)
    cfg2 = RiskConfig.from_yaml(p2)
    assert cfg1.params_hash() == cfg2.params_hash()


# ===== RuleParams 取參數 =====


def test_rule_params_for_rule_returns_dict(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, _valid_data())
    cfg = RiskConfig.from_yaml(p)
    idempotency_params = cfg.rules.params.for_rule("IdempotencyRule")
    assert idempotency_params == {"ttl_seconds": 300, "max_entries": 100000}


def test_rule_params_for_rule_unknown_returns_empty(tmp_path: Path) -> None:
    p = _write_yaml(tmp_path, _valid_data())
    cfg = RiskConfig.from_yaml(p)
    assert cfg.rules.params.for_rule("UnknownRule") == {}
