"""Fixture: dự án tạm (knowledge/, .claude/) + TestClient không gọi Claude."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import agent_core, config, files
from backend.config import Settings
from backend.main import create_app

AGENT_MD = textwrap.dedent("""\
    ---
    name: ai-researcher
    description: Nghiên cứu AI, lưu vào knowledge/ai/.
    tools: WebSearch, WebFetch, Read, Write, Glob, Grep
    ---

    Ghi file trong `knowledge/ai/`.
    """)

SKILL_MD = textwrap.dedent("""\
    ---
    name: deep-research
    description: Nghiên cứu sâu.
    ---

    # Nghiên cứu sâu
    """)

KNOW_MD = textwrap.dedent("""\
    ---
    title: Mô hình ngôn ngữ
    domain: ai
    last_updated: {date}
    sources:
      - url: https://example.org/a
        title: A
        accessed: {date}
    confidence: cao
    ---

    ## Tóm tắt

    Nội dung thử nghiệm về transformer.

    ## Chi tiết

    ## Nhận định

    ## Nguồn

    1. [A](https://example.org/a) — truy cập {date}
    """)

PROPOSAL_MD = textwrap.dedent("""\
    ---
    target: knowledge/ai/mo-hinh-ngon-ngu.md
    created: 2026-11-17
    status: cho-duyet
    proposed_by: deep-research (ai-researcher)
    ---

    ## Đề xuất 1 – Số tham số

    - **Loại:** thêm
    - **Vị trí:** Chi tiết
    - **Nội dung hiện tại:** chưa có
    - **Nội dung đề xuất:** Mô hình có 7 tỷ tham số.
    - **Nguồn:** [B](https://example.org/b) — truy cập 2026-11-17
    - **Lý do chưa chắc chắn:** một nguồn

    ## Đề xuất 2 – Nhận định

    - **Loại:** nhận định
    - **Vị trí:** Nhận định
    - **Nội dung hiện tại:** chưa có
    - **Nội dung đề xuất:** Xu hướng tăng — mức độ chắc chắn: thấp.
    - **Nguồn:** suy luận
    - **Lý do chưa chắc chắn:** phỏng đoán
    """)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "proj"
    knowledge = root / "knowledge"
    claude = root / ".claude"
    (knowledge / "ai").mkdir(parents=True)
    (knowledge / "game").mkdir()
    (knowledge / "_cho-duyet").mkdir()
    (knowledge / "game" / ".gitkeep").write_text("")
    (claude / "agents").mkdir(parents=True)
    (claude / "skills" / "deep-research").mkdir(parents=True)
    (root / "backend").mkdir()
    (root / "frontend").mkdir()
    (root / "frontend" / "index.html").write_text("<h1>test</h1>", encoding="utf-8")
    (root / ".env").write_text("PORT=1\n", encoding="utf-8")
    (claude / "agents" / "ai-researcher.md").write_text(AGENT_MD, encoding="utf-8")
    (claude / "skills" / "deep-research" / "SKILL.md").write_text(SKILL_MD, encoding="utf-8")
    (knowledge / "ai" / "mo-hinh-ngon-ngu.md").write_text(KNOW_MD.format(date="2026-11-01"), encoding="utf-8")
    (knowledge / "ai" / "cu.md").write_text(
        KNOW_MD.format(date="2025-01-01").replace("Mô hình ngôn ngữ", "Cũ"), encoding="utf-8"
    )
    (knowledge / "_index.md").write_text("# Mục lục\n", encoding="utf-8")
    (knowledge / "_cho-duyet" / "ai--mo-hinh-ngon-ngu--2026-11-17.md").write_text(PROPOSAL_MD, encoding="utf-8")

    for mod in (config, agent_core, files):
        monkeypatch.setattr(mod, "PROJECT_ROOT", root, raising=False)
        monkeypatch.setattr(mod, "KNOWLEDGE_DIR", knowledge, raising=False)
        monkeypatch.setattr(mod, "CLAUDE_DIR", claude, raising=False)
        monkeypatch.setattr(mod, "AGENTS_DIR", claude / "agents", raising=False)
        monkeypatch.setattr(mod, "SKILLS_DIR", claude / "skills", raising=False)
        monkeypatch.setattr(mod, "PENDING_DIR", knowledge / "_cho-duyet", raising=False)
    return root


@pytest.fixture
def client(project: Path):
    settings = Settings(db_path=project / "backend" / "test.db", max_turns=20)
    app = create_app(settings=settings, check_env=False, frontend_dir=project / "frontend",
                     start_scheduler=False, config_path=project / "config.yaml")
    with TestClient(app) as c:
        yield c
