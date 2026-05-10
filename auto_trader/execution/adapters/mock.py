"""MockExecutionAdapter：測試與 dry-run 用。

預設成功模式：每次 submit 回傳遞增 broker_order_id。
fail_next toggle 啟用後下一次 submit 拋例外。
紀錄所有 submit / cancel 呼叫供測試斷言。
"""

from __future__ import annotations

from dataclasses import dataclass

from risk.types import OrderIntent


@dataclass
class _SubmitRecord:
    intent: OrderIntent
    client_order_id: str
    broker_order_id: str | None
    error: str | None


class MockExecutionAdapter:
    """測試替身 ExecutionAdapter；結構符合 ExecutionAdapter Protocol。"""

    def __init__(self) -> None:
        self.submitted: list[_SubmitRecord] = []
        self.canceled: list[str] = []
        self.fail_next: bool = False
        self._counter: int = 0

    async def submit(
        self,
        *,
        intent: OrderIntent,
        client_order_id: str,
    ) -> str:
        if self.fail_next:
            self.fail_next = False
            self.submitted.append(
                _SubmitRecord(
                    intent=intent,
                    client_order_id=client_order_id,
                    broker_order_id=None,
                    error="fail_next set",
                )
            )
            raise RuntimeError("MockExecutionAdapter intentional failure")

        self._counter += 1
        broker_order_id = f"mock-{self._counter}"
        self.submitted.append(
            _SubmitRecord(
                intent=intent,
                client_order_id=client_order_id,
                broker_order_id=broker_order_id,
                error=None,
            )
        )
        return broker_order_id

    async def cancel(self, broker_order_id: str) -> None:
        self.canceled.append(broker_order_id)
