# add-reservation-release-bridge — 驗收紀錄

## 驗證

```
$ openspec validate add-reservation-release-bridge → valid
$ mypy → 112 source files clean
$ pytest -q → 393 passed
$ ruff check → All clean
```

## 對 spec scenario 的覆蓋

| Scenario | 測試 |
|----------|------|
| OrderSubmitted 紀錄 mapping | `test_reservation_bridge.py::test_order_submitted_records_mapping` |
| reservation_id None 跳過 | `test_order_submitted_with_none_reservation_skipped` |
| Reject 釋放 reservation | `test_order_rejected_releases_reservation` |
| Fill 釋放 reservation | `test_fill_processed_releases_reservation` |
| 未知 client_order_id 不釋放 | `test_unknown_client_order_id_does_not_release` |
| release 失敗容錯 | `test_release_failure_logged_but_not_raised` |
| LRU 淘汰 | `test_mapping_lru_eviction` |
| TTL 過期 | `test_expired_mapping_not_released` |
| OrderSubmitted reservation_id 與 decision 一致 | `test_execution.py::test_sink_success_emits_order_submitted`（已含） |

## 影響範圍

- **MODIFIED order-execution**：OrderSubmitted 加 reservation_id 欄位，向下相容（預設 None）
- **NEW reservation-release**：ReservationBridge 模組

既有測試（test_execution.py 等）仍全綠，無 breaking change。
