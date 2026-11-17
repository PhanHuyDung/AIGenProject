"""Kiểm tra môi trường trước khi chạy app.

Code được clone về nhiều máy khác nhau, nên mọi thứ cần thiết (Python, thư viện,
Claude Code CLI, đăng nhập) đều được kiểm tra ở đây và in hướng dẫn cài bằng
tiếng Việt thay vì để lỗi khó hiểu.

Xác thực: app chỉ dùng tài khoản Claude đã đăng nhập (`claude login`). Các biến
môi trường có thể làm SDK chuyển sang API key hay nhà cung cấp khác (và tính
tiền ngoài gói đăng ký) được gỡ khỏi tiến trình trước khi gọi SDK.

Module này KHÔNG import claude_agent_sdk ở cấp module, để `python backend/cli.py`
vẫn in được hướng dẫn khi chưa `pip install -r requirements.txt`.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .config import ENV_EXAMPLE, ENV_FILE, PROJECT_ROOT

MIN_PYTHON = (3, 10)

# Biến môi trường làm Claude Code / SDK dùng nguồn xác thực khác tài khoản đăng
# nhập. Thứ tự ưu tiên xác thực của Claude Code đặt đăng nhập claude.ai ở cuối,
# nên chỉ cần một biến trong số này tồn tại là phiên chạy không còn dùng gói
# đăng ký. (Nguồn: code.claude.com/docs/en/authentication, mục precedence.)
BILLING_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "ANTHROPIC_PROFILE",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
)

REQUIRED_MODULES = {
    "claude_agent_sdk": "claude-agent-sdk",
    "dotenv": "python-dotenv",
    "aiosqlite": "aiosqlite",
}

IS_WINDOWS = platform.system() == "Windows"


@dataclass
class Problem:
    level: Literal["error", "warning"]
    message: str
    fix: str = ""


@dataclass
class Report:
    problems: list[Problem] = field(default_factory=list)
    cli_path: str | None = None
    cli_version: str | None = None
    auth: dict[str, Any] | None = None
    removed_env: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(p.level == "error" for p in self.problems)

    @property
    def auth_method(self) -> str | None:
        return (self.auth or {}).get("authMethod")

    @property
    def subscription_type(self) -> str | None:
        return (self.auth or {}).get("subscriptionType")

    def error(self, message: str, fix: str = "") -> None:
        self.problems.append(Problem("error", message, fix))

    def warning(self, message: str, fix: str = "") -> None:
        self.problems.append(Problem("warning", message, fix))


def _venv_hint() -> str:
    if IS_WINDOWS:
        return (
            "python -m venv .venv\n"
            "    .venv\\Scripts\\Activate.ps1      (PowerShell; CMD: .venv\\Scripts\\activate.bat)\n"
            "    pip install -r requirements.txt"
        )
    return "python3 -m venv .venv\n    source .venv/bin/activate\n    pip install -r requirements.txt"


def _in_project_venv() -> bool:
    venv_dir = PROJECT_ROOT / ".venv"
    try:
        return venv_dir.exists() and Path(sys.prefix).resolve() == venv_dir.resolve()
    except OSError:
        return False


def check_python(report: Report) -> None:
    if sys.version_info < MIN_PYTHON:
        report.error(
            f"Python {platform.python_version()} quá cũ; cần Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} trở lên.",
            "Cài Python mới từ https://www.python.org/downloads/"
            + (" hoặc: winget install Python.Python.3.12" if IS_WINDOWS else ""),
        )


def check_modules(report: Report) -> None:
    missing = [pkg for mod, pkg in REQUIRED_MODULES.items() if importlib.util.find_spec(mod) is None]
    if not missing:
        return
    hint = _venv_hint()
    if (PROJECT_ROOT / ".venv").exists() and not _in_project_venv():
        hint = (
            "Đang chạy bằng Python ngoài .venv của dự án. Kích hoạt .venv rồi chạy lại:\n    "
            + (".venv\\Scripts\\Activate.ps1" if IS_WINDOWS else "source .venv/bin/activate")
            + "\n  Hoặc cài lại:\n    " + hint
        )
    report.error(
        "Thiếu thư viện Python: " + ", ".join(missing) + ".",
        hint,
    )


def find_claude_cli() -> tuple[str | None, str | None]:
    """Tìm Claude Code CLI. Trả về (đường dẫn, nguồn).

    Ưu tiên bản kèm trong gói claude-agent-sdk (SDK cũng tự dùng bản này).
    Trên Windows bỏ qua shim `claude.cmd` của npm vì SDK từ chối chạy file .cmd.
    """
    spec = importlib.util.find_spec("claude_agent_sdk")
    if spec and spec.origin:
        name = "claude.exe" if IS_WINDOWS else "claude"
        bundled = Path(spec.origin).parent / "_bundled" / name
        if bundled.is_file():
            return str(bundled), "bundled"

    if IS_WINDOWS:
        for directory in os.environ.get("PATH", "").split(os.pathsep):
            exe = Path(directory) / "claude.exe"
            if directory and Path(directory).is_absolute() and exe.is_file():
                return str(exe), "path"
        native = Path.home() / ".local" / "bin" / "claude.exe"
        if native.is_file():
            return str(native), "native"
        return None, None

    found = shutil.which("claude")
    if found:
        return found, "path"
    for candidate in (
        Path.home() / ".local/bin/claude",
        Path.home() / ".npm-global/bin/claude",
        Path("/usr/local/bin/claude"),
        Path.home() / ".claude/local/claude",
    ):
        if candidate.is_file():
            return str(candidate), "native"
    return None, None


def check_cli(report: Report) -> None:
    cli, source = find_claude_cli()
    if cli is None:
        if IS_WINDOWS:
            fix = (
                "Cách 1 (khuyên dùng): cài lại gói pip để có bản CLI kèm theo:\n"
                "    pip install --force-reinstall claude-agent-sdk\n"
                "  Cách 2: cài Claude Code bản native (PowerShell):\n"
                "    irm https://claude.ai/install.ps1 | iex\n"
                "  Lưu ý: bản cài qua npm tạo shim claude.cmd, SDK không chạy được file này."
            )
        else:
            fix = (
                "Cài Claude Code: curl -fsSL https://claude.ai/install.sh | bash\n"
                "  hoặc: npm install -g @anthropic-ai/claude-code (cần Node.js)"
            )
        report.error("Không tìm thấy Claude Code CLI (claude).", fix)
        return
    report.cli_path = cli
    try:
        out = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=30)
        report.cli_version = (out.stdout or out.stderr).strip() or None
    except (OSError, subprocess.TimeoutExpired) as exc:
        report.warning(f"Không chạy được `claude --version` ({exc}).")
    if source != "bundled":
        report.warning(
            f"Dùng Claude CLI ngoài gói SDK: {cli}. SDK sẽ ưu tiên bản kèm theo gói nếu có.",
        )


def scrub_billing_env() -> list[str]:
    """Gỡ các biến làm SDK không dùng tài khoản đăng nhập. Trả về danh sách đã gỡ.

    Chỉ ảnh hưởng tiến trình hiện tại và tiến trình con, không đụng tới cấu hình
    hệ thống của người dùng.
    """
    removed = []
    for name in BILLING_ENV_VARS:
        if name in os.environ:
            os.environ.pop(name, None)
            removed.append(name)
    return removed


def check_env_vars(report: Report) -> None:
    removed = scrub_billing_env()
    report.removed_env = removed
    if removed:
        report.warning(
            "Phát hiện biến môi trường có thể làm phiên chạy bị tính tiền ngoài gói Claude: "
            + ", ".join(removed)
            + ". Đã gỡ khỏi tiến trình này (không thay đổi cấu hình hệ thống) để SDK dùng tài khoản đăng nhập.",
            "Để không thấy cảnh báo này, xoá các biến đó khỏi .env hoặc biến môi trường của hệ thống.",
        )


def check_auth(report: Report) -> None:
    if not report.cli_path:
        return
    try:
        out = subprocess.run(
            [report.cli_path, "auth", "status"], capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report.error(f"Không kiểm tra được trạng thái đăng nhập ({exc}).", "Chạy thử: claude auth status")
        return
    raw = out.stdout.strip()
    try:
        start = raw.index("{")
        auth = json.loads(raw[start:])
    except (ValueError, json.JSONDecodeError):
        report.error(
            "Không đọc được kết quả `claude auth status`.",
            "Chạy `claude login` để đăng nhập bằng tài khoản Claude, rồi chạy lại.",
        )
        return
    report.auth = auth
    if not auth.get("loggedIn"):
        report.error(
            "Chưa đăng nhập Claude Code.",
            "Chạy: claude login   (đăng nhập bằng tài khoản Claude, không dùng API key)",
        )
        return
    method = auth.get("authMethod")
    if method != "claude.ai":
        report.error(
            f"Đang đăng nhập bằng phương thức '{method}', không phải tài khoản Claude (claude.ai). "
            "Phiên chạy sẽ không dùng gói đăng ký.",
            "Chạy: claude logout   rồi   claude login   và chọn đăng nhập bằng tài khoản Claude.",
        )


def check_env_file(report: Report) -> None:
    if ENV_FILE.exists():
        return
    copy_cmd = "Copy-Item .env.example .env" if IS_WINDOWS else "cp .env.example .env"
    report.warning(
        f"Chưa có file .env, dùng cấu hình mặc định.",
        f"{copy_cmd}   (mẫu: {ENV_EXAMPLE.name})",
    )


def check_environment(require_login: bool = True) -> Report:
    """Chạy toàn bộ kiểm tra. Thứ tự quan trọng: gỡ biến môi trường trước khi
    kiểm tra đăng nhập và trước mọi lần gọi SDK."""
    report = Report()
    check_python(report)
    check_modules(report)
    check_cli(report)
    check_env_vars(report)
    if require_login:
        check_auth(report)
    check_env_file(report)
    return report


def format_report(report: Report) -> str:
    lines: list[str] = []
    for p in report.problems:
        tag = "LỖI" if p.level == "error" else "Cảnh báo"
        lines.append(f"[{tag}] {p.message}")
        if p.fix:
            lines.append("  Cách sửa: " + p.fix.replace("\n", "\n  "))
    if report.ok:
        auth = report.auth or {}
        if auth.get("loggedIn"):
            lines.append(
                "Xác thực: tài khoản Claude ({}, gói {}) — không dùng API key.".format(
                    auth.get("authMethod"), auth.get("subscriptionType") or "không rõ"
                )
            )
        if report.cli_version:
            lines.append(f"Claude Code CLI: {report.cli_version}")
    return "\n".join(lines)


def ensure_ready(require_login: bool = True, quiet_when_ok: bool = False) -> Report:
    """Kiểm tra, in kết quả, thoát với mã 1 nếu có lỗi."""
    report = check_environment(require_login=require_login)
    text = format_report(report)
    if not report.ok:
        print(text, file=sys.stderr)
        print("\nMôi trường chưa sẵn sàng. Sửa các lỗi trên rồi chạy lại.", file=sys.stderr)
        sys.exit(1)
    if text and not (quiet_when_ok and not report.problems):
        print(text)
    return report
