"""未實作 SignalSource adapter 的契約 stub。

對應 spec：「VibeShadowScannerAdapter 與 Mt5HttpPushAdapter 為 stub」。
本 change 僅凍結介面，呼叫 start() 即拋 NotImplementedError；
具體實作交由後續 change（依 design-brief 第 5 節定義）。
"""

from __future__ import annotations

_NOT_IMPLEMENTED_MSG = (
    "{name} not implemented in add-signal-ingestion change; "
    "see openspec/changes/<future-change>"
)


class VibeShadowScannerAdapter:
    """Vibe-Trading shadow_account.scan_today_signals 拉取 adapter。

    用途：每日依 cron schedule 呼叫 Vibe-Trading MCP `scan_shadow_signals`
        工具或直接 import `src.shadow_account.scanner.scan_today_signals`，
        把研究級候選清單轉為 Signal 並推 router。

    輸入：cron schedule（從 SignalIngestionConfig.scanner.schedule 取得）
    輸出：每次 scan 命中為 source=vibe_shadow 的多筆 Signal
    配置：scanner.schedule（cron expression）

    預期實作策略：
        - 內部 spawn asyncio task 跑 cron loop（croniter）
        - scan 結果經 strategy 對應後一筆一筆呼叫 router.ingest()
        - 注意：研究級候選，建議搭配人工複核或更嚴格風控
    """

    async def start(self) -> None:
        raise NotImplementedError(
            _NOT_IMPLEMENTED_MSG.format(name="VibeShadowScannerAdapter")
        )

    async def stop(self) -> None:
        raise NotImplementedError(
            _NOT_IMPLEMENTED_MSG.format(name="VibeShadowScannerAdapter")
        )


class Mt5HttpPushAdapter:
    """MT5 EA HTTP push 接收 adapter。

    用途：自寫 MT5 Expert Advisor 透過 WebRequest() 推送訊號至本 adapter
        提供的 HTTP 端點（類似 TradingViewWebhookAdapter）。
        主要適用外匯（FX）市場，加密與股票仍以 TradingView 為主。

    輸入：HTTP POST /webhook/mt5/{secret}/{strategy_id}
    輸出：source=mt5 的 Signal
    配置：與 TradingViewConfig 結構相似（secret + 認證機制待 EA 實作確定後設計）

    預期實作策略：
        - MT5 EA 自寫 HMAC（自訂 header），比 TV 更嚴的認證
        - 端點 schema 由 EA wrapper 定義
        - 與 TradingViewWebhookAdapter 共用認證 helper（signals/auth.py）
    """

    async def start(self) -> None:
        raise NotImplementedError(
            _NOT_IMPLEMENTED_MSG.format(name="Mt5HttpPushAdapter")
        )

    async def stop(self) -> None:
        raise NotImplementedError(
            _NOT_IMPLEMENTED_MSG.format(name="Mt5HttpPushAdapter")
        )
