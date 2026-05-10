## 1. 骨架

- [x] 1.1 建立 `reconciliation/` 套件 + `reconciliation/adapters/`
- [x] 1.2 pyproject.toml include `reconciliation*`

## 2. 核心元件

- [x] 2.1 `reconciliation/events.py`：FillProcessed 事件
- [x] 2.2 `reconciliation/ports.py`：FillSource Protocol（runtime_checkable）
- [x] 2.3 `reconciliation/processor.py`：FillProcessor（內含 fill_id 去重）
- [x] 2.4 `reconciliation/broker_book.py`：BrokerPositionTracker
- [x] 2.5 `reconciliation/position_reader.py`：BookPositionReader

## 3. Adapters

- [x] 3.1 `reconciliation/adapters/mock.py`：MockFillSource（push API）
- [x] 3.2 `reconciliation/adapters/ccxt_stub.py`：CcxtFillSource stub

## 4. 文件 + 整合

- [x] 4.1 `reconciliation/README.md`
- [x] 4.2 e2e 測試：MockFillSource + FillProcessor + StrategyRegistry → 驗證 LogicalBook 更新

## 5. 驗收

- [x] 5.1 mypy / pytest / ruff 全綠
- [x] 5.2 acceptance.md
