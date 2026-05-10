"""vibe-auto-trader reservation-release capability。

橋接 client_order_id ↔ reservation_id；fill / reject 自動釋放對應 reservation。
對外進入點：reservation_bridge.bridge.ReservationBridge。
"""
