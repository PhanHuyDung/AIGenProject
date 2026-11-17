"""FastAPI app của AIGenProject.

Chạy:  uvicorn backend.main:app --reload --port 8000
hoặc:  python -m backend.main

App chỉ dành cho một người dùng trên máy cá nhân: bind 127.0.0.1, không có đăng
nhập web. Xác thực với Claude dùng tài khoản đã `claude login` (xem env_check.py).
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config as cfg
from .agent_core import AgentCore
from .api import claude_files, history, knowledge, proposals, research, scheduler as scheduler_api, status
from .api.deps import RunLock
from .config import Settings, ensure_utf8_stdout, load_settings
from .env_check import check_environment, format_report
from .scheduler import AutoUpdater


def create_app(settings: Settings | None = None, core: AgentCore | None = None,
               check_env: bool = True, frontend_dir: Path | None = None,
               start_scheduler: bool = True, config_path: Path | None = None) -> FastAPI:
    settings = settings or load_settings()
    core = core or AgentCore(settings)
    run_lock = RunLock()
    updater = AutoUpdater(core, run_lock, settings, config_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ensure_utf8_stdout()
        for w in settings.warnings:
            print("[Cảnh báo .env] " + w, file=sys.stderr)
        if check_env:
            report = check_environment(require_login=True)
            text = format_report(report)
            if text:
                print(text, file=sys.stderr)
            hard = [p for p in report.problems if p.level == "error" and "đăng nhập" not in p.message.lower()]
            if hard:
                raise RuntimeError(
                    "Môi trường chưa sẵn sàng (xem các lỗi ở trên). Chạy: python backend/cli.py --check"
                )
            if not report.ok:
                print("[Cảnh báo] Chưa đăng nhập Claude: API vẫn chạy nhưng không thể nghiên cứu "
                      "cho tới khi `claude login`.", file=sys.stderr)
        await core.store.init_db()
        if start_scheduler:
            await updater.start()
            for w in updater.config.warnings:
                print("[Cảnh báo config.yaml] " + w, file=sys.stderr)
        try:
            yield
        finally:
            await updater.stop()

    app = FastAPI(title="AIGenProject", version="0.7.0", lifespan=lifespan)

    @app.middleware("http")
    async def only_local_host(request, call_next):
        # App chỉ dành cho máy cá nhân: từ chối yêu cầu có header Host lạ (chống DNS rebinding).
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host and host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return JSONResponse(status_code=421, content={"detail": f"Host '{host}' không được phép; chỉ dùng 127.0.0.1 hoặc localhost."})
        return await call_next(request)
    app.state.settings = settings
    app.state.core = core
    app.state.run_lock = run_lock
    app.state.scheduler = updater
    app.state.skip_env_check = not check_env

    for r in (status.router, research.router, knowledge.router, claude_files.router,
              proposals.router, history.router, scheduler_api.router):
        app.include_router(r)

    fe = frontend_dir or (cfg.PROJECT_ROOT / "frontend")
    if fe.exists():
        app.mount("/", StaticFiles(directory=str(fe), html=True), name="frontend")
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=load_settings().port, reload=True)
