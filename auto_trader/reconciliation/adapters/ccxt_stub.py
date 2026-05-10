"""CcxtFillSource stub：訂閱 ccxt WebSocket 取得交易所 fill。

用途：訂閱交易所的成交回報串流（WebSocket）。
輸入：建構參數含 exchange / API key / testnet flag、callback。
輸出：交易所 fill 透過 callback 推送（每筆轉為標準 Fill）。
配置：與 execution.yaml 共用 broker 設定。
實作策略：
  - 使用 ccxt.async_support 對應 exchange
  - 啟動 task 訂閱 watch_my_trades / watch_orders
  - 每筆 ws message 轉為 strategies.types.Fill
  - 異常重連邏輯（指數退避）
本 change 為 stub，凍結介面；具體實作交由後續 change（依部署交易所）。
"""

from __future__ import annotations

from reconciliation.ports import FillCallback

_NOT_IMPLEMENTED_MSG = (
    "CcxtFillSource not implemented in add-reconciliation change; "
    "see openspec/changes/<future-change>"
)


class CcxtFillSource:
    """ccxt WebSocket 訂閱 stub；結構符合 FillSource Protocol。"""

    def __init__(
        self,
        *,
        callback: FillCallback,
        exchange: str = "binance",
        testnet: bool = True,
    ) -> None:
        self._callback = callback
        self._exchange = exchange
        self._testnet = testnet

    async def start(self) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)

    async def stop(self) -> None:
        raise NotImplementedError(_NOT_IMPLEMENTED_MSG)
