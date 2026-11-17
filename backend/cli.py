"""Chạy thử lõi agent từ terminal.

    python backend/cli.py "câu hỏi" [--domain ai] [--max-turns N]
    python backend/cli.py --skill deep-research "tham số"
    python backend/cli.py --check            # chỉ kiểm tra môi trường
    python backend/cli.py --history [N]      # xem N phiên gần nhất
    python backend/cli.py --list             # liệt kê lĩnh vực và skill
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.config import ensure_utf8_stdout, load_settings  # noqa: E402
from backend.env_check import ensure_ready  # noqa: E402


def _fmt_ms(ms: int | None) -> str:
    if ms is None:
        return "?"
    return f"{ms / 1000:.1f}s"


def print_event(ev: dict) -> None:
    kind, data = ev["type"], ev["data"]
    if kind == "text":
        if data.get("kind") == "init":
            src = data.get("api_key_source")
            ok = data.get("uses_subscription")
            print(f"[phiên {data.get('sdk_session_id')}] model={data.get('model')} "
                  f"nguồn xác thực={src!r} → {'tài khoản Claude, không dùng API key' if ok else 'CẢNH BÁO: ĐANG DÙNG API KEY'}")
        else:
            prefix = "  │ " if data.get("parent_tool_use_id") else ""
            for line in data["text"].rstrip().splitlines():
                print(prefix + line)
    elif kind == "tool_use":
        name, inp = data["name"], data["input"]
        prefix = "  │ " if data.get("parent_tool_use_id") else ""
        if name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
            print(f"{prefix}▶ {name}: {inp.get('file_path') or inp.get('notebook_path')}")
        elif name == "WebSearch":
            print(f"{prefix}▶ WebSearch: {inp.get('query')!r}")
        elif name == "WebFetch":
            print(f"{prefix}▶ WebFetch: {inp.get('url')}")
        elif name in ("Task", "Agent"):
            print(f"{prefix}▶ Subagent {inp.get('subagent_type')}: {inp.get('description')}")
        elif name == "Skill":
            print(f"{prefix}▶ Skill: {inp.get('skill') or inp.get('command')} {inp.get('args', '')}")
        elif name in ("Read", "Glob", "Grep"):
            print(f"{prefix}▶ {name}: {inp.get('file_path') or inp.get('pattern')}")
        else:
            print(f"{prefix}▶ {name}: {inp}")
    elif kind == "tool_result":
        if data.get("is_error"):
            print(f"  ✖ lỗi tool: {data.get('content')}")
    elif kind == "done":
        print("\n" + "─" * 60)
        print(f"Trạng thái     : {data['subtype']}{' (lỗi)' if data['is_error'] else ''}")
        print(f"Số lượt        : {data['num_turns']}")
        print(f"Thời gian      : {_fmt_ms(data['duration_ms'])}")
        cost = data.get("cost_usd")
        print(f"Chi phí ước tính: {'$%.4f' % cost if cost is not None else 'không có'} — {data['cost_note']}")
        print(f"Xác thực       : {'tài khoản Claude (gói đăng ký), không dùng API key' if data.get('uses_subscription') else 'API KEY — kiểm tra lại môi trường!'}")
        if data["files"]:
            print("File đã ghi    :")
            for f in data["files"]:
                print(f"  - {f['path']} ({f['action']})")
        else:
            print("File đã ghi    : không có")
        if data["denied_files"]:
            print("File bị chặn   :")
            for f in data["denied_files"]:
                print(f"  - {f['path']} — {f['reason']}")
        print(f"Đề xuất chờ duyệt (knowledge/_cho-duyet): {data['pending_proposals']}")
        if data.get("errors"):
            print("Lỗi            : " + "; ".join(data["errors"]))
        print(f"Mã phiên (SQLite): {data['session_id']}")
    elif kind == "error":
        print("\n[LỖI] " + data["message"], file=sys.stderr)
        if data.get("details"):
            print(data["details"], file=sys.stderr)
        if data.get("domains"):
            print("Lĩnh vực hợp lệ: " + ", ".join(data["domains"]), file=sys.stderr)
        if data.get("skills"):
            print("Skill hợp lệ: " + ", ".join(data["skills"]), file=sys.stderr)


async def run(args: argparse.Namespace) -> int:
    from backend.agent_core import AgentCore, list_domain_agents, list_skills

    core = AgentCore()
    if args.list:
        print("Lĩnh vực → agent:")
        for d in list_domain_agents():
            print(f"  - {d['domain']:22} → {d['agent']}")
        print("Skill:")
        for s in list_skills():
            print(f"  - {s['name']}: {s['description'][:100]}")
        return 0
    if args.history is not None:
        await core.store.init_db()
        sessions = await core.store.list_sessions(limit=args.history or 10)
        if not sessions:
            print("Chưa có phiên nào.")
            return 0
        for s in sessions:
            cost = f"${s['cost_usd']:.4f}" if s["cost_usd"] is not None else "-"
            print(f"{s['started_at']}  {s['status']:7} {s['kind']:8} lượt={s['num_turns'] or '-':<3} "
                  f"{_fmt_ms(s['duration_ms']):>7} ước tính={cost:>8}  {s['domain'] or s['skill_name'] or ''}")
            print(f"    {s['prompt'][:100]}")
            for f in s["files"]:
                print(f"    {'✖' if f['denied'] else '•'} {f['path']} ({f['action']})")
        return 0

    exit_code = 0
    if args.skill:
        stream = core.run_skill(args.skill, args.prompt or "", max_turns=args.max_turns)
    else:
        stream = core.run_research(args.prompt, domain=args.domain, max_turns=args.max_turns)
    async for ev in stream:
        print_event(ev)
        if ev["type"] == "error" or (ev["type"] == "done" and ev["data"]["is_error"]):
            exit_code = 1
    return exit_code


def main() -> None:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description="Chạy thử lõi agent AIGenProject.")
    parser.add_argument("prompt", nargs="?", help="Câu hỏi nghiên cứu, hoặc tham số cho --skill")
    parser.add_argument("--domain", "-d", help="Lĩnh vực: ai, game, tai-chinh, cong-nghe-thong-tin, phat-trien-phan-mem...")
    parser.add_argument("--skill", "-s", help="Chạy skill trong .claude/skills/<tên>")
    parser.add_argument("--max-turns", type=int, help="Số lượt tối đa (mặc định MAX_TURNS trong .env)")
    parser.add_argument("--check", action="store_true", help="Chỉ kiểm tra môi trường")
    parser.add_argument("--history", type=int, nargs="?", const=10, help="Xem N phiên gần nhất")
    parser.add_argument("--list", action="store_true", help="Liệt kê lĩnh vực và skill")
    args = parser.parse_args()

    settings = load_settings()
    for w in settings.warnings:
        print("[Cảnh báo .env] " + w, file=sys.stderr)

    if args.check:
        ensure_ready(require_login=True)
        print("Môi trường sẵn sàng.")
        return
    if args.list or args.history is not None:
        ensure_ready(require_login=False, quiet_when_ok=True)
    else:
        if not args.prompt and not args.skill:
            parser.error("cần câu hỏi, hoặc --skill, --check, --history, --list")
        ensure_ready(require_login=True)

    try:
        sys.exit(asyncio.run(run(args)))
    except KeyboardInterrupt:
        print("\nĐã dừng theo yêu cầu.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
