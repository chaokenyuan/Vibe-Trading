"""vibe-auto-trader order-execution capability。

訂單執行層：實作 strategies.ports.OrderSink，把 APPROVE 的 OrderIntent 真正送到交易所。
本 capability 提供：
- ExchangeOrderSink（OrderSink 實作）
- ExecutionAdapter Protocol（交易所 SDK 抽象）
- MockExecutionAdapter（測試與 dry-run 用）
- CcxtExecutionAdapter stub（後續 change 填入真實邏輯）
"""
