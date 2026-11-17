"""Lưu lịch sử phiên chạy vào SQLite (aiosqlite).

Một phiên = một lần gọi run_research hoặc run_skill. Chi phí USD do SDK trả về
chỉ là ước tính; app dùng gói đăng ký Claude nên không bị tính tiền theo số này.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id                TEXT PRIMARY KEY,
    kind              TEXT NOT NULL,            -- research | skill
    prompt            TEXT NOT NULL,
    domain            TEXT,
    skill_name        TEXT,
    status            TEXT NOT NULL,            -- running | done | error
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    num_turns         INTEGER,
    duration_ms       INTEGER,
    cost_usd          REAL,                     -- ước tính từ SDK, có thể NULL
    sdk_session_id    TEXT,
    result_subtype    TEXT,
    error             TEXT,
    auth_method       TEXT,
    subscription_type TEXT
);
CREATE TABLE IF NOT EXISTS session_files (
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    path       TEXT NOT NULL,                   -- tương đối gốc dự án, dấu /
    action     TEXT NOT NULL,                   -- write | edit
    denied     INTEGER NOT NULL DEFAULT 0,      -- 1 nếu bị chặn
    UNIQUE (session_id, path, action, denied)
);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE TABLE IF NOT EXISTS auto_runs (
    id                 TEXT PRIMARY KEY,
    domain             TEXT NOT NULL,
    trigger            TEXT NOT NULL,           -- cron | manual
    started_at         TEXT NOT NULL,
    finished_at        TEXT,
    status             TEXT NOT NULL,           -- running | done | error | skipped
    step               TEXT,                    -- update | curate | commit
    message            TEXT,
    commit_hash        TEXT,
    update_session_id  TEXT,
    curate_session_id  TEXT
);
CREATE TABLE IF NOT EXISTS app_state (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class SessionStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    async def init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript(_SCHEMA)
            await db.commit()

    async def create_session(
        self,
        *,
        kind: str,
        prompt: str,
        domain: str | None = None,
        skill_name: str | None = None,
        auth_method: str | None = None,
        subscription_type: str | None = None,
    ) -> str:
        session_id = uuid.uuid4().hex
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT INTO sessions (id, kind, prompt, domain, skill_name, status,
                       started_at, auth_method, subscription_type)
                   VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)""",
                (session_id, kind, prompt, domain, skill_name, _now(), auth_method, subscription_type),
            )
            await db.commit()
        return session_id

    async def finish_session(self, session_id: str, *, status: str, **fields: Any) -> None:
        allowed = {
            "num_turns", "duration_ms", "cost_usd", "sdk_session_id",
            "result_subtype", "error",
        }
        cols = {k: v for k, v in fields.items() if k in allowed}
        cols["status"] = status
        cols["finished_at"] = _now()
        assignments = ", ".join(f"{k} = ?" for k in cols)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                f"UPDATE sessions SET {assignments} WHERE id = ?",
                (*cols.values(), session_id),
            )
            await db.commit()

    async def add_file(self, session_id: str, path: str, action: str, denied: bool = False) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO session_files (session_id, path, action, denied) VALUES (?, ?, ?, ?)",
                (session_id, path, action, 1 if denied else 0),
            )
            await db.commit()

    async def list_sessions(self, limit: int = 50) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            )
            sessions = [dict(r) for r in rows]
            if not sessions:
                return []
            ids = [s["id"] for s in sessions]
            placeholders = ",".join("?" * len(ids))
            files = await db.execute_fetchall(
                f"SELECT session_id, path, action, denied FROM session_files WHERE session_id IN ({placeholders})",
                ids,
            )
        by_session: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in sessions}
        for f in files:
            by_session[f["session_id"]].append(
                {"path": f["path"], "action": f["action"], "denied": bool(f["denied"])}
            )
        for s in sessions:
            s["files"] = by_session[s["id"]]
        return sessions

    # -- lịch tự động -----------------------------------------------------------

    async def create_auto_run(self, domain: str, trigger: str, status: str = "running",
                              message: str | None = None) -> str:
        run_id = uuid.uuid4().hex
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO auto_runs (id, domain, trigger, started_at, status, message) VALUES (?, ?, ?, ?, ?, ?)",
                (run_id, domain, trigger, _now(), status, message),
            )
            if status != "running":
                await db.execute("UPDATE auto_runs SET finished_at = ? WHERE id = ?", (_now(), run_id))
            await db.commit()
        return run_id

    async def update_auto_run(self, run_id: str, **fields: Any) -> None:
        allowed = {"status", "step", "message", "commit_hash", "update_session_id", "curate_session_id"}
        cols = {k: v for k, v in fields.items() if k in allowed}
        if cols.get("status") in ("done", "error", "skipped"):
            cols["finished_at"] = _now()
        if not cols:
            return
        assignments = ", ".join(f"{k} = ?" for k in cols)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE auto_runs SET {assignments} WHERE id = ?", (*cols.values(), run_id))
            await db.commit()

    async def list_auto_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            rows = await db.execute_fetchall(
                "SELECT * FROM auto_runs ORDER BY started_at DESC, rowid DESC LIMIT ?", (limit,)
            )
            return [dict(r) for r in rows]

    async def count_auto_runs_today(self) -> int:
        """Số lần chạy tự động đã thực sự bắt đầu hôm nay (không tính skipped)."""
        today = datetime.now(timezone.utc).astimezone().date().isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            row = await (await db.execute(
                "SELECT COUNT(*) FROM auto_runs WHERE substr(started_at, 1, 10) = ? AND status != 'skipped'",
                (today,),
            )).fetchone()
            return int(row[0]) if row else 0

    async def get_state(self, key: str, default: str | None = None) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            row = await (await db.execute("SELECT value FROM app_state WHERE key = ?", (key,))).fetchone()
            return row[0] if row else default

    async def set_state(self, key: str, value: str | None) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            if value is None:
                await db.execute("DELETE FROM app_state WHERE key = ?", (key,))
            else:
                await db.execute(
                    "INSERT INTO app_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            await db.commit()

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            row = await (await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))).fetchone()
            if row is None:
                return None
            files = await db.execute_fetchall(
                "SELECT path, action, denied FROM session_files WHERE session_id = ?", (session_id,)
            )
        session = dict(row)
        session["files"] = [
            {"path": f["path"], "action": f["action"], "denied": bool(f["denied"])} for f in files
        ]
        return session
