import asyncio

from backend.db import SessionStore


def test_status_without_env_check(client):
    r = client.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["pending_proposals"] == 1 and body["busy"] is False
    assert body["settings"]["max_turns"] == 20


def test_static_index(client):
    r = client.get("/")
    assert r.status_code == 200 and "test" in r.text


def test_knowledge_tree_and_read(client):
    assert client.get("/api/knowledge").json()["type"] == "dir"
    r = client.get("/api/knowledge/ai/mo-hinh-ngon-ngu.md")
    assert r.status_code == 200
    assert r.json()["frontmatter"]["domain"] == "ai"
    assert client.get("/api/knowledge/knowledge/ai/mo-hinh-ngon-ngu.md").status_code == 200
    assert client.get("/api/knowledge/ai/khong-co.md").status_code == 404
    assert client.get("/api/knowledge/search?q=transformer").json()["results"]


def test_knowledge_traversal_blocked(client):
    for p in ["../backend/agent_core.py", "..%2Fbackend%2Fagent_core.py",
              "knowledge/../.claude/agents/ai-researcher.md"]:
        r = client.get(f"/api/knowledge/{p}")
        assert r.status_code in (400, 403, 404), p
    # endpoint knowledge chỉ đọc trong knowledge/
    assert client.get("/api/knowledge/.claude/agents/ai-researcher.md").status_code in (400, 403, 404)


def test_agents_and_skills(client):
    agents = client.get("/api/agents").json()
    assert agents[0]["name"] == "ai-researcher" and agents[0]["domain"] == "ai"
    skills = client.get("/api/skills").json()
    assert skills[0]["name"] == "deep-research"


def test_files_get_put(client):
    r = client.get("/api/files/.claude/agents/ai-researcher.md")
    assert r.status_code == 200 and r.json()["frontmatter"]["name"] == "ai-researcher"
    new = r.json()["content"].replace("Nghiên cứu AI", "Nghiên cứu AI sâu")
    r = client.put("/api/files/.claude/agents/ai-researcher.md", json={"content": new})
    assert r.status_code == 200
    assert "sâu" in client.get("/api/files/.claude/agents/ai-researcher.md").json()["content"]
    # frontmatter hỏng
    assert client.put("/api/files/.claude/agents/ai-researcher.md",
                      json={"content": "khong co frontmatter"}).status_code == 422
    # ngoài phạm vi
    assert client.put("/api/files/backend/x.md", json={"content": "x"}).status_code == 403
    # client chuẩn hoá ../ → route khác (405); dạng mã hoá đi tới handler và bị safe_resolve chặn
    assert client.put("/api/files/../README.md", json={"content": "x"}).status_code in (400, 403, 404, 405)
    assert client.put("/api/files/..%2FREADME.md", json={"content": "x"}).status_code in (400, 403)
    assert client.put("/api/files/knowledge%2F..%2Fbackend%2Fx.md", json={"content": "x"}).status_code in (400, 403)
    assert client.put("/api/files/knowledge/.env", json={"content": "x"}).status_code == 403
    assert client.put("/api/files/knowledge/ai/a.py", json={"content": "x"}).status_code == 415
    # ghi file kiến thức mới
    assert client.put("/api/files/knowledge/ai/moi.md", json={"content": "# moi"}).status_code == 200


def test_proposals_list_reject(client):
    ps = client.get("/api/proposals?status=cho-duyet").json()
    assert len(ps) == 1 and len(ps[0]["items"]) == 2
    pid = ps[0]["id"]
    assert client.get(f"/api/proposals/{pid}").status_code == 200
    assert client.get("/api/proposals/khong-co").status_code == 404
    assert client.get("/api/proposals/..%2Fx").status_code in (400, 404)
    r = client.post(f"/api/proposals/{pid}/reject", json={"note": "thiếu nguồn"})
    assert r.status_code == 200 and r.json()["status"] == "tu-choi"
    assert client.post(f"/api/proposals/{pid}/reject", json={}).status_code == 409
    assert client.post(f"/api/proposals/{pid}/approve", json={}).status_code == 409
    assert client.get("/api/proposals?status=cho-duyet").json() == []
    assert client.get("/api/proposals?status=sai").status_code == 400


def test_approve_validation_without_claude(client):
    pid = client.get("/api/proposals").json()[0]["id"]
    assert client.post(f"/api/proposals/{pid}/approve", json={"items": [9]}).status_code == 400
    # đang bận → 409, status không đổi
    lock = client.app.state.run_lock
    lock.try_acquire({"kind": "test"})
    try:
        assert client.post(f"/api/proposals/{pid}/approve", json={}).status_code == 409
        assert client.post("/api/research", json={"prompt": "x"}).status_code == 409
        assert client.post("/api/skills/deep-research/run", json={"args": "x"}).status_code == 409
    finally:
        lock.release()
    assert client.get(f"/api/proposals/{pid}").json()["status"] == "cho-duyet"


def test_research_validation(client):
    assert client.post("/api/research", json={"prompt": ""}).status_code == 422
    assert client.post("/api/research", json={"prompt": "   "}).status_code == 422
    r = client.post("/api/research", json={"prompt": "x", "domain": "khong-co"})
    assert r.status_code == 400 and r.json()["detail"]["domains"] == ["ai"]
    r = client.post("/api/skills/khong-co/run", json={"args": ""})
    assert r.status_code == 404 and r.json()["detail"]["skills"] == ["deep-research"]
    assert client.app.state.run_lock.busy is False


def test_history(client, project):
    assert client.get("/api/history").json() == []
    store = SessionStore(project / "backend" / "test.db")

    async def seed():
        sid = await store.create_session(kind="research", prompt="hỏi", domain="ai")
        await store.finish_session(sid, status="done", num_turns=2, duration_ms=1000, cost_usd=0.1)
        await store.add_file(sid, "knowledge/ai/x.md", "write")
        return sid

    sid = asyncio.run(seed())
    hist = client.get("/api/history").json()
    assert hist[0]["id"] == sid and hist[0]["files"][0]["path"] == "knowledge/ai/x.md"
    assert client.get(f"/api/history/{sid}").json()["num_turns"] == 2
    assert client.get("/api/history/khong-co").status_code == 404
