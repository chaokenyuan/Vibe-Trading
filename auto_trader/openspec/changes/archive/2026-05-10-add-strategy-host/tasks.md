## 1. 骨架

- [x] 1.1 建立 `strategies/` 套件 + `strategies/strategies/`（具體實作集）
- [x] 1.2 在 `pyproject.toml` 設定 `strategies*` include

## 2. 值物件與型別

- [x] 2.1 在 `strategies/types.py` 定義 `StrategyState` StrEnum、`LogicalPosition`、`Fill` frozen dataclass
- [x] 2.2 Fill.to_dict 共用 risk._serialize.to_json_safe
- [x] 2.3 撰寫 types 不可變 + 序列化測試

## 3. Ports

- [x] 3.1 在 `strategies/ports.py` 定義 `Strategy` Protocol（runtime_checkable）
- [x] 3.2 同檔定義 `OrderSink` Protocol
- [x] 3.3 撰寫 Protocol 結構驗證測試

## 4. LogicalBook

- [x] 4.1 在 `strategies/book.py` 實作 `LogicalBook`：apply_fill 加減倉與 avg_entry 更新
- [x] 4.2 撰寫測試：開倉、加倉、平倉、SHORT、跨 symbol 隔離

## 5. StrategyRegistry

- [x] 5.1 在 `strategies/registry.py` 實作 `StrategyRegistry`：register/set_state/get_*/list
- [x] 5.2 register 自動建空 LogicalBook
- [x] 5.3 結構符合 signals.ports.StrategyRegistryProtocol（提供 get_strategy_metadata）
- [x] 5.4 撰寫測試：註冊、狀態切換、未知 ID 行為、與 SignalRouter 相容

## 6. StrategyHost

- [x] 6.1 在 `strategies/host.py` 實作 `StrategyHost(SignalConsumer)`
  - on_signal: registry lookup → state check → strategy.on_signal → for each intent: risk_gate.evaluate → submit
  - client_order_id 編碼
  - Strategy crash 設 FAILED
- [x] 6.2 撰寫測試覆蓋所有 spec scenario

## 7. PassthroughStrategy

- [x] 7.1 在 `strategies/strategies/passthrough.py` 實作 `PassthroughStrategy`
- [x] 7.2 撰寫測試

## 8. 文件與整合

- [x] 8.1 `strategies/README.md`
- [x] 8.2 e2e 整合測試：SignalRouter + StrategyHost + RiskGate + Mock OrderSink

## 9. 驗收

- [x] 9.1 `openspec validate add-strategy-host` 通過
- [x] 9.2 mypy strict 0 錯
- [x] 9.3 pytest 全過、coverage ≥ 90%
- [x] 9.4 撰寫 acceptance.md
