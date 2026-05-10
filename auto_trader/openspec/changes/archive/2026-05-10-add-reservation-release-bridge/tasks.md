## 1. 修改既有 OrderSubmitted 事件

- [x] 1.1 `execution/events.py`：OrderSubmitted 加 `reservation_id: UUID | None = None`
- [x] 1.2 `execution/sink.py`：發布事件時帶 decision.reservation_id
- [x] 1.3 既有測試 `test_execution.py` 確保仍通過

## 2. ReservationBridge

- [x] 2.1 `reservation_bridge/__init__.py`
- [x] 2.2 `reservation_bridge/bridge.py`：
  - 訂閱 OrderSubmitted / OrderRejectedByBroker / FillProcessed
  - 內部 OrderedDict-based LRU mapping + TTL（clock.monotonic）
  - reserver.release 失敗紀錄 error 不向上拋
- [x] 2.3 pyproject.toml include `reservation_bridge*`

## 3. 測試

- [x] 3.1 `tests/test_reservation_bridge.py`：覆蓋所有 spec scenario
- [x] 3.2 e2e：StrategyHost → ExchangeOrderSink → Bridge → 收 fill → release

## 4. 驗收

- [x] 4.1 mypy / pytest / ruff 全綠
- [x] 4.2 acceptance.md
