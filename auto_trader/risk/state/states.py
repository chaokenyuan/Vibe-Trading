"""SystemState：FSM 六個狀態列舉。

對應 spec：「系統狀態機維護全系統風險狀態」。
"""

from __future__ import annotations

from enum import StrEnum


class SystemState(StrEnum):
    """風控閘 Layer 1 狀態。

    NORMAL      : 全速交易
    WARNING     : 告警繼續交易
    THROTTLED   : 縮量交易 + 鎖新策略
    HALTED      : 停新單守倉，必須人工 reset
    KILL_SWITCH : 全平 + 4 小時冷靜期，人工 reset 才能解鎖
    MAINTENANCE : 人工專用，升級/遷移時使用
    """

    NORMAL = "NORMAL"
    WARNING = "WARNING"
    THROTTLED = "THROTTLED"
    HALTED = "HALTED"
    KILL_SWITCH = "KILL_SWITCH"
    MAINTENANCE = "MAINTENANCE"
