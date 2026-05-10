"""Stub adapters 測試（VibeShadowScannerAdapter + Mt5HttpPushAdapter）。"""

from __future__ import annotations

import pytest

from signals.adapters.stubs import Mt5HttpPushAdapter, VibeShadowScannerAdapter
from signals.ports import SignalSource


@pytest.mark.parametrize(
    "stub_cls", [VibeShadowScannerAdapter, Mt5HttpPushAdapter]
)
@pytest.mark.asyncio
async def test_stub_start_raises_not_implemented(stub_cls: type) -> None:
    """spec scenario：嘗試啟動 stub adapter 拋 NotImplementedError。"""
    adapter = stub_cls()
    with pytest.raises(NotImplementedError, match="not implemented"):
        await adapter.start()


@pytest.mark.parametrize(
    "stub_cls", [VibeShadowScannerAdapter, Mt5HttpPushAdapter]
)
@pytest.mark.asyncio
async def test_stub_stop_raises_not_implemented(stub_cls: type) -> None:
    adapter = stub_cls()
    with pytest.raises(NotImplementedError, match="not implemented"):
        await adapter.stop()


@pytest.mark.parametrize(
    "stub_cls", [VibeShadowScannerAdapter, Mt5HttpPushAdapter]
)
def test_stub_satisfies_signal_source_protocol(stub_cls: type) -> None:
    """spec scenario：4 adapter 結構性符合 SignalSource Protocol。"""
    assert isinstance(stub_cls(), SignalSource)


@pytest.mark.parametrize(
    "stub_cls", [VibeShadowScannerAdapter, Mt5HttpPushAdapter]
)
def test_stub_has_docstring(stub_cls: type) -> None:
    """spec：stub 含完整 docstring（用途／輸入／輸出／配置／實作策略）。"""
    doc = stub_cls.__doc__
    assert doc is not None
    assert "用途" in doc
    assert "輸入" in doc
    assert "輸出" in doc
    assert "配置" in doc
    assert "實作策略" in doc
