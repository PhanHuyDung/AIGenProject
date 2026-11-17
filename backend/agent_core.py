"""Lõi agent: chạy nghiên cứu và skill qua Claude Agent SDK.

- Xác thực bằng tài khoản Claude đã đăng nhập (claude login), không dùng API key.
- Nạp CLAUDE.md, .claude/agents, .claude/skills của dự án (setting_sources=["project"]).
- Chỉ cho phép ghi file trong knowledge/ và .claude/ (hook PreToolUse).
- Mỗi phiên được lưu vào SQLite (backend/data.db).

Mọi hàm chạy đều là async generator trả về sự kiện dạng
    {"type": "text" | "tool_use" | "tool_result" | "done" | "error", "data": {...}, "cost_usd": float | None}
"""

from __future__ import annotations

import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from . import config as cfg
from .config import Settings, load_settings
from .db import SessionStore
from .env_check import Report, check_environment, format_report

ALLOWED_TOOLS = [
    "Skill", "Task", "Agent",
    "WebSearch", "WebFetch",
    "Read", "Write", "Edit", "Glob", "Grep",
]
# Bash có thể ghi file mà hook không phát hiện được → gỡ hẳn khỏi phiên.
DISALLOWED_TOOLS = ["Bash", "NotebookEdit", "MultiEdit"]
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
# Trong .claude/ chỉ cho ghi file văn bản vào agents/ và skills/ (không settings.json, hooks, script).
CLAUDE_WRITABLE_SUFFIXES = {".md", ".txt", ".yaml", ".yml"}

_TRUNCATE = 300


# ----------------------------------------------------------------------------
# Giới hạn ghi file
# ----------------------------------------------------------------------------

