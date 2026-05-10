## MODIFIED Requirements

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
