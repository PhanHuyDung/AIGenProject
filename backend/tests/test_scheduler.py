import asyncio
import subprocess
import textwrap

import pytest

from backend import scheduler as sch
from backend.agent_core import AgentCore
from backend.api.deps import RunLock
from backend.config import Settings


class FakeCore(AgentCore):
    """Giả lập AgentCore: không gọi Claude, phát sự kiện theo kịch bản."""

    def __init__(self, settings, script=None):
        super().__init__(settings)
        self.calls = []
        self.script = script or {}

    async def _fake(self, name, args):
        self.calls.append((name, args))
        events = self.script.get(name) or [
            {"type": "text", "data": {"kind": "init"}, "cost_usd": None},
            {"type": "done", "data": {"session_id": "s-" + name, "is_error": False, "num_turns": 2, "duration_ms": 1000,
                                      "files": [], "subtype": "success"}, "cost_usd": 0.01},
        ]
        for ev in events:
            yield ev

    def run_skill(self, skill_name, args="", max_turns=None, kind="skill"):
        return self._fake("skill:" + skill_name, args)

    def run_research(self, prompt, domain=None, max_turns=None, kind="research"):
        return self._fake("research", prompt)


def write_config(root, text):
    p = root / "config.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_load_config_validates(project):
    p = write_config(project, """
        scheduler:
          enabled: false
          max_turns: 7
          jobs:
            - domain: ai
              cron: "0 8 * * *"
            - domain: khong-co
              cron: "0 8 * * *"
            - domain: ai
              cron: "sai cron"
    """)
    conf = sch.load_config(p)
    assert conf.enabled is False and conf.max_turns == 7
    assert [j.domain for j in conf.jobs] == ["ai"]
    assert len(conf.warnings) == 2


def test_load_config_missing(project):
    conf = sch.load_config(project / "khong-co.yaml")
    assert conf.jobs == [] and conf.warnings


def test_is_usage_limit():
    assert sch.is_usage_limit({"type": "error", "data": {"message": "Đã chạm giới hạn sử dụng của gói Claude."}})
    assert sch.is_usage_limit({"type": "done", "data": {"is_error": True, "api_error_status": 429}})
    assert not sch.is_usage_limit({"type": "done", "data": {"is_error": False}})
    assert not sch.is_usage_limit({"type": "error", "data": {"message": "lỗi khác"}})


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)


def test_git_commit_knowledge(project):
    assert _git(project, "init", "-q").returncode == 0
    _git(project, "config", "user.email", "t@example.com"); _git(project, "config", "user.name", "t")
    _git(project, "add", "-A"); _git(project, "commit", "-q", "-m", "init")
    sha, msg = sch.git_commit_knowledge("ai", project)
    assert sha is None and "Không có thay đổi" in msg
    (project / "knowledge" / "ai" / "moi.md").write_text("# x", encoding="utf-8")
    (project / "backend" / "khong-commit.txt").write_text("x", encoding="utf-8")
    sha, msg = sch.git_commit_knowledge("ai", project)
    assert sha and "auto-update ai" in msg
    assert "khong-commit" not in _git(project, "show", "--stat", "HEAD").stdout
    assert _git(project, "status", "--porcelain").stdout.strip().startswith("?? backend/")


def _updater(project, core, max_daily=5, git=False):
    write_config(project, f"""
        scheduler:
          enabled: true
          git_commit: {str(git).lower()}
          jobs:
            - domain: ai
              cron: "0 8 * * *"
    """)
    settings = Settings(db_path=project / "backend" / "t.db", max_daily_runs=max_daily, max_turns=20)
    core = core or FakeCore(settings)
    return sch.AutoUpdater(core, RunLock(), settings, project / "config.yaml"), core


def test_run_domain_full_cycle_and_daily_limit(project):
    up, core = _updater(project, None, max_daily=1)
    r = asyncio.run(up.run_domain("ai", trigger="manual"))
    assert r["status"] == "done", r
    assert [c[0] for c in core.calls] == ["skill:update-knowledge", "research"]
    assert core.calls[0][1] == "knowledge/ai/"
    assert "knowledge-curator" in core.calls[1][1]
    assert up.lock.busy is False
    r2 = asyncio.run(up.run_domain("ai", trigger="cron"))
    assert r2["status"] == "skipped" and "MAX_DAILY_RUNS" in r2["message"]
    runs = asyncio.run(core.store.list_auto_runs())
    assert [x["status"] for x in runs] == ["skipped", "done"]
    assert asyncio.run(core.store.count_auto_runs_today()) == 1


def test_run_domain_skips_when_disabled_or_busy(project):
    up, core = _updater(project, None)
    asyncio.run(up.set_enabled(False))
    assert asyncio.run(up.run_domain("ai", trigger="cron"))["status"] == "skipped"
    # thủ công vẫn chạy khi lịch tắt
    assert asyncio.run(up.run_domain("ai", trigger="manual"))["status"] == "done"
    up.lock.try_acquire({"kind": "test"})
    try:
        assert "phiên khác" in asyncio.run(up.run_domain("ai", trigger="manual"))["message"]
    finally:
        up.lock.release()
    assert asyncio.run(up.run_domain("khong-co", trigger="manual"))["status"] == "skipped"


def test_run_domain_usage_limit_stops(project):
    settings = Settings(db_path=project / "backend" / "t.db", max_daily_runs=5, max_turns=20)
    core = FakeCore(settings, script={"skill:update-knowledge": [
        {"type": "error", "data": {"message": "Đã chạm giới hạn sử dụng của gói Claude.", "session_id": "s1"}, "cost_usd": None}]})
    up, _ = _updater(project, core)
    r = asyncio.run(up.run_domain("ai", trigger="cron"))
    assert r["status"] == "error" and "giới hạn sử dụng" in r["message"]
    assert up.last_limit_hit is not None
    assert [c[0] for c in core.calls] == ["skill:update-knowledge"]  # không chạy curator
    assert up.lock.busy is False


def test_scheduler_api(client, project):
    write_config(project, """
        scheduler:
          jobs:
            - domain: ai
              cron: "30 6 * * mon"
    """)
    up = client.app.state.scheduler
    up.config = sch.load_config(project / "config.yaml")
    s = client.get("/api/scheduler").json()
    assert s["jobs"][0]["domain"] == "ai" and s["jobs"][0]["cron"] == "30 6 * * mon"
    assert s["max_daily_runs"] == 10 or s["max_daily_runs"] > 0
    s = client.post("/api/scheduler/toggle", json={"enabled": False}).json()
    assert s["enabled"] is False
    assert client.get("/api/scheduler").json()["enabled"] is False
    assert client.get("/api/scheduler/runs").json() == []
    assert client.post("/api/scheduler/run/khong-co").status_code == 404
