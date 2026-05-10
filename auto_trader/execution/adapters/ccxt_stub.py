"""CcxtExecutionAdapter stub。

用途：以 ccxt SDK 對接 100+ 交易所。
輸入：建構參數（exchange name、API key、testnet flag）；submit 接 OrderIntent + client_order_id。
輸出：交易所 broker_order_id。
配置：execution.yaml 的 broker 區段（後續定義）。
實作策略：
  - import ccxt.async_support 對應 exchange
  - submit 內部 map OrderIntent → exchange.create_order 參數
  - testnet 模式切換 exchange URL
  - 錯誤碼 mapping 為標準例外
本 change 為 stub，凍結介面；具體實作交由後續 change（依部署交易所）。
"""

from __future__ import annotations

from risk.types import OrderIntent

_NOT_IMPLEMENTED_MSG = (
    "CcxtExecutionAdapter not implemented in add-order-execution change; "
    "see openspec/changes/<future-change>"
)


class CcxtExecutionAdapter:
    """ccxt 整合 stub；結構符合 ExecutionAdapter Protocol。"""

    def __init__(
        self,
        *,
        exchange: str = "binance",
        testnet: bool = True,
    ) -> None:
        self._exchange = exchange
        self._testnet = testnet

    async def submit(
        self,
        *,
        intent: OrderIntent,
        client_order_id: str,
    ) -> str:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def cancel(self, broker_order_id: str) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
