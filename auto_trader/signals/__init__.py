"""vibe-auto-trader signal-ingestion capability。

訊號入口層：把外部世界（TradingView / Vibe-Trading scanner / MT5 / CLI）的訊號
轉換為內部正規化的 Signal，並交給 strategy-host capability 消費。

對外進入點：signal.router.SignalRouter。
"""
