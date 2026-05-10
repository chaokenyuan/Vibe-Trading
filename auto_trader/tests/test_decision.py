"""Decision 與 RuleVerdict 序列化與不可變性測試。

對應 spec scenario：
- Decision 序列化：to_dict 結果可被 json.dumps 完整序列化
- Decision 不可變：FrozenInstanceError
"""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from risk.decision import Decision, Outcome, RuleVerdict, Verdict


def test_rule_verdict_immutable() -> None:
    rv = RuleVerdict(
        rule_name="SystemStateRule",
        outcome=Outcome.PASS,
        before_value=Decimal("10"),
        after_value=Decimal("10"),
        message="ok",
    )
    with pytest.raises(FrozenInstanceError):
        rv.message = "changed"  # type: ignore[misc]


def test_decision_immutable() -> None:
    d = Decision(
        verdict=Verdict.APPROVE,
        final_size=Decimal("5"),
        final_price=None,
        reasons=[],
        reservation_id=None,
        evaluated_at=datetime(2026, 5, 10, tzinfo=UTC),
    )
    with pytest.raises(FrozenInstanceError):
        d.final_size = Decimal("10")  # type: ignore[misc]


def test_decision_to_dict_json_serializable() -> None:
    rv = RuleVerdict(
        rule_name="SystemStateRule",
        outcome=Outcome.CLAMP,
        before_value=Decimal("10"),
        after_value=Decimal("5"),
        message="throttled",
        metadata={"key": "value"},
    )
    d = Decision(
        verdict=Verdict.APPROVE,
        final_size=Decimal("5"),
        final_price=Decimal("65000.50"),
        reasons=[rv],
        reservation_id=UUID("00000000-0000-0000-0000-000000000001"),
        evaluated_at=datetime(2026, 5, 10, 12, 0, 0, tzinfo=UTC),
    )

    payload = d.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["verdict"] == "APPROVE"
    assert decoded["final_size"] == "5"
    assert decoded["final_price"] == "65000.50"
    assert decoded["reservation_id"] == "00000000-0000-0000-0000-000000000001"
    assert decoded["evaluated_at"] == "2026-05-10T12:00:00+00:00"
    assert decoded["reasons"][0]["rule_name"] == "SystemStateRule"
    assert decoded["reasons"][0]["outcome"] == "CLAMP"
    assert decoded["reasons"][0]["before_value"] == "10"
    assert decoded["reasons"][0]["after_value"] == "5"
    assert decoded["reasons"][0]["metadata"] == {"key": "value"}


def test_decision_to_dict_handles_none_values() -> None:
    d = Decision(
        verdict=Verdict.REJECT,
        final_size=Decimal("0"),
        final_price=None,
        reasons=[],
        reservation_id=None,
        evaluated_at=datetime(2026, 5, 10, tzinfo=UTC),
    )

    payload = d.to_dict()
    encoded = json.dumps(payload)
    decoded = json.loads(encoded)

    assert decoded["final_price"] is None
    assert decoded["reservation_id"] is None
    assert decoded["reasons"] == []


def test_rule_verdict_metadata_default_empty() -> None:
    rv = RuleVerdict(
        rule_name="X",
        outcome=Outcome.PASS,
        before_value=None,
        after_value=None,
        message="",
    )
    assert rv.metadata == {}


def test_rule_verdict_metadata_isolated_per_instance() -> None:
    """確保 default_factory 不被多實例共用。"""
    rv1 = RuleVerdict(
        rule_name="A",
        outcome=Outcome.PASS,
        before_value=None,
        after_value=None,
        message="",
    )
    rv2 = RuleVerdict(
        rule_name="B",
        outcome=Outcome.PASS,
        before_value=None,
        after_value=None,
        message="",
    )
    assert rv1.metadata is not rv2.metadata


def test_verdict_str_enum_values() -> None:
    assert Verdict.APPROVE.value == "APPROVE"
    assert Verdict.REJECT.value == "REJECT"
    assert Verdict.DEFER.value == "DEFER"


def test_outcome_str_enum_values() -> None:
    assert Outcome.PASS.value == "PASS"
    assert Outcome.CLAMP.value == "CLAMP"
    assert Outcome.REJECT.value == "REJECT"
