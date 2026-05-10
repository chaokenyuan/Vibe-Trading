"""URL secret token + IP 白名單驗證。

對應 spec：「TradingViewWebhookAdapter 認證採 URL secret + IP 白名單」。
secret 比對使用 hmac.compare_digest 為 constant-time，避免 timing attack。
"""

from __future__ import annotations

import hmac
from collections.abc import Iterable


def verify_secret(provided: str, expected: str) -> bool:
    """constant-time 比對 secret token。"""
    return hmac.compare_digest(provided, expected)


def verify_ip(client_ip: str, allowed_ips: Iterable[str]) -> bool:
    """IP 白名單檢查。

    空白名單代表全部接受（適合本機測試）；
    非空白名單僅接受名單中的 IP（精確比對，不支援 CIDR）。
    """
    allowed_list = list(allowed_ips)
    if not allowed_list:
        return True
    return client_ip in allowed_list
