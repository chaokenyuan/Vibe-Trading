# order-execution Specification

## Purpose
TBD - created by archiving change add-order-execution. Update Purpose after archive.
## Requirements
### Requirement: ExecutionAdapter 為交易所 SDK 抽象

`ExecutionAdapter` Protocol SHALL 暴露：

- `async submit(intent, client_order_id) -> str`：回傳交易所 broker_order_id
- `async cancel(broker_order_id) -> None`

`MockExecutionAdapter` 為完整測試替身；`CcxtExecutionAdapter` 為 stub（拋 NotImplementedError）。

#### Scenario: MockExecutionAdapter 結構符合 Protocol

- **WHEN** `isinstance(MockExecutionAdapter(), ExecutionAdapter)`（runtime_checkable）
- **THEN** SHALL 回傳 True

#### Scenario: CcxtExecutionAdapter stub 拋 NotImplementedError

- **WHEN** 呼叫 CcxtExecutionAdapter().submit(...)
- **THEN** SHALL 拋 NotImplementedError，附訊息指向後續 change

---

### Requirement: ExchangeOrderSink 實作 strategies.OrderSink

`ExchangeOrderSink` SHALL 結構性符合 `strategies.ports.OrderSink`，且：

1. 接受 ExecutionAdapter 與 EventPublisher 注入
2. submit() 呼叫 adapter.submit 取得 broker_order_id
3. 成功發布 `OrderSubmitted` 事件，**附 `reservation_id` 欄位（從 decision.reservation_id 取得，可為 None）**
4. adapter raise 時發布 `OrderRejectedByBroker` 並 re-raise

#### Scenario: 成功 submit 發布 OrderSubmitted

- **WHEN** ExchangeOrderSink.submit 成功
- **THEN** EventPublisher SHALL 收到一筆 OrderSubmitted 事件，含 broker_order_id 與 client_order_id
- **AND** OrderSubmitted.reservation_id SHALL 與 decision.reservation_id 相同

#### Scenario: adapter 失敗發布 OrderRejectedByBroker

- **WHEN** ExecutionAdapter.submit 拋例外
- **THEN** EventPublisher SHALL 收到 OrderRejectedByBroker 事件
- **AND** ExchangeOrderSink SHALL re-raise 該例外

#### Scenario: ExchangeOrderSink 結構符合 strategies.ports.OrderSink

- **WHEN** `isinstance(ExchangeOrderSink(...), OrderSink)`
- **THEN** SHALL 回傳 True

#### Scenario: decision.reservation_id 為 None 時 OrderSubmitted 帶 None

- **WHEN** decision.reservation_id 為 None（例如 RiskGate 配置未啟用 CapitalReservationRule）
- **THEN** OrderSubmitted.reservation_id SHALL 為 None

### Requirement: MockExecutionAdapter 提供可控行為

`MockExecutionAdapter` SHALL 支援：

- 預設成功模式：每次 submit 回傳遞增的 broker_order_id
- failure_mode：toggling 後 submit 直接拋例外
- 紀錄所有呼叫，供測試斷言

#### Scenario: 預設成功模式 submit 回傳 broker_order_id

- **WHEN** 預設模式下呼叫 submit 兩次
- **THEN** SHALL 回傳兩個不同 broker_order_id

#### Scenario: failure_mode 啟用後 submit 拋例外

- **WHEN** 設定 mock.fail_next=True 後呼叫 submit
- **THEN** SHALL 拋 RuntimeError

#### Scenario: 紀錄所有 submit 呼叫

- **WHEN** submit 三次後查 mock.submitted
- **THEN** SHALL 回傳三筆紀錄

---

### Requirement: 事件契約

事件 `OrderSubmitted` 與 `OrderRejectedByBroker` SHALL 為 frozen dataclass（繼承 `risk.events.Event`），可序列化為 JSON。

#### Scenario: 事件不可變

- **WHEN** 嘗試修改 OrderSubmitted 任一欄位
- **THEN** SHALL 拋 FrozenInstanceError

#### Scenario: 事件可序列化

- **WHEN** to_dict() 並 json.dumps
- **THEN** SHALL 完整輸出

