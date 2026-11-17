"""Lịch sử phiên từ SQLite."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..agent_core import AgentCore
from .deps import get_core

router = APIRouter(prefix="/api/history", tags=["history"])


@router.get("")
async def history(limit: int = Query(50, ge=1, le=500), core: AgentCore = Depends(get_core)):
    await core._ensure_db()
    return await core.store.list_sessions(limit)


@router.get("/{session_id}")
async def session(session_id: str, core: AgentCore = Depends(get_core)):
    await core._ensure_db()
    s = await core.store.get_session(session_id)
    if s is None:
        raise HTTPException(404, "Không có phiên này.")
    return s
