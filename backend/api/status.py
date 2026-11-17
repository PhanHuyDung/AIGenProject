"""GET /api/status: xác thực, môi trường, số đề xuất chờ duyệt, trạng thái bận."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict

from fastapi import APIRouter, Depends, Query, Request

from ..agent_core import count_pending_proposals
from ..config import Settings
from ..env_check import check_environment
from .deps import RunLock, get_lock, get_settings

router = APIRouter(prefix="/api", tags=["status"])

_CACHE: dict[str, object] = {"at": 0.0, "report": None}
CACHE_SECONDS = 60


async def _report(force: bool):
    now = time.monotonic()
    if force or _CACHE["report"] is None or now - float(_CACHE["at"]) > CACHE_SECONDS:
        _CACHE["report"] = await asyncio.to_thread(check_environment, True)
        _CACHE["at"] = now
    return _CACHE["report"]


@router.get("/status")
async def status(request: Request, refresh: bool = Query(False), settings: Settings = Depends(get_settings),
                 lock: RunLock = Depends(get_lock)):
    report = None if getattr(request.app.state, "skip_env_check", False) else await _report(refresh)
    auth = (report.auth if report else None) or {}
    return {
        "ok": report.ok if report else True,
        "auth": {
            "logged_in": bool(auth.get("loggedIn")),
            "method": auth.get("authMethod"),
            "subscription": auth.get("subscriptionType"),
            "uses_subscription": bool(auth.get("loggedIn")) and auth.get("authMethod") == "claude.ai",
        },
        "cli_version": report.cli_version if report else None,
        "removed_env": report.removed_env if report else [],
        "problems": [asdict(p) for p in report.problems] if report else [],
        "pending_proposals": count_pending_proposals(),
        "busy": lock.busy,
        "current": lock.current,
        "settings": {"max_turns": settings.max_turns, "max_daily_runs": settings.max_daily_runs,
                     "env_file_exists": settings.env_file_exists},
    }
