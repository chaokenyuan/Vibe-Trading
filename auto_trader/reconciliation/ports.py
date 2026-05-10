"""FillSource Protocol：訂閱交易所 Fill 串流的抽象。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable

from strategies.types import Fill

FillCallback = Callable[[Fill], Awaitable[None]]


@runtime_checkable
class FillSource(Protocol):
    """Fill 來源 adapter（push 模式）。

    建構時注入 FillCallback；adapter 收到交易所 fill 後呼叫 callback。
    """

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
