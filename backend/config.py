"""Đọc cấu hình app từ .env.

Chỉ chứa cấu hình app (PORT, MAX_DAILY_RUNS, MAX_TURNS...). Tuyệt đối không có
API key: app dùng tài khoản Claude đã đăng nhập (xem env_check.py).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
ENV_EXAMPLE = PROJECT_ROOT / ".env.example"
KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"
CLAUDE_DIR = PROJECT_ROOT / ".claude"
AGENTS_DIR = CLAUDE_DIR / "agents"
SKILLS_DIR = CLAUDE_DIR / "skills"
PENDING_DIR = KNOWLEDGE_DIR / "_cho-duyet"


def _load_dotenv() -> bool:
    """Nạp .env nếu có python-dotenv; trả về True khi file .env tồn tại."""
    if not ENV_FILE.exists():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:  # env_check sẽ báo thiếu thư viện
        return True
    load_dotenv(ENV_FILE, override=False)
    return True


def _int_env(name: str, default: int, warnings: list[str]) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        warnings.append(f"{name}={raw!r} không phải số nguyên, dùng mặc định {default}.")
        return default
    if value <= 0:
        warnings.append(f"{name}={value} phải lớn hơn 0, dùng mặc định {default}.")
        return default
    return value


@dataclass
class Settings:
    port: int = 8000
    max_daily_runs: int = 10
    max_turns: int = 50
    db_path: Path = PROJECT_ROOT / "backend" / "data.db"
    env_file_exists: bool = False
    warnings: list[str] = field(default_factory=list)

    project_root: Path = PROJECT_ROOT
    knowledge_dir: Path = KNOWLEDGE_DIR
    claude_dir: Path = CLAUDE_DIR


def load_settings() -> Settings:
    warnings: list[str] = []
    env_exists = _load_dotenv()
    db_raw = os.environ.get("DB_PATH", "").strip()
    db_path = (PROJECT_ROOT / db_raw) if db_raw else PROJECT_ROOT / "backend" / "data.db"
    return Settings(
        port=_int_env("PORT", 8000, warnings),
        max_daily_runs=_int_env("MAX_DAILY_RUNS", 10, warnings),
        max_turns=_int_env("MAX_TURNS", 50, warnings),
        db_path=db_path,
        env_file_exists=env_exists,
        warnings=warnings,
    )


def ensure_utf8_stdout() -> None:
    """Windows console mặc định không phải UTF-8; bật để in tiếng Việt."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
