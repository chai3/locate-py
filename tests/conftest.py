"""pytest共通フィクスチャ。"""

from collections.abc import Generator

import pytest

from locatepy.mcp import _state


@pytest.fixture(autouse=True)
def reset_mcp_state() -> Generator[None, None, None]:
    """各テスト後に mcp._state を元の値に戻し、テスト間の状態汚染を防ぐ。"""
    original = _state.copy()
    yield
    _state.clear()
    _state.update(original)
