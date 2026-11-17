"""Đề xuất chờ duyệt trong knowledge/_cho-duyet/.

Agent không bao giờ tự đổi status. Người dùng duyệt/từ chối ở đây:
- reject: chỉ đổi status trong file đề xuất.
- approve: đổi status thành da-duyet, rồi chạy một phiên Claude ngắn để ghép
  nguyên văn nội dung đề xuất vào file đích (người dùng đã chọn cách này).
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..agent_core import AgentCore
from ..config import Settings
from ..files import PROPOSAL_STATUSES, Proposal, list_proposals, load_proposal, proposal_path, set_proposal_status
from .deps import RunLock, clamp_turns, get_core, get_lock, get_settings
from .sse import sse_response

router = APIRouter(prefix="/api/proposals", tags=["proposals"])

APPROVE_MAX_TURNS = 12


class DecisionBody(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class ApproveBody(BaseModel):
    items: list[int] | None = Field(default=None, description="Chỉ số đề xuất cần áp dụng; trống = tất cả")
    note: str | None = Field(default=None, max_length=2000)
    max_turns: int | None = Field(default=None, ge=1, le=100)


@router.get("")
async def proposals(status: str | None = Query(None)):
    if status is not None and status not in PROPOSAL_STATUSES:
        raise HTTPException(400, f"status phải là một trong {PROPOSAL_STATUSES}.")
    return [asdict(p) for p in list_proposals(status)]


@router.get("/{proposal_id}")
async def proposal(proposal_id: str):
    return asdict(load_proposal(proposal_path(proposal_id)))


@router.post("/{proposal_id}/reject")
async def reject(proposal_id: str, body: DecisionBody):
    p = load_proposal(proposal_path(proposal_id))
    if p.status != "cho-duyet":
        raise HTTPException(409, f"Đề xuất đang ở trạng thái '{p.status}', không thể từ chối.")
    return asdict(set_proposal_status(proposal_id, "tu-choi", body.note))


def _apply_prompt(p: Proposal, items: list[int] | None) -> str:
    which = "tất cả các đề xuất" if not items else "các đề xuất số " + ", ".join(str(i) for i in items)
    today = date.today().isoformat()
    return (
        f"Người dùng đã DUYỆT {which} trong file đề xuất `{p.path}` (status đã được đổi thành da-duyet). "
        f"Nhiệm vụ: áp dụng các đề xuất đó vào file đích `{p.target}`.\n\n"
        "Cách làm, không làm gì khác:\n"
        f"1. Đọc `{p.path}` và `{p.target}`.\n"
        "2. Với mỗi đề xuất được duyệt: ghép ĐÚNG NGUYÊN VĂN phần 'Nội dung đề xuất' vào vị trí ghi ở 'Vị trí' "
        "của file đích. Nếu 'Nội dung hiện tại' là một câu có trong file đích thì thay câu đó; nếu là 'chưa có' "
        "thì thêm vào cuối mục tương ứng. Thêm nguồn của đề xuất vào `sources` trong frontmatter và mục 'Nguồn' "
        "(đánh số tiếp), ghi rõ nếu là nguồn dẫn lại.\n"
        f"3. Cập nhật `last_updated: {today}`. Thêm vào mục 'Lịch sử thay đổi' (tạo nếu chưa có, đặt sau mục Nguồn) "
        f"một dòng: `- {today} — Áp dụng {which} từ {p.id}; đã được người dùng duyệt ngày {today}.`\n"
        "4. Cập nhật dòng tương ứng trong `knowledge/_index.md` (ngày cập nhật).\n"
        "5. KHÔNG tìm web, KHÔNG thêm nội dung ngoài đề xuất, KHÔNG sửa file đề xuất, KHÔNG đổi `confidence` "
        "trừ khi đề xuất yêu cầu. Chỉ dùng Read, Edit, Write.\n"
        "6. Báo lại ngắn gọn: đã ghép đề xuất nào vào đâu."
    )


@router.post("/{proposal_id}/approve")
async def approve(proposal_id: str, body: ApproveBody, core: AgentCore = Depends(get_core),
                  settings: Settings = Depends(get_settings), lock: RunLock = Depends(get_lock)):
    p = load_proposal(proposal_path(proposal_id))
    if p.status != "cho-duyet":
        raise HTTPException(409, f"Đề xuất đang ở trạng thái '{p.status}', không thể duyệt.")
    if not p.target_exists:
        raise HTTPException(409, f"File đích '{p.target}' không tồn tại.")
    valid = {it["index"] for it in p.items}
    if body.items:
        bad = [i for i in body.items if i not in valid]
        if bad:
            raise HTTPException(400, f"Không có đề xuất số {bad}; có: {sorted(valid)}.")
    turns = min(clamp_turns(body.max_turns or APPROVE_MAX_TURNS, settings), APPROVE_MAX_TURNS * 2)
    lock.try_acquire({"kind": "approve", "proposal": proposal_id})
    set_proposal_status(proposal_id, "da-duyet", body.note)

    async def run():
        failed = False
        try:
            async for ev in core.run_research(_apply_prompt(p, body.items), max_turns=turns):
                if ev["type"] == "error" or (ev["type"] == "done" and ev["data"].get("is_error")):
                    failed = True
                yield ev
        finally:
            if failed:
                try:
                    set_proposal_status(proposal_id, "cho-duyet")
                except HTTPException:
                    pass

    return sse_response(lock.guard(run()))
