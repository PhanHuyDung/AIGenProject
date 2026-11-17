"""Truy cập file an toàn trong knowledge/ và .claude/.

Mọi đường dẫn từ web đều đi qua safe_resolve(): chuẩn hoá, từ chối traversal,
resolve symlink, rồi bắt buộc nằm trong một thư mục gốc được phép.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from . import config as cfg
from .agent_core import is_path_allowed, read_frontmatter

STALE_DAYS = 90
WRITABLE_SUFFIXES = {".md", ".yaml", ".yml", ".json", ".txt"}
SYSTEM_DIRS = {"_cho-duyet", "_bao-cao"}


def roots() -> dict[str, Path]:
    return {"knowledge": cfg.KNOWLEDGE_DIR, ".claude": cfg.CLAUDE_DIR}


def _normalize(rel: str) -> str:
    rel = (rel or "").replace("\\", "/").strip()
    if "\x00" in rel:
        raise HTTPException(400, "Đường dẫn không hợp lệ.")
    while rel.startswith("/"):
        rel = rel[1:]
    if not rel:
        raise HTTPException(400, "Thiếu đường dẫn.")
    if re.match(r"^[A-Za-z]:", rel) or rel.startswith("//"):
        raise HTTPException(400, "Không nhận đường dẫn tuyệt đối.")
    parts = rel.split("/")
    if any(p in ("..", ".") or p == "" for p in parts):
        raise HTTPException(400, "Đường dẫn không được chứa '..' hoặc đoạn rỗng.")
    return rel


def safe_resolve(rel: str, *, allowed_roots: tuple[str, ...] = ("knowledge", ".claude"),
                 must_exist: bool = False) -> Path:
    """Trả về đường dẫn tuyệt đối đã kiểm tra, hoặc raise HTTPException 400/403/404."""
    rel = _normalize(rel)
    target = (cfg.PROJECT_ROOT / rel).resolve()
    for name in allowed_roots:
        root = roots()[name].resolve()
        try:
            target.relative_to(root)
            break
        except ValueError:
            continue
    else:
        raise HTTPException(403, f"Chỉ được truy cập trong {', '.join(allowed_roots)}/.")
    if target.name.lower() == ".env" or target.name.lower().startswith(".env."):
        raise HTTPException(403, "Không được truy cập file .env.")
    if must_exist and not target.exists():
        raise HTTPException(404, f"Không tìm thấy '{rel}'.")
    return target


def relpath(path: Path) -> str:
    return path.resolve().relative_to(cfg.PROJECT_ROOT.resolve()).as_posix()


def read_text(rel: str, allowed_roots=("knowledge", ".claude")) -> tuple[Path, str]:
    path = safe_resolve(rel, allowed_roots=allowed_roots, must_exist=True)
    if path.is_dir():
        raise HTTPException(400, "Đây là thư mục, không phải file.")
    try:
        return path, path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(415, "File không phải văn bản UTF-8.")


def write_text(rel: str, content: str) -> Path:
    path = safe_resolve(rel)
    if path.suffix.lower() not in WRITABLE_SUFFIXES:
        raise HTTPException(415, f"Chỉ ghi được file {', '.join(sorted(WRITABLE_SUFFIXES))}.")
    ok, reason = is_path_allowed(str(path))
    if not ok:
        raise HTTPException(403, reason)
    if path.exists() and path.is_dir():
        raise HTTPException(400, "Đường dẫn trỏ tới thư mục.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return path


# ----------------------------------------------------------------------------
# Kho kiến thức
# ----------------------------------------------------------------------------

def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def is_stale(last_updated: str | None, today: date | None = None) -> bool:
    d = parse_date(last_updated)
    if d is None:
        return False
    return ((today or date.today()) - d).days > STALE_DAYS


def file_meta(path: Path) -> dict[str, Any]:
    fm = read_frontmatter(path)
    return {
        "title": fm.get("title") or path.stem,
        "domain": fm.get("domain"),
        "last_updated": fm.get("last_updated"),
        "confidence": fm.get("confidence"),
        "status": fm.get("status"),
        "stale": is_stale(fm.get("last_updated")),
        "size": path.stat().st_size,
    }


def knowledge_tree() -> dict[str, Any]:
    root = cfg.KNOWLEDGE_DIR

    def walk(d: Path) -> dict[str, Any]:
        children = []
        for child in sorted(d.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                node = walk(child)
                if child.name in SYSTEM_DIRS or child.name.startswith("_"):
                    node["system"] = True
                children.append(node)
            elif child.suffix.lower() == ".md":
                children.append({
                    "name": child.name, "path": relpath(child), "type": "file",
                    "meta": file_meta(child),
                })
        return {"name": d.name, "path": relpath(d), "type": "dir", "children": children}

    if not root.exists():
        return {"name": "knowledge", "path": "knowledge", "type": "dir", "children": []}
    return walk(root)


def search_knowledge(q: str, limit: int = 50) -> list[dict[str, Any]]:
    q_low = q.strip().lower()
    if not q_low:
        return []
    results = []
    for path in sorted(cfg.KNOWLEDGE_DIR.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        low = text.lower()
        in_name = q_low in path.name.lower()
        idx = low.find(q_low)
        if not in_name and idx < 0:
            continue
        snippet = ""
        if idx >= 0:
            start = max(0, idx - 60)
            snippet = text[start:start + 160].replace("\n", " ")
        results.append({"path": relpath(path), "meta": file_meta(path), "snippet": snippet,
                        "match": "name" if in_name else "content"})
        if len(results) >= limit:
            break
    return results


# ----------------------------------------------------------------------------
# Đề xuất chờ duyệt (knowledge/_cho-duyet/*.md)
# ----------------------------------------------------------------------------

_PROPOSAL_BLOCK_RE = re.compile(r"^## Đề xuất\s+(\d+)\s*[–-]\s*(.*)$", re.M)
_FIELD_RE = re.compile(r"^- \*\*(.+?):\*\*\s*(.*)$", re.M)
PROPOSAL_STATUSES = ("cho-duyet", "da-duyet", "tu-choi")


@dataclass
class Proposal:
    id: str
    path: str
    target: str
    created: str
    status: str
    proposed_by: str
    decided: str | None
    decision_note: str | None
    items: list[dict[str, Any]]
    target_exists: bool


def _split_items(body: str) -> list[dict[str, Any]]:
    matches = list(_PROPOSAL_BLOCK_RE.finditer(body))
    items = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        block = body[m.end():end].strip()
        fields = {k.strip().lower(): v.strip() for k, v in _FIELD_RE.findall(block)}
        items.append({
            "index": int(m.group(1)),
            "title": m.group(2).strip(),
            "kind": fields.get("loại"),
            "location": fields.get("vị trí"),
            "reason": fields.get("lý do chưa chắc chắn"),
            "body": block,
        })
    return items


def load_proposal(path: Path) -> Proposal:
    text = path.read_text(encoding="utf-8")
    fm = read_frontmatter(path)
    body = text.split("\n---", 2)[-1] if text.startswith("---") else text
    target = fm.get("target", "")
    target_path = (cfg.PROJECT_ROOT / target) if target else None
    return Proposal(
        id=path.stem, path=relpath(path), target=target, created=fm.get("created", ""),
        status=fm.get("status", "cho-duyet"), proposed_by=fm.get("proposed_by", ""),
        decided=fm.get("decided"), decision_note=fm.get("decision_note"),
        items=_split_items(body), target_exists=bool(target_path and target_path.exists()),
    )


def list_proposals(status: str | None = None) -> list[Proposal]:
    if not cfg.PENDING_DIR.exists():
        return []
    out = []
    for f in sorted(cfg.PENDING_DIR.glob("*.md"), reverse=True):
        try:
            p = load_proposal(f)
        except (OSError, UnicodeDecodeError):
            continue
        if status and p.status != status:
            continue
        out.append(p)
    return out


def proposal_path(proposal_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9._-]+", proposal_id or "") or ".." in proposal_id:
        raise HTTPException(400, "Mã đề xuất không hợp lệ.")
    path = cfg.PENDING_DIR / f"{proposal_id}.md"
    if not path.exists():
        raise HTTPException(404, f"Không có đề xuất '{proposal_id}'.")
    return path


def set_proposal_status(proposal_id: str, status: str, note: str | None = None) -> Proposal:
    if status not in PROPOSAL_STATUSES:
        raise HTTPException(400, f"status phải là một trong {PROPOSAL_STATUSES}.")
    path = proposal_path(proposal_id)
    text = path.read_text(encoding="utf-8")
    m = re.match(r"\A---\s*\n(.*?)\n---", text, re.S)
    if not m:
        raise HTTPException(422, "File đề xuất không có frontmatter.")
    lines = [ln for ln in m.group(1).splitlines() if not ln.startswith(("decided:", "decision_note:"))]
    lines = [re.sub(r"^status:.*$", f"status: {status}", ln) for ln in lines]
    if not any(ln.startswith("status:") for ln in lines):
        lines.append(f"status: {status}")
    if status != "cho-duyet":
        lines.append(f"decided: {date.today().isoformat()}")
        if note:
            lines.append("decision_note: " + note.replace("\n", " ").strip())
    new_text = "---\n" + "\n".join(lines) + "\n---" + text[m.end():]
    path.write_text(new_text, encoding="utf-8", newline="\n")
    return load_proposal(path)
