"""Decision 與 RuleVerdict 不可變值物件。

對應 spec：「Decision 與 RuleVerdict 為不可變值物件」。
所有風控閘判決 SHALL 透過 Decision 表達；每條規則的判斷 SHALL 透過 RuleVerdict 累積至 Decision.reasons。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from risk._serialize import to_json_safe


class Verdict(StrEnum):
    """Decision 的最終判決類型。"""

    APPROVE = "APPROVE"
    REJECT = "REJECT"
    DEFER = "DEFER"


class Outcome(StrEnum):
    """單條規則對某筆 OrderIntent 的回傳結果。"""

    PASS = "PASS"
    CLAMP = "CLAMP"
    REJECT = "REJECT"


@dataclass(frozen=True, kw_only=True)
class RuleVerdict:
    """單條規則的判斷紀錄。

    metadata 為彈性擴充欄位，未來新增資訊優先放此處避免破壞契約簽名。
    """

    rule_name: str
    outcome: Outcome
    before_value: Decimal | None
    after_value: Decimal | None
    message: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, kw_only=True)
class Decision:
    """RuleEngine 對單筆 OrderIntent 的最終判決。

    reservation_id 僅在 verdict=APPROVE 時非空。
    evaluated_at 來自注入的 Clock，不直接呼叫 datetime.now()。
    """

    verdict: Verdict
    final_size: Decimal
    final_price: Decimal | None
    reasons: list[RuleVerdict]
    reservation_id: UUID | None
    evaluated_at: datetime

    def to_dict(self) -> dict[str, Any]:
        """序列化為純資料 dict，可直接被 json.dumps 接受。"""
        return cast(dict[str, Any], to_json_safe(asdict(self)))
