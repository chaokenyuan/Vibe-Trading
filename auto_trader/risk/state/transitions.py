"""FSM 狀態轉換純函式。

純函式設計（無副作用）：
- 輸入：當前狀態 + 即時 metrics + 配置閾值
- 輸出：目標狀態
- StateMachine 負責後續動作（事件發布、持久化、冷靜期計時）

下行（嚴重度提升）：可跨級立即套用（例：NORMAL → HALTED）
上行（嚴重度下降）：階梯式，每 tick 升一級（THROTTLED → WARNING → NORMAL）
人工專用狀態（MAINTENANCE / KILL_SWITCH）：自動規則不影響，須人工指令解除

對應 spec：「系統狀態轉換依凍結閾值自動觸發」。
"""

from __future__ import annotations

from risk.config import FsmThresholds
from risk.state.states import SystemState

# 嚴重度分級：自動規則只能下行至更高嚴重度，上行需階梯
_SEVERITY: dict[SystemState, int] = {
    SystemState.NORMAL: 0,
    SystemState.WARNING: 1,
    SystemState.THROTTLED: 2,
    SystemState.HALTED: 3,
    SystemState.KILL_SWITCH: 4,
    SystemState.MAINTENANCE: 5,  # 與其他無自然順序，人工專用
}

# 階梯回升映射
_STEP_UP: dict[SystemState, SystemState] = {
    SystemState.WARNING: SystemState.NORMAL,
    SystemState.THROTTLED: SystemState.WARNING,
}


def evaluate_transition(
    current: SystemState,
    *,
    daily_pnl_ratio: float,
    api_error_rate: float,
    thresholds: FsmThresholds,
) -> SystemState:
    """依當前狀態與 metrics 計算目標狀態。

    Args:
        current: 當前 FSM 狀態。
        daily_pnl_ratio: 日內 PnL 佔總權益比例（負值代表虧損）。
        api_error_rate: API 錯誤率（0-1 之間）。
        thresholds: FSM 觸發閾值（來自 config）。

    Returns:
        目標狀態。可能與 current 相同（不轉換）。
    """
    # MAINTENANCE 與 KILL_SWITCH 鎖死，自動規則不變更（須人工指令）
    if current in (SystemState.MAINTENANCE, SystemState.KILL_SWITCH):
        return current

    # 緊急下行：任何狀態 → KILL_SWITCH（最強，優先於其他規則）
    if daily_pnl_ratio <= thresholds.daily_pnl_kill:
        return SystemState.KILL_SWITCH

    # HALTED 不自動回升（spec scenario：HALTED 不自動回升）
    if current == SystemState.HALTED:
        return current

    # 計算「符合 metrics 的目標嚴重度」
    target = _target_for_metrics(daily_pnl_ratio, api_error_rate, thresholds)

    # 下行（嚴重度提升）：直接套用，可跨級
    if _SEVERITY[target] > _SEVERITY[current]:
        return target

    # 上行（嚴重度下降）：階梯，每 tick 只升一級
    if _SEVERITY[target] < _SEVERITY[current]:
        return _STEP_UP.get(current, current)

    # 同嚴重度：保持
    return current


def _target_for_metrics(
    daily_pnl_ratio: float,
    api_error_rate: float,
    thresholds: FsmThresholds,
) -> SystemState:
    """純粹依 metrics 推算「最匹配的狀態」，不考慮當前狀態的階梯約束。"""
    if daily_pnl_ratio <= thresholds.daily_pnl_halted:
        return SystemState.HALTED
    if (
        daily_pnl_ratio <= thresholds.daily_pnl_throttled
        or api_error_rate > thresholds.api_error_rate_throttled
    ):
        return SystemState.THROTTLED
    if daily_pnl_ratio <= thresholds.daily_pnl_warning:
        return SystemState.WARNING
    return SystemState.NORMAL
