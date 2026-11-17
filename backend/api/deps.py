"""Phụ thuộc chung: lấy core/settings/lock từ app.state, khoá một phiên tại một thời điểm."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException, Request

from ..agent_core import AgentCore
from ..config import Settings


def get_core(request: Request) -> AgentCore:
    return request.app.state.core


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


class RunLock:
    """Chỉ một phiên Claude chạy tại một thời điểm (bảo vệ file và quota).

    Mọi thao tác đều diễn ra trên một vòng lặp sự kiện nên một cờ bool là đủ.
    """

    def __init__(self) -> None:
        self._busy = False
        self.current: dict[str, Any] | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    def try_acquire(self, info: dict[str, Any]) -> None:
        if self._busy:
            raise HTTPException(409, {"message": "Đang có phiên khác chạy, hãy chờ xong rồi thử lại.",
                                      "current": self.current})
        self._busy = True
        self.current = info

    def release(self) -> None:
        self._busy = False
        self.current = None

    async def guard(self, agen: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        try:
            async for ev in agen:
                yield ev
        finally:
            self.release()


def get_lock(request: Request) -> RunLock:
    return request.app.state.run_lock


def clamp_turns(requested: int | None, settings: Settings) -> int:
    if requested is None or requested <= 0:
        return settings.max_turns
    return min(requested, settings.max_turns)
