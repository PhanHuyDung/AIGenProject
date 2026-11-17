"""Lịch tự động cập nhật kiến thức (APScheduler, chạy trong vòng lặp của FastAPI).

Mỗi lần chạy một lĩnh vực:
  1. skill update-knowledge cho knowledge/<domain>/
  2. agent knowledge-curator dọn trùng lặp, đánh dấu cũ, cập nhật _index.md
  3. git commit knowledge/ và .claude/ với message "auto-update <domain> <ngày>"

Giới hạn: MAX_DAILY_RUNS lần chạy mỗi ngày (đếm trong SQLite), max_turns mỗi phiên,
chỉ một phiên Claude tại một thời điểm (dùng chung RunLock với API). Gặp lỗi hết
giới hạn sử dụng (rate/usage limit) thì dừng lần chạy, ghi log, lần chạy kế tiếp
theo lịch sẽ thử lại. Mọi đề xuất chưa chắc chắn vẫn chờ người dùng duyệt.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config as cfg
from .agent_core import AgentCore, list_domains
from .config import Settings

log = logging.getLogger("aigen.scheduler")

USAGE_LIMIT_MARKERS = ("giới hạn sử dụng", "rate limit", "usage limit", "hit your limit", "max_budget")
STATE_ENABLED = "scheduler.enabled"


@dataclass
class Job:
    domain: str
    cron: str
    label: str = ""


@dataclass
class SchedulerConfig:
    enabled: bool = True
    timezone: str | None = None
    max_turns: int = 30
    git_commit: bool = True
    jobs: list[Job] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def load_config(path: Path) -> SchedulerConfig:
    """Đọc config.yaml; cron sai hoặc lĩnh vực không có agent → cảnh báo, bỏ job đó."""
    conf = SchedulerConfig()
    if not path.exists():
        conf.warnings.append(f"Không có {path.name}; lịch tự động không có job nào.")
        return conf
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        conf.warnings.append(f"{path.name} không đọc được: {exc}")
        return conf
    s = data.get("scheduler") or {}
    conf.enabled = bool(s.get("enabled", True))
    conf.timezone = s.get("timezone") or None
    conf.git_commit = bool(s.get("git_commit", True))
    try:
        conf.max_turns = max(1, int(s.get("max_turns", 30)))
    except (TypeError, ValueError):
        conf.warnings.append("max_turns không phải số, dùng 30.")
    known = set(list_domains())
    for raw in s.get("jobs") or []:
        domain = str(raw.get("domain", "")).strip()
        cron = str(raw.get("cron", "")).strip()
        if not domain or not cron:
            conf.warnings.append(f"Job thiếu domain hoặc cron: {raw}")
            continue
        try:
            CronTrigger.from_crontab(cron)
        except ValueError as exc:
            conf.warnings.append(f"Cron '{cron}' của {domain} không hợp lệ: {exc}")
            continue
        if known and domain not in known:
            conf.warnings.append(f"Lĩnh vực '{domain}' chưa có agent *-researcher; bỏ qua job.")
            continue
        conf.jobs.append(Job(domain=domain, cron=cron, label=str(raw.get("label", "") or "")))
    return conf


def is_usage_limit(ev: dict[str, Any]) -> bool:
    d = ev.get("data") or {}
    if ev.get("type") == "error":
        msg = str(d.get("message", "")).lower()
        return any(m in msg for m in USAGE_LIMIT_MARKERS)
    if ev.get("type") == "done" and d.get("is_error"):
        if d.get("api_error_status") == 429:
            return True
        text = " ".join([str(d.get("subtype", "")), *(d.get("errors") or [])]).lower()
        return any(m in text for m in USAGE_LIMIT_MARKERS)
    return False


def git_commit_knowledge(domain: str, root: Path | None = None) -> tuple[str | None, str]:
    """Commit knowledge/ và .claude/ nếu có thay đổi. Trả về (hash, thông điệp)."""
    root = root or cfg.PROJECT_ROOT
    run = lambda *args: subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=60)  # noqa: E731
    if run("rev-parse", "--is-inside-work-tree").returncode != 0:
        return None, "Không phải kho git, bỏ qua commit."
    add = run("add", "-A", "--", "knowledge", ".claude")
    if add.returncode != 0:
        return None, "git add lỗi: " + (add.stderr or add.stdout).strip()
    if run("diff", "--cached", "--quiet", "--", "knowledge", ".claude").returncode == 0:
        return None, "Không có thay đổi trong knowledge/ và .claude/."
    msg = f"auto-update {domain} {date.today().isoformat()}"
    commit = run("commit", "-m", msg, "--", "knowledge", ".claude")
    if commit.returncode != 0:
        return None, "git commit lỗi: " + (commit.stderr or commit.stdout).strip()
    sha = run("rev-parse", "--short", "HEAD").stdout.strip()
    return sha, f"Đã commit {sha}: {msg}"


class AutoUpdater:
    def __init__(self, core: AgentCore, lock: Any, settings: Settings, config_path: Path | None = None):
        self.core = core
        self.lock = lock
        self.settings = settings
        self.config_path = config_path or (cfg.PROJECT_ROOT / "config.yaml")
        self.config = load_config(self.config_path)
        self.scheduler: AsyncIOScheduler | None = None
        self.enabled = self.config.enabled
        self.current: dict[str, Any] | None = None
        self.last_limit_hit: str | None = None
        self._tasks: set[asyncio.Task] = set()
        self._log_handler_added = False

    # -- vòng đời ---------------------------------------------------------------

    def _setup_logging(self) -> None:
        if self._log_handler_added:
            return
        log.setLevel(logging.INFO)
        path = self.settings.db_path.parent / "scheduler.log"
        try:
            h = logging.FileHandler(path, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(h)
        except OSError:
            pass
        self._log_handler_added = True

    async def start(self) -> None:
        self._setup_logging()
        await self.core._ensure_db()
        saved = await self.core.store.get_state(STATE_ENABLED)
        if saved is not None:
            self.enabled = saved == "1"
        for w in self.config.warnings:
            log.warning("config.yaml: %s", w)
        self.scheduler = AsyncIOScheduler(timezone=self.config.timezone) if self.config.timezone else AsyncIOScheduler()
        for job in self.config.jobs:
            self.scheduler.add_job(
                self._cron_fire, CronTrigger.from_crontab(job.cron, timezone=self.config.timezone),
                args=[job.domain], id=f"auto:{job.domain}", name=job.domain,
                misfire_grace_time=3600, coalesce=True, max_instances=1,
            )
        self.scheduler.start()
        log.info("Lịch tự động khởi động: %d job, enabled=%s, MAX_DAILY_RUNS=%d",
                 len(self.config.jobs), self.enabled, self.settings.max_daily_runs)

    async def stop(self) -> None:
        if self.scheduler and self.scheduler.running:
            self.scheduler.shutdown(wait=False)
        for t in list(self._tasks):
            t.cancel()

    async def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)
        await self.core._ensure_db()
        await self.core.store.set_state(STATE_ENABLED, "1" if enabled else "0")
        log.info("Lịch tự động %s bởi người dùng", "BẬT" if enabled else "TẮT")

    # -- trạng thái -------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        await self.core._ensure_db()
        runs = await self.core.store.list_auto_runs(limit=200)
        last_by_domain: dict[str, dict[str, Any]] = {}
        for r in runs:
            last_by_domain.setdefault(r["domain"], r)
        jobs = []
        for job in self.config.jobs:
            nxt = None
            if self.scheduler:
                j = self.scheduler.get_job(f"auto:{job.domain}")
                if j and j.next_run_time:
                    nxt = j.next_run_time.isoformat(timespec="minutes")
            jobs.append({"domain": job.domain, "cron": job.cron, "label": job.label,
                         "next_run": nxt if self.enabled else None, "last_run": last_by_domain.get(job.domain)})
        return {
            "enabled": self.enabled,
            "running": self.current,
            "today_count": await self.core.store.count_auto_runs_today(),
            "max_daily_runs": self.settings.max_daily_runs,
            "max_turns": min(self.config.max_turns, self.settings.max_turns),
            "git_commit": self.config.git_commit,
            "timezone": self.config.timezone,
            "last_limit_hit": self.last_limit_hit,
            "config_warnings": self.config.warnings,
            "scheduler_alive": bool(self.scheduler and self.scheduler.running),
            "jobs": jobs,
        }

    # -- chạy -------------------------------------------------------------------

    async def _cron_fire(self, domain: str) -> None:
        await self.run_domain(domain, trigger="cron")

    def run_in_background(self, domain: str, trigger: str = "manual") -> asyncio.Task:
        task = asyncio.create_task(self.run_domain(domain, trigger=trigger))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def run_domain(self, domain: str, trigger: str = "cron") -> dict[str, Any]:
        """Chạy một lượt cập nhật cho lĩnh vực. Trả về bản ghi auto_run (dict)."""
        store = self.core.store
        await self.core._ensure_db()

        async def skip(reason: str) -> dict[str, Any]:
            log.info("[%s] bỏ qua (%s): %s", domain, trigger, reason)
            rid = await store.create_auto_run(domain, trigger, status="skipped", message=reason)
            return {"id": rid, "domain": domain, "status": "skipped", "message": reason}

        if trigger == "cron" and not self.enabled:
            return await skip("Lịch tự động đang tắt.")
        if domain not in list_domains():
            return await skip(f"Lĩnh vực '{domain}' không có agent.")
        today = await store.count_auto_runs_today()
        if today >= self.settings.max_daily_runs:
            return await skip(f"Đã đạt giới hạn {self.settings.max_daily_runs} lần chạy tự động hôm nay (MAX_DAILY_RUNS).")
        if self.lock.busy:
            return await skip("Đang có phiên khác chạy.")
        try:
            self.lock.try_acquire({"kind": "auto-update", "domain": domain, "trigger": trigger})
        except Exception as exc:  # HTTPException từ RunLock
            return await skip(f"Không lấy được khoá: {exc}")

        turns = min(self.config.max_turns, self.settings.max_turns)
        run_id = await store.create_auto_run(domain, trigger)
        self.current = {"id": run_id, "domain": domain, "trigger": trigger, "step": "update"}
        log.info("[%s] bắt đầu (%s), run %s, max_turns=%d", domain, trigger, run_id, turns)
        status, message, commit_hash = "done", "", None
        try:
            # 1. update-knowledge
            await store.update_auto_run(run_id, step="update")
            ok, msg, sid = await self._consume(
                self.core.run_skill("update-knowledge", f"knowledge/{domain}/", max_turns=turns, kind="auto-update"))
            await store.update_auto_run(run_id, update_session_id=sid)
            if not ok:
                raise _StepFailed("update", msg)

            # 2. knowledge-curator
            self.current["step"] = "curate"
            await store.update_auto_run(run_id, step="curate")
            prompt = (
                f"Chạy tự động theo lịch. Giao việc cho subagent `knowledge-curator` dọn kho kiến thức, chỉ trong "
                f"thư mục knowledge/{domain}/ và knowledge/_cho-duyet/: kiểm tra frontmatter, đánh dấu file quá 90 ngày, "
                f"gộp trùng lặp, cập nhật knowledge/_index.md theo đúng hướng dẫn của agent. Không tìm web. "
                f"Không tự duyệt hay áp dụng đề xuất. Báo cáo ngắn gọn, nêu số đề xuất đang chờ duyệt."
            )
            ok, msg, sid = await self._consume(self.core.run_research(prompt, max_turns=turns, kind="auto-curate"))
            await store.update_auto_run(run_id, curate_session_id=sid)
            if not ok:
                raise _StepFailed("curate", msg)

            # 3. git commit
            self.current["step"] = "commit"
            await store.update_auto_run(run_id, step="commit")
            if self.config.git_commit:
                commit_hash, msg = await asyncio.to_thread(git_commit_knowledge, domain)
                message = msg
            else:
                message = "Bỏ qua git commit (git_commit: false)."
            log.info("[%s] xong: %s", domain, message)
        except _StepFailed as exc:
            status, message = "error", f"Lỗi ở bước {exc.step}: {exc.message}"
            if exc.usage_limit:
                self.last_limit_hit = datetime.now().astimezone().isoformat(timespec="seconds")
                message += " Đã chạm giới hạn sử dụng của gói Claude; dừng lần chạy này, lần chạy kế tiếp theo lịch sẽ thử lại."
            log.error("[%s] %s", domain, message)
        except asyncio.CancelledError:
            status, message = "error", "Bị huỷ khi app dừng."
            raise
        except Exception as exc:  # noqa: BLE001
            status, message = "error", f"Lỗi không mong đợi: {exc}"
            log.exception("[%s] lỗi", domain)
        finally:
            self.lock.release()
            self.current = None
            await store.update_auto_run(run_id, status=status, message=message, commit_hash=commit_hash)
        return {"id": run_id, "domain": domain, "status": status, "message": message, "commit_hash": commit_hash}

    async def _consume(self, stream) -> tuple[bool, str, str | None]:
        """Chạy hết một stream sự kiện. Trả về (thành công, thông điệp, session_id)."""
        sid = None
        last_error = None
        done = None
        async for ev in stream:
            if ev["type"] == "done":
                done = ev
                sid = ev["data"].get("session_id")
            elif ev["type"] == "error":
                last_error = ev
                sid = ev["data"].get("session_id", sid)
            if is_usage_limit(ev):
                raise _StepFailed("", str(ev["data"].get("message") or ev["data"].get("errors") or "usage limit"), usage_limit=True)
        if last_error is not None:
            return False, str(last_error["data"].get("message", "lỗi")), sid
        if done is None:
            return False, "Phiên kết thúc mà không có kết quả.", sid
        d = done["data"]
        if d.get("is_error"):
            return False, f"{d.get('subtype')}: {'; '.join(d.get('errors') or [])}", sid
        return True, f"{d.get('num_turns')} lượt, {d.get('duration_ms', 0) / 1000:.0f}s, {len(d.get('files') or [])} file", sid


class _StepFailed(Exception):
    def __init__(self, step: str, message: str, usage_limit: bool = False):
        super().__init__(message)
        self.step, self.message, self.usage_limit = step, message, usage_limit
