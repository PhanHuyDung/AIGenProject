"""Agent, skill và đọc/ghi file trong .claude/ và knowledge/ để sửa trên web."""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agent_core import list_agents, list_domain_agents, list_skills, read_frontmatter
from ..files import read_text, relpath, write_text

router = APIRouter(prefix="/api", tags=["claude-files"])


class FileBody(BaseModel):
    content: str = Field(max_length=2_000_000)


@router.get("/agents")
async def agents():
    domain_by_agent = {d["agent"]: d["domain"] for d in list_domain_agents()}
    out = []
    for a in list_agents():
        a = dict(a)
        a["domain"] = domain_by_agent.get(a["name"])
        out.append(a)
    return out


@router.get("/skills")
async def skills():
    return list_skills()


@router.get("/files/{path:path}")
async def get_file(path: str):
    p, content = read_text(path)
    return {"path": relpath(p), "content": content, "frontmatter": read_frontmatter(p)}


@router.put("/files/{path:path}")
async def put_file(path: str, body: FileBody):
    norm = path.replace("\\", "/").lstrip("/")
    is_agent_or_skill = norm.startswith(".claude/agents/") or norm.endswith("/SKILL.md")
    if is_agent_or_skill:
        m = re.match(r"\A---\s*\n(.*?)\n---", body.content, re.S)
        if not m:
            raise HTTPException(422, "File agent/skill phải bắt đầu bằng frontmatter (---).")
        if not re.search(r"^name:\s*\S", m.group(1), re.M):
            raise HTTPException(422, "Frontmatter phải có trường name.")
    p = write_text(path, body.content)
    return {"path": relpath(p), "bytes": p.stat().st_size, "frontmatter": read_frontmatter(p)}
