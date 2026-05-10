## ADDED Requirements

### Requirement: ReservationBridge 訂閱事件並維護 client_order_id ↔ reservation_id mapping

`ReservationBridge` SHALL 訂閱以下事件：

- `OrderSubmitted`：紀錄 `client_order_id → reservation_id`（若 reservation_id 為 None 則跳過紀錄）
- `OrderRejectedByBroker`：以 client_order_id 查 mapping，找到即呼叫 `reserver.release`
- `FillProcessed`：同上，找到即釋放

mapping SHALL 為 LRU + TTL：預設 TTL 24 小時、上限 100,000 筆。

#### Scenario: OrderSubmitted 紀錄 mapping

- **WHEN** 收到 OrderSubmitted（reservation_id=R1, client_order_id=C1）
- **THEN** mapping SHALL 含 C1 → R1

#### Scenario: OrderSubmitted reservation_id 為 None 時跳過

- **WHEN** 收到 OrderSubmitted 帶 reservation_id=None
- **THEN** mapping SHALL 不包含此 client_order_id

#### Scenario: OrderRejectedByBroker 釋放 reservation

- **WHEN** 紀錄 C1 → R1 後收到 OrderRejectedByBroker(C1)
- **THEN** reserver.release(R1) SHALL 被呼叫一次
- **AND** mapping 中 C1 SHALL 被移除

#### Scenario: FillProcessed 釋放 reservation

- **WHEN** 紀錄 C1 → R1 後收到 FillProcessed(client_order_id=C1)
- **THEN** reserver.release(R1) SHALL 被呼叫一次
- **AND** mapping 中 C1 SHALL 被移除

#### Scenario: 未知 client_order_id 的 fill 不釋放

- **WHEN** mapping 不含 C2 但收到 FillProcessed(C2)
- **THEN** reserver.release SHALL 不被呼叫
- **AND** logger.warning SHALL 紀錄

#### Scenario: release 失敗紀錄 error 但不向上拋

- **WHEN** reserver.release 拋例外
- **THEN** Bridge SHALL 不向上拋
- **AND** logger.exception SHALL 紀錄

#### Scenario: mapping 達上限觸發 LRU 淘汰

- **WHEN** mapping 已達 max_entries 且新 OrderSubmitted 到達
- **THEN** 最早條目 SHALL 被淘汰
