"""SymbolWhitelistRule：限制可交易標的。"""

from __future__ import annotations

from collections.abc import Iterable

from risk.decision import Outcome, RuleVerdict
from risk.rules.base import RuleContext


class SymbolWhitelistRule:
    """空清單接受全部；非空僅接受清單內 symbol。"""

    name = "SymbolWhitelistRule"

    def __init__(self, *, symbols: Iterable[str] = ()) -> None:
        self._symbols = frozenset(symbols)

    def evaluate(self, ctx: RuleContext) -> RuleVerdict:
        if not self._symbols:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message="empty whitelist (accept all)",
            )
        if ctx.intent.symbol in self._symbols:
            return RuleVerdict(
                rule_name=self.name,
                outcome=Outcome.PASS,
                before_value=ctx.current_size,
                after_value=ctx.current_size,
                message=f"symbol {ctx.intent.symbol} in whitelist",
            )
        return RuleVerdict(
            rule_name=self.name,
            outcome=Outcome.REJECT,
            before_value=ctx.current_size,
            after_value=None,
            message=f"symbol {ctx.intent.symbol} not in whitelist",
            metadata={"symbol": ctx.intent.symbol},
        )
