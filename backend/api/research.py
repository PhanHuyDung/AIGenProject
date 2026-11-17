"""POST /api/research và POST /api/skills/{name}/run → SSE."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..agent_core import AgentCore, list_domains, list_skills, resolve_domain
from ..config import Settings
from .deps import RunLock, clamp_turns, get_core, get_lock, get_settings
from .sse import sse_response

router = APIRouter(prefix="/api", tags=["research"])


class ResearchRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20000)
    domain: str | None = None
    max_turns: int | None = Field(default=None, ge=1, le=500)


class SkillRequest(BaseModel):
    args: str = Field(default="", max_length=20000)
    max_turns: int | None = Field(default=None, ge=1, le=500)


@router.post("/research")
async def research(body: ResearchRequest, core: AgentCore = Depends(get_core),
                   settings: Settings = Depends(get_settings), lock: RunLock = Depends(get_lock)):
    if not body.prompt.strip():
        raise HTTPException(422, "Câu hỏi trống.")
    domain = None
    if body.domain:
        resolved = resolve_domain(body.domain)
        if resolved is None:
            raise HTTPException(400, {"message": f"Không có agent cho lĩnh vực '{body.domain}'.",
                                      "domains": list_domains()})
        domain = resolved["domain"]
    turns = clamp_turns(body.max_turns, settings)
    lock.try_acquire({"kind": "research", "prompt": body.prompt[:120], "domain": domain})
    return sse_response(lock.guard(core.run_research(body.prompt, domain=domain, max_turns=turns)))


@router.post("/skills/{name}/run")
async def run_skill(name: str, body: SkillRequest, core: AgentCore = Depends(get_core),
                    settings: Settings = Depends(get_settings), lock: RunLock = Depends(get_lock)):
    names = [s["name"] for s in list_skills()]
    if name not in names:
        raise HTTPException(404, {"message": f"Không có skill '{name}'.", "skills": names})
    turns = clamp_turns(body.max_turns, settings)
    lock.try_acquire({"kind": "skill", "skill": name, "args": body.args[:120]})
    return sse_response(lock.guard(core.run_skill(name, body.args, max_turns=turns)))
