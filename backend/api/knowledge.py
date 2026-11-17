"""Kho kiến thức: cây thư mục, nội dung file, tìm kiếm."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..agent_core import read_frontmatter
from ..files import file_meta, knowledge_tree, read_text, relpath, search_knowledge

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("")
async def tree():
    return knowledge_tree()


@router.get("/search")
async def search(q: str = Query(min_length=1, max_length=200), limit: int = Query(50, ge=1, le=200)):
    return {"q": q, "results": search_knowledge(q, limit)}


@router.get("/{path:path}")
async def read_file(path: str):
    norm = path.replace("\\", "/").lstrip("/")
    if not norm.startswith("knowledge/"):
        norm = "knowledge/" + norm
    p, content = read_text(norm, allowed_roots=("knowledge",))
    return {"path": relpath(p), "content": content, "frontmatter": read_frontmatter(p), "meta": file_meta(p)}
