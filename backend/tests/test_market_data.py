import json
import math
from datetime import date, timedelta

import pytest

from backend import market_data as md
from backend import scheduler as sch
from backend.api.deps import RunLock
from backend.config import Settings


def _series(n=300, start=100.0, step=0.5):
    """Chuỗi giá tăng đều để kiểm tra công thức."""
    rows = []
    d = date(2026, 1, 1)
    for i in range(n):
        while d.weekday() >= 5:
            d += timedelta(days=1)
        c = start + i * step
        rows.append({"date": d, "open": c, "high": c + 1, "low": c - 1, "close": c, "raw_close": c,
                     "volume": 1000 + i, "value": 10.0})
        d += timedelta(days=1)
    return rows


def test_sma_rsi_macd_basic():
    closes = [r["close"] for r in _series()]
    assert math.isclose(md.sma(closes, 20), sum(closes[-20:]) / 20)
    assert md.sma(closes[:5], 20) is None
    assert md.rsi(closes, 14) == 100.0  # chỉ tăng
    down = list(reversed(closes))
    assert md.rsi(down, 14) == pytest.approx(0.0, abs=1e-9)
    m = md.macd(closes)
    assert m is not None and m[0] > 0  # xu hướng tăng → MACD dương


def test_compute_indicators_fields():
    out = md.compute_indicators(_series())
    for k in ("sma20", "sma50", "sma200", "rsi14", "macd_hist", "vol_ratio", "high_20d", "low_20d", "high_52w", "low_52w"):
        assert out[k] is not None, k
    assert out["vs_sma20_pct"] > 0 and out["ma_cross"] == "MA20 > MA50"
    assert out["chg_1d_pct"] == pytest.approx(0.5 / (out["close"] - 0.5) * 100)


def _fake_cafef(symbol_rows):
    """Tạo opener giả trả JSON CafeF theo mã; hỗ trợ phân trang."""
    def opener(url):
        import urllib.parse
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        sym, page, size = q["Symbol"][0], int(q["PageIndex"][0]), int(q["PageSize"][0])
        rows = symbol_rows.get(sym)
        if rows is None:
            return json.dumps({"Data": {"Data": []}})
        desc = list(reversed(rows))
        chunk = desc[(page - 1) * size: page * size]
        items = [{"Symbol": sym, "Ngay": r["date"].strftime("%d/%m/%Y"), "GiaDieuChinh": r["close"], "GiaDongCua": r["close"],
                  "KhoiLuongKhopLenh": r["volume"], "GiaTriKhopLenh": r["value"], "GiaMoCua": r["open"],
                  "GiaCaoNhat": r["high"], "GiaThapNhat": r["low"]} for r in chunk]
        return json.dumps({"Data": {"Data": items}})
    return opener


def test_fetch_history_drops_incomplete_last_row():
    rows = _series(60)
    rows.append({**rows[-1], "date": rows[-1]["date"] + timedelta(days=1), "value": 0.0})  # phiên đang chạy
    got = md.fetch_history("ABC", 260, opener=_fake_cafef({"ABC": rows}))
    assert len(got) == 60 and got[-1]["date"] == rows[-2]["date"]
    assert got[0]["date"] < got[-1]["date"]


def test_build_market_data_writes_file(project):
    conf = md.MarketDataConfig(output=project / "knowledge" / "_du-lieu" / "ck" / "chi-bao.md",
                               indices=["VNINDEX"], tickers=["ABC", "XYZ"])
    data = {"VNINDEX": _series(260, 1500, 1.0), "ABC": _series(260, 50, 0.1)}  # XYZ không có
    s = md.build_market_data(conf, opener=_fake_cafef(data))
    assert s["ok"] == 2 and s["failed"] == 1 and "XYZ" in s["errors"]
    text = conf.output.read_text(encoding="utf-8")
    assert "| VNINDEX |" in text and "| ABC |" in text and "XYZ" in text
    assert "một nguồn" in text and "không phải khuyến nghị" in text


def test_load_market_config(project):
    (project / "config.yaml").write_text(
        "market_data:\n  output: knowledge/_du-lieu/x/y.md\n  tickers: [fpt, hpg]\n  indices: [VNINDEX]\n", encoding="utf-8")
    c = md.load_market_config(project / "config.yaml")
    assert c.tickers == ["FPT", "HPG"] and c.indices == ["VNINDEX"]
    assert c.output == project / "knowledge/_du-lieu/x/y.md"
    d = md.load_market_config(project / "khong-co.yaml")
    assert d.tickers == md.DEFAULT_TICKERS


def test_scheduler_pre_step_and_job_max_turns(project, monkeypatch):
    (project / "config.yaml").write_text(
        "scheduler:\n  git_commit: false\n  max_turns: 30\n  jobs:\n"
        "    - domain: ai\n      cron: \"0 17 * * mon-fri\"\n      max_turns: 60\n      pre_steps: [market-data, khong-co]\n",
        encoding="utf-8")
    conf = sch.load_config(project / "config.yaml")
    assert conf.jobs[0].max_turns == 60 and conf.jobs[0].pre_steps == ["market-data"]
    assert any("pre_steps" in w for w in conf.warnings)

    from backend.tests.test_scheduler import FakeCore
    settings = Settings(db_path=project / "backend" / "t.db", max_daily_runs=5, max_turns=100)
    core = FakeCore(settings)
    up = sch.AutoUpdater(core, RunLock(), settings, project / "config.yaml")
    calls = []
    monkeypatch.setattr(up, "_run_pre_step", lambda step: calls.append(step) or "đã ghi x")
    import asyncio
    r = asyncio.run(up.run_domain("ai", trigger="manual"))
    assert r["status"] == "done" and calls == ["market-data"]
    assert "market-data: đã ghi x" in r["message"]
    runs = asyncio.run(core.store.list_auto_runs())
    assert runs[0]["step"] == "commit"
