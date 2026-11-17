"""Lịch tự động: trạng thái, bật/tắt, chạy ngay, lịch sử chạy."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/scheduler", tags=["scheduler"])


class ToggleBody(BaseModel):
    enabled: bool


def _updater(request: Request):
    u = getattr(request.app.state, "scheduler", None)
    if u is None:
        raise HTTPException(503, "Lịch tự động chưa khởi tạo.")
    return u


@router.get("")
async def status(request: Request):
    return await _updater(request).status()


@router.post("/toggle")
async def toggle(body: ToggleBody, request: Request):
    u = _updater(request)
    await u.set_enabled(body.enabled)
    return await u.status()


@router.post("/run/{domain}")
async def run_now(domain: str, request: Request):
    u = _updater(request)
    if u.lock.busy:
        raise HTTPException(409, {"message": "Đang có phiên khác chạy.", "current": u.lock.current})
    if domain not in [j.domain for j in u.config.jobs]:
        from ..agent_core import list_domains
        if domain not in list_domains():
            raise HTTPException(404, f"Không có lĩnh vực '{domain}'.")
    u.run_in_background(domain, trigger="manual")
    return {"started": True, "domain": domain}


@router.get("/runs")
async def runs(request: Request, limit: int = Query(50, ge=1, le=500)):
    u = _updater(request)
    await u.core._ensure_db()
    return await u.core.store.list_auto_runs(limit)