def is_path_allowed(raw_path: str) -> tuple[bool, str]:
    """Chỉ cho phép ghi trong knowledge/ và .claude/ của dự án.

    Trả về (được phép, lý do). Lý do viết cho agent đọc, để nó hiểu vì sao bị chặn.
    """
    if not raw_path or not str(raw_path).strip():
        return False, "Thiếu đường dẫn file."
    p = Path(str(raw_path).strip())
    if not p.is_absolute():
        p = cfg.PROJECT_ROOT / p
    try:
        resolved = p.resolve()
    except OSError as exc:
        return False, f"Không xử lý được đường dẫn: {exc}"

    name_lower = resolved.name.lower()
    if name_lower == ".env" or name_lower.startswith(".env."):
        return False, "Không được ghi file .env (chứa cấu hình riêng của máy)."
    if ".git" in resolved.parts:
        return False, "Không được ghi vào thư mục .git."

    rel = _relative(resolved)
    try:
        resolved.relative_to(cfg.KNOWLEDGE_DIR.resolve())
        return True, ""
    except ValueError:
        pass
    try:
        inside_claude = resolved.relative_to(cfg.CLAUDE_DIR.resolve())
    except ValueError:
        inside_claude = None
    if inside_claude is not None:
        # Trong .claude/ chỉ được ghi agents/ và skills/ (file văn bản). settings.json, hooks...
        # có thể làm Claude Code chạy lệnh ở phiên sau, nên cấm để chặn prompt injection từ web.
        top = inside_claude.parts[0] if inside_claude.parts else ""
        if top not in ("agents", "skills") or len(inside_claude.parts) < 2:
            return False, (
                f"Trong .claude/ chỉ được ghi file trong .claude/agents/ và .claude/skills/; '{rel}' không thuộc "
                "hai thư mục đó (quy tắc ghi file trong CLAUDE.md)."
            )
        if resolved.suffix.lower() not in CLAUDE_WRITABLE_SUFFIXES:
            return False, (
                f"Trong .claude/ chỉ được ghi file {', '.join(sorted(CLAUDE_WRITABLE_SUFFIXES))}; "
                f"'{rel}' không được phép."
            )
        return True, ""
    return False, (
        f"Chỉ được ghi file trong knowledge/ và .claude/ của dự án; '{rel}' nằm ngoài phạm vi đó "
        "(quy tắc ghi file trong CLAUDE.md)."
    )


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(cfg.PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _extract_path(tool_input: dict[str, Any]) -> str | None:
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            return value
    return None


# ----------------------------------------------------------------------------
# Agent / skill của dự án
# ----------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.S)


def read_frontmatter(path: Path) -> dict[str, str]:
    """Đọc frontmatter dạng key: value đơn giản (đủ cho name/description/tools)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}
    data: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, _, value = line.partition(":")
            data[key.strip()] = value.strip()
    return data


def list_agents() -> list[dict[str, str]]:
    agents = []
    for f in sorted(cfg.AGENTS_DIR.glob("*.md")):
        fm = read_frontmatter(f)
        agents.append({
            "name": fm.get("name", f.stem),
            "description": fm.get("description", ""),
            "tools": fm.get("tools", ""),
            "file": _relative(f),
        })
    return agents


_KNOWLEDGE_DIR_RE = re.compile(r"knowledge/([a-z0-9][a-z0-9-]*)/")


def list_domain_agents() -> list[dict[str, str]]:
    """Ánh xạ lĩnh vực → agent nghiên cứu.

    Lĩnh vực là tên thư mục `knowledge/<domain>/` mà agent `*-researcher` ghi vào
    (đọc từ nội dung file agent); ví dụ finance-researcher → tai-chinh.
    """
    result = []
    for f in sorted(cfg.AGENTS_DIR.glob("*-researcher.md")):
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        dirs = [d for d in _KNOWLEDGE_DIR_RE.findall(text) if not d.startswith("_")]
        if not dirs:
            continue
        # Thư mục xuất hiện nhiều nhất trong file là thư mục của agent.
        domain = max(set(dirs), key=dirs.count)
        fm = read_frontmatter(f)
        result.append({
            "domain": domain,
            "agent": fm.get("name", f.stem),
            "description": fm.get("description", ""),
        })
    return result


def list_domains() -> list[str]:
    return [d["domain"] for d in list_domain_agents()]


def resolve_domain(value: str) -> dict[str, str] | None:
    """Nhận tên thư mục (tai-chinh) hoặc tên agent / tiền tố agent (finance)."""
    value = (value or "").strip().lower().rstrip("/")
    if value.startswith("knowledge/"):
        value = value[len("knowledge/"):]
    for d in list_domain_agents():
        if value in (d["domain"], d["agent"], d["agent"].removesuffix("-researcher")):
            return d
    return None


def list_skills() -> list[dict[str, str]]:
    skills = []
    for d in sorted(cfg.SKILLS_DIR.iterdir()) if cfg.SKILLS_DIR.exists() else []:
        skill_file = d / "SKILL.md"
        if d.is_dir() and skill_file.exists():
            fm = read_frontmatter(skill_file)
            skills.append({
                "name": fm.get("name", d.name),
                "description": fm.get("description", ""),
                "file": _relative(skill_file),
            })
    return skills


def count_pending_proposals() -> int:
    if not cfg.PENDING_DIR.exists():
        return 0
    count = 0
    for f in cfg.PENDING_DIR.glob("*.md"):
        fm = read_frontmatter(f)
        if fm.get("status", "").strip() == "cho-duyet":
            count += 1
    return count


# ----------------------------------------------------------------------------
# Chạy phiên
# ----------------------------------------------------------------------------

def _truncate(value: Any, limit: int = _TRUNCATE) -> Any:
    if isinstance(value, str) and len(value) > limit:
        return value[:limit] + f"… (+{len(value) - limit} ký tự)"
    return value


def _summarize_input(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Rút gọn input của tool để stream ra giao diện (không gửi cả nội dung file)."""
    out: dict[str, Any] = {}
    for key, value in tool_input.items():
        if key in ("content", "old_string", "new_string", "prompt"):
            out[key] = _truncate(value, 120)
        else:
            out[key] = _truncate(value)
    return out


def _summarize_result(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return _truncate(content)
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text", "")))
    return _truncate("\n".join(parts))


def _event(kind: str, data: dict[str, Any], cost_usd: float | None = None) -> dict[str, Any]:
    return {"type": kind, "data": data, "cost_usd": cost_usd}


def _classify_process_error(stderr: str) -> str:
    low = (stderr or "").lower()
    if "not logged in" in low or "please run /login" in low or "claude login" in low or "invalid api key" in low:
        return "Claude Code chưa đăng nhập hoặc phiên đăng nhập hết hạn. Chạy `claude login` bằng tài khoản Claude rồi thử lại."
    if "rate limit" in low or "usage limit" in low or "429" in low or "hit your limit" in low:
        return "Đã chạm giới hạn sử dụng của gói Claude. Chờ sang khung giờ mới rồi thử lại; không chuyển sang API key."
    return "Claude Code CLI kết thúc với lỗi."


class AgentCore:
    """Gói Settings + SessionStore để bước 4 (FastAPI) dùng lại một instance."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or load_settings()
        self.store = SessionStore(self.settings.db_path)
        self._db_ready = False

    async def _ensure_db(self) -> None:
        if not self._db_ready:
            await self.store.init_db()
            self._db_ready = True

    # -- public API ---------------------------------------------------------

    async def run_research(
        self, prompt: str, domain: str | None = None, max_turns: int | None = None,
        kind: str = "research",
    ) -> AsyncIterator[dict[str, Any]]:
        """Nghiên cứu một câu hỏi. `domain` là tên lĩnh vực (ai, game, tai-chinh...)."""
        prompt = (prompt or "").strip()
        if not prompt:
            yield _event("error", {"message": "Câu hỏi trống."})
            return
        full_prompt = prompt
        if domain:
            resolved = resolve_domain(domain)
            if resolved is None:
                yield _event("error", {
                    "message": f"Không có agent cho lĩnh vực '{domain}'.",
                    "domains": list_domains(),
                })
                return
            domain, agent = resolved["domain"], resolved["agent"]
            full_prompt = (
                f"Lĩnh vực: {domain}. Giao việc nghiên cứu cho subagent `{agent}` "
                f"(định nghĩa trong .claude/agents/{agent}.md) và yêu cầu lưu kết quả vào "
                f"knowledge/{domain}/ theo đúng quy tắc trong CLAUDE.md. Nếu chủ đề chưa có trong kho "
                f"kiến thức thì làm theo skill deep-research; nếu đã có thì theo skill update-knowledge. "
                f"Nội dung chưa chắc chắn phải ghi thành đề xuất chờ duyệt trong knowledge/_cho-duyet/.\n\n"
                f"Câu hỏi: {prompt}"
            )
        async for ev in self._run(full_prompt, kind=kind, prompt_for_db=prompt,
                                  domain=domain, max_turns=max_turns):
            yield ev

    async def run_skill(
        self, skill_name: str, args: str = "", max_turns: int | None = None, kind: str = "skill"
    ) -> AsyncIterator[dict[str, Any]]:
        """Chạy một skill trong .claude/skills/<skill_name>/ dưới dạng slash command."""
        skill_name = (skill_name or "").strip().lstrip("/")
        available = [s["name"] for s in list_skills()]
        if skill_name not in available:
            yield _event("error", {
                "message": f"Không có skill '{skill_name}'.",
                "skills": available,
            })
            return
        prompt = f"/{skill_name} {args.strip()}".strip()
        async for ev in self._run(prompt, kind=kind, prompt_for_db=prompt,
                                  skill_name=skill_name, max_turns=max_turns):
            yield ev

    # -- lõi -----------------------------------------------------------------

    def _build_options(self, report: Report, max_turns: int, session_state: dict[str, Any]):
        import warnings

        from claude_agent_sdk import ClaudeAgentOptions, HookMatcher

        # allowed_tools tự duyệt các tool thường; can_use_tool vẫn cần để CLI có kênh trả lời
        # các yêu cầu xin phép đặc biệt (ghi vào .claude/). SDK cảnh báo "shadowed" là nhiễu.
        warnings.filterwarnings("ignore", message=".*can_use_tool will not be invoked.*")

        async def guard_writes(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict[str, Any]:
            tool_name = input_data.get("tool_name", "")
            tool_input = input_data.get("tool_input") or {}
            raw = _extract_path(tool_input)
            allowed, reason = is_path_allowed(raw or "")
            action = "edit" if tool_name in ("Edit", "MultiEdit", "NotebookEdit") else "write"
            rel = _relative(Path(raw)) if raw else "(không rõ)"
            if allowed:
                entry = {"path": rel, "action": action}
                session_state["files"].append(entry)
                if tool_use_id:
                    session_state["write_ids"][tool_use_id] = entry
                return {}
            session_state["denied"].append({"path": rel, "action": action, "reason": reason})
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }

        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        async def can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any):
            # Claude Code xin phép riêng khi ghi vào .claude/ (kể cả khi Write nằm trong allowed_tools).
            # Không có người trả lời thì lệnh bị từ chối, nên trả lời ở đây theo đúng quy tắc đường dẫn.
            if tool_name in WRITE_TOOLS:
                ok, reason = is_path_allowed(_extract_path(tool_input or {}) or "")
                return PermissionResultAllow() if ok else PermissionResultDeny(message=reason)
            if tool_name in DISALLOWED_TOOLS:
                return PermissionResultDeny(message=f"Tool {tool_name} không được dùng trong app này.")
            return PermissionResultAllow()

        stderr_lines: list[str] = session_state["stderr"]

        def on_stderr(line: str) -> None:
            stderr_lines.append(line)
            if len(stderr_lines) > 200:
                del stderr_lines[:-200]

        return ClaudeAgentOptions(
            cwd=cfg.PROJECT_ROOT,
            cli_path=report.cli_path,
            setting_sources=["project"],
            allowed_tools=ALLOWED_TOOLS,
            disallowed_tools=DISALLOWED_TOOLS,
            skills="all",
            max_turns=max_turns,
            permission_mode="default",
            hooks={"PreToolUse": [HookMatcher(matcher="|".join(WRITE_TOOLS), hooks=[guard_writes])]},
            can_use_tool=can_use_tool,
            stderr=on_stderr,
        )

    async def _run(
        self,
        prompt: str,
        *,
        kind: str,
        prompt_for_db: str,
        domain: str | None = None,
        skill_name: str | None = None,
        max_turns: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        # 1. Môi trường + xác thực; gỡ biến API key trước mọi lần gọi SDK.
        report = check_environment(require_login=True)
        if not report.ok:
            yield _event("error", {
                "message": "Môi trường chưa sẵn sàng.",
                "details": format_report(report),
                "problems": [p.__dict__ for p in report.problems],
            })
            return

        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeSDKError,
            CLIConnectionError,
            CLINotFoundError,
            ProcessError,
            ResultMessage,
            SystemMessage,
            TextBlock,
            ToolResultBlock,
            ToolUseBlock,
            UserMessage,
            query,
        )

        turns = max_turns or self.settings.max_turns
        await self._ensure_db()
        session_id = await self.store.create_session(
            kind=kind, prompt=prompt_for_db, domain=domain, skill_name=skill_name,
            auth_method=report.auth_method, subscription_type=report.subscription_type,
        )
        state: dict[str, Any] = {"files": [], "denied": [], "stderr": [], "write_ids": {}}
        options = self._build_options(report, turns, state)

        started = time.monotonic()
        cost: float | None = None
        finished = False
        api_key_source: str | None = None

        try:
            async for msg in query(prompt=prompt, options=options):
                if isinstance(msg, SystemMessage):
                    if msg.subtype == "init":
                        api_key_source = msg.data.get("apiKeySource")
                        yield _event("text", {
                            "kind": "init",
                            "sdk_session_id": msg.data.get("session_id"),
                            "model": msg.data.get("model"),
                            "api_key_source": api_key_source,
                            "auth_method": report.auth_method,
                            "subscription_type": report.subscription_type,
                            "uses_subscription": api_key_source in (None, "none"),
                            "text": "",
                        })
                elif isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            yield _event("text", {
                                "text": block.text,
                                "parent_tool_use_id": msg.parent_tool_use_id,
                            }, cost)
                        elif isinstance(block, ToolUseBlock):
                            yield _event("tool_use", {
                                "id": block.id,
                                "name": block.name,
                                "input": _summarize_input(block.name, block.input),
                                "parent_tool_use_id": msg.parent_tool_use_id,
                            }, cost)
                elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
                    for block in msg.content:
                        if isinstance(block, ToolResultBlock):
                            if block.is_error and block.tool_use_id in state["write_ids"]:
                                # Hook cho phép nhưng lệnh ghi vẫn lỗi (ví dụ bị tầng quyền của Claude Code chặn).
                                entry = state["write_ids"][block.tool_use_id]
                                entry["failed"] = True
                                entry["error"] = _summarize_result(block.content)
                            yield _event("tool_result", {
                                "tool_use_id": block.tool_use_id,
                                "is_error": bool(block.is_error),
                                "content": _summarize_result(block.content),
                                "parent_tool_use_id": msg.parent_tool_use_id,
                            }, cost)
                elif isinstance(msg, ResultMessage):
                    cost = msg.total_cost_usd
                    finished = True
                    status = "error" if msg.is_error else "done"
                    error_text = "; ".join(msg.errors) if msg.errors else None
                    await self.store.finish_session(
                        session_id, status=status, num_turns=msg.num_turns,
                        duration_ms=msg.duration_ms, cost_usd=cost,
                        sdk_session_id=msg.session_id, result_subtype=msg.subtype,
                        error=error_text,
                    )
                    ok_files = [f for f in state["files"] if not f.get("failed")]
                    failed_files = [{"path": f["path"], "action": f["action"], "reason": f.get("error", "lỗi ghi")}
                                    for f in state["files"] if f.get("failed")]
                    for f in ok_files:
                        await self.store.add_file(session_id, f["path"], f["action"])
                    for f in state["denied"] + failed_files:
                        await self.store.add_file(session_id, f["path"], f["action"], denied=True)
                    yield _event("done", {
                        "session_id": session_id,
                        "sdk_session_id": msg.session_id,
                        "subtype": msg.subtype,
                        "is_error": msg.is_error,
                        "num_turns": msg.num_turns,
                        "duration_ms": msg.duration_ms,
                        "cost_usd": cost,
                        "cost_note": "Ước tính của SDK; không bị tính tiền vì dùng gói đăng ký Claude.",
                        "files": _dedupe(ok_files),
                        "denied_files": state["denied"] + failed_files,
                        "pending_proposals": count_pending_proposals(),
                        "result": _truncate(msg.result, 2000),
                        "errors": msg.errors,
                        "api_error_status": getattr(msg, "api_error_status", None),
                        "api_key_source": api_key_source,
                        "uses_subscription": api_key_source in (None, "none"),
                    }, cost)
        except CLINotFoundError as exc:
            yield await self._fail(session_id, f"Không tìm thấy Claude Code CLI: {exc}", state)
        except CLIConnectionError as exc:
            hint = ""
            if "batch script" in str(exc).lower() or ".cmd" in str(exc).lower():
                hint = " SDK không chạy được shim claude.cmd của npm; cài lại gói claude-agent-sdk để dùng CLI kèm theo."
            yield await self._fail(session_id, f"Không kết nối được Claude Code CLI: {exc}.{hint}", state)
        except ProcessError as exc:
            stderr = exc.stderr or "\n".join(state["stderr"][-20:])
            yield await self._fail(
                session_id, f"{_classify_process_error(stderr)} (mã thoát {exc.exit_code})", state,
                details=_truncate(stderr, 1500),
            )
        except ClaudeSDKError as exc:
            yield await self._fail(session_id, f"Lỗi Claude Agent SDK: {exc}", state,
                                   details=_truncate("\n".join(state["stderr"][-20:]), 1500))
        finally:
            if not finished:
                elapsed = int((time.monotonic() - started) * 1000)
                try:
                    await self.store.finish_session(
                        session_id, status="error", duration_ms=elapsed,
                        error="Phiên kết thúc mà không nhận được ResultMessage.",
                    )
                except Exception:  # pragma: no cover - không che lỗi gốc
                    pass

    async def _fail(self, session_id: str, message: str, state: dict[str, Any],
                    details: str | None = None) -> dict[str, Any]:
        await self.store.finish_session(session_id, status="error", error=message)
        for f in state["files"]:
            await self.store.add_file(session_id, f["path"], f["action"])
        data: dict[str, Any] = {"message": message, "session_id": session_id}
        if details:
            data["details"] = details
        return _event("error", data)


def _dedupe(files: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    out = []
    for f in files:
        key = (f["path"], f["action"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


# Hàm tiện dụng cấp module (dùng một AgentCore mặc định).
_default_core: AgentCore | None = None


def get_core() -> AgentCore:
    global _default_core
    if _default_core is None:
        _default_core = AgentCore()
    return _default_core


async def run_research(prompt: str, domain: str | None = None, max_turns: int | None = None):
    async for ev in get_core().run_research(prompt, domain=domain, max_turns=max_turns):
        yield ev


async def run_skill(skill_name: str, args: str = "", max_turns: int | None = None):
    async for ev in get_core().run_skill(skill_name, args, max_turns=max_turns):
        yield ev
