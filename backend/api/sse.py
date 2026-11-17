"""Server-Sent Events từ async generator sự kiện của agent_core."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi.responses import StreamingResponse

PING_SECONDS = 15


def format_event(ev: dict[str, Any]) -> str:
    payload = json.dumps(ev, ensure_ascii=False, default=str)
    return f"event: {ev.get('type', 'message')}\ndata: {payload}\n\n"


async def _stream(agen: AsyncIterator[dict[str, Any]]) -> AsyncIterator[str]:
    it = agen.__aiter__()
    pending: asyncio.Task | None = None
    try:
        while True:
            if pending is None:
                pending = asyncio.ensure_future(it.__anext__())
            done, _ = await asyncio.wait({pending}, timeout=PING_SECONDS)
            if not done:
                yield ": ping\n\n"
                continue
            try:
                ev = pending.result()
            except StopAsyncIteration:
                break
            finally:
                pending = None
            yield format_event(ev)
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
        aclose = getattr(agen, "aclose", None)
        if aclose is not None:
            try:
                await aclose()
            except Exception:  # noqa: BLE001 - đóng generator khi client ngắt
                pass


def sse_response(agen: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
    return StreamingResponse(
        _stream(agen),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
