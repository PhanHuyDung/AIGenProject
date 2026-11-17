import pytest
from fastapi import HTTPException

from backend import files


@pytest.mark.parametrize("rel", [
    "../backend/x.py", "knowledge/../backend/x.py", "/etc/passwd", "C:/Windows/x", "knowledge//a.md",
    "knowledge/./a.md", "backend/agent_core.py", "frontend/index.html", "", "knowledge/.env",
    "knowledge/.env.local",
])
def test_safe_resolve_rejects(project, rel):
    with pytest.raises(HTTPException) as e:
        files.safe_resolve(rel)
    assert e.value.status_code in (400, 403)


def test_safe_resolve_allows(project):
    assert files.safe_resolve("knowledge/ai/mo-hinh-ngon-ngu.md").exists()
    assert files.safe_resolve(".claude/agents/ai-researcher.md").exists()
    assert files.safe_resolve("knowledge\\ai\\mo-hinh-ngon-ngu.md").exists()


def test_claude_dir_writes_restricted(project):
    from backend.agent_core import is_path_allowed
    assert is_path_allowed(".claude/agents/x.md")[0]
    assert is_path_allowed(".claude/skills/x/SKILL.md")[0]
    assert is_path_allowed(".claude/skills/x/mau.md")[0]
    for bad in [".claude/settings.json", ".claude/settings.local.json", ".claude/hooks/run.sh",
                ".claude/agents", ".claude/x.md", ".claude/skills/x/run.py", ".claude/agents/a.json"]:
        ok, why = is_path_allowed(bad)
        assert not ok, bad
        assert why
    with pytest.raises(HTTPException) as e:
        files.write_text(".claude/settings.json", "{}")
    assert e.value.status_code == 403


def test_host_header_guard(client):
    assert client.get("/api/status", headers={"host": "evil.example"}).status_code == 421
    assert client.get("/api/status", headers={"host": "localhost:8000"}).status_code == 200


def test_write_text_only_text_types(project):
    with pytest.raises(HTTPException) as e:
        files.write_text("knowledge/ai/x.py", "print(1)")
    assert e.value.status_code == 415
    p = files.write_text("knowledge/ai/moi.md", "# a")
    assert p.read_text(encoding="utf-8") == "# a"


def test_knowledge_tree_and_stale(project):
    tree = files.knowledge_tree()
    names = {c["name"] for c in tree["children"]}
    assert {"ai", "game", "_cho-duyet", "_index.md"} <= names
    game = next(c for c in tree["children"] if c["name"] == "game")
    assert game["children"] == []  # .gitkeep bị bỏ
    pending = next(c for c in tree["children"] if c["name"] == "_cho-duyet")
    assert pending["system"] is True
    ai = next(c for c in tree["children"] if c["name"] == "ai")
    by_name = {c["name"]: c["meta"] for c in ai["children"]}
    assert by_name["cu.md"]["stale"] is True
    assert by_name["mo-hinh-ngon-ngu.md"]["title"] == "Mô hình ngôn ngữ"


def test_search(project):
    res = files.search_knowledge("transformer")
    assert res and res[0]["path"].startswith("knowledge/ai/")
    assert files.search_knowledge("khong-co-gi") == []


def test_proposals_parse_and_status(project):
    ps = files.list_proposals()
    assert len(ps) == 1
    p = ps[0]
    assert p.status == "cho-duyet" and p.target_exists
    assert [it["index"] for it in p.items] == [1, 2]
    assert p.items[0]["location"] == "Chi tiết"
    p2 = files.set_proposal_status(p.id, "tu-choi", "không đủ nguồn")
    assert p2.status == "tu-choi" and p2.decided and p2.decision_note == "không đủ nguồn"
    assert files.list_proposals("cho-duyet") == []
    p3 = files.set_proposal_status(p.id, "cho-duyet")
    assert p3.status == "cho-duyet" and p3.decided is None
