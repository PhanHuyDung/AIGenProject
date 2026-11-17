"""Tải lịch sử giá từ CafeF và tính sẵn các chỉ báo kỹ thuật cho một danh sách mã.

Kết quả là một bảng markdown trong knowledge/_du-lieu/<domain>/chi-bao-cuoi-phien.md để agent
đọc trước khi viết bản tin và chọn danh sách theo dõi kỹ thuật. Đây là dữ liệu do backend tính
từ MỘT nguồn (CafeF), không phải nguồn chính thức của sở; agent phải ghi rõ điều đó.

Chạy tay:  python -m backend.market_data            (dùng cấu hình trong config.yaml)
           python -m backend.market_data FPT HPG     (chỉ các mã này, in ra màn hình)
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

import yaml

from . import config as cfg

CAFEF_URL = ("https://cafef.vn/du-lieu/Ajax/PageNew/DataHistory/PriceHistory.ashx"
             "?Symbol={symbol}&StartDate=&EndDate=&PageIndex={page}&PageSize={size}")
HEADERS = {"User-Agent": "Mozilla/5.0 (AIGenProject market-data)", "Accept": "application/json"}
DEFAULT_OUTPUT = "knowledge/_du-lieu/chung-khoan-viet-nam/chi-bao-cuoi-phien.md"
DEFAULT_INDICES = ["VNINDEX", "VN30INDEX", "HNX-INDEX", "UPCOM-INDEX"]
DEFAULT_TICKERS = [
    "VIC", "VHM", "VRE", "VNM", "VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "HDB", "STB", "TPB", "VIB",
    "LPB", "SHB", "HPG", "FPT", "MWG", "MSN", "SAB", "GAS", "PLX", "POW", "SSI", "VND", "VCI", "HCM", "GVR",
    "BCM", "VJC", "PNJ", "REE", "DGC", "KDH", "NLG", "DXG", "BVH",
]  # chỉ mã HOSE: endpoint CafeF này trả rỗng cho mã HNX (SHS, PVS...), kiểm tra 2026-11-17


@dataclass
class MarketDataConfig:
    output: Path
    indices: list[str] = field(default_factory=lambda: list(DEFAULT_INDICES))
    tickers: list[str] = field(default_factory=lambda: list(DEFAULT_TICKERS))
    history_days: int = 260


def load_market_config(path: Path | None = None) -> MarketDataConfig:
    path = path or (cfg.PROJECT_ROOT / "config.yaml")
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("market_data") or {}
        except yaml.YAMLError:
            data = {}
    out = data.get("output") or DEFAULT_OUTPUT
    return MarketDataConfig(
        output=cfg.PROJECT_ROOT / out,
        indices=[str(s).upper() for s in (data.get("indices") or DEFAULT_INDICES)],
        tickers=[str(s).upper() for s in (data.get("tickers") or DEFAULT_TICKERS)],
        history_days=int(data.get("history_days") or 260),
    )


# ----------------------------------------------------------------------------- tải dữ liệu

def _parse_num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def fetch_history(symbol: str, days: int = 260, opener: Callable[[str], str] | None = None) -> list[dict[str, Any]]:
    """Trả về danh sách phiên tăng dần theo ngày: {date, open, high, low, close, volume, value}.

    Bỏ dòng cuối nếu chưa phải số đóng phiên hoàn chỉnh (giá trị khớp lệnh = 0).
    """
    def _default_opener(url: str) -> str:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    opener = opener or _default_opener
    rows: list[dict[str, Any]] = []
    seen_dates: set[date] = set()
    page, size = 1, 30  # CafeF trả tối đa ~30 dòng mỗi trang
    max_pages = days // size + 3
    while len(rows) < days and page <= max_pages:
        raw = opener(CAFEF_URL.format(symbol=urllib.parse.quote(symbol), page=page, size=size))
        data = json.loads(raw)
        items = ((data.get("Data") or {}).get("Data")) or []
        if not items:
            break
        new_in_page = 0
        for it in items:
            try:
                d = datetime.strptime(it["Ngay"], "%d/%m/%Y").date()
            except (KeyError, ValueError):
                continue
            if d in seen_dates:
                continue
            seen_dates.add(d)
            new_in_page += 1
            rows.append({
                "date": d,
                "open": _parse_num(it.get("GiaMoCua")),
                "high": _parse_num(it.get("GiaCaoNhat")),
                "low": _parse_num(it.get("GiaThapNhat")),
                "close": _parse_num(it.get("GiaDieuChinh")) or _parse_num(it.get("GiaDongCua")),
                "raw_close": _parse_num(it.get("GiaDongCua")),
                "volume": _parse_num(it.get("KhoiLuongKhopLenh")) or 0.0,
                "value": _parse_num(it.get("GiaTriKhopLenh")) or 0.0,
            })
        if new_in_page == 0:
            break
        page += 1
    rows = [r for r in rows if r["close"]]
    rows.sort(key=lambda r: r["date"])
    # Dòng cuối chưa hoàn chỉnh (phiên đang diễn ra): giá trị khớp lệnh = 0 trong khi các phiên trước > 0.
    if len(rows) >= 2 and rows[-1]["value"] == 0 and rows[-2]["value"] > 0:
        rows.pop()
    return rows[-days:]


# ----------------------------------------------------------------------------- chỉ báo

def sma(values: list[float], n: int) -> float | None:
    if len(values) < n or n <= 0:
        return None
    return sum(values[-n:]) / n


def rsi(values: list[float], n: int = 14) -> float | None:
    """RSI theo Wilder (trung bình mũ của lãi/lỗ)."""
    if len(values) < n + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        ch = values[i] - values[i - 1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        avg_gain = (avg_gain * (n - 1) + g) / n
        avg_loss = (avg_loss * (n - 1) + l) / n
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def ema_series(values: list[float], n: int) -> list[float]:
    if len(values) < n:
        return []
    k = 2 / (n + 1)
    out = [sum(values[:n]) / n]
    for v in values[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return out


def macd(values: list[float], fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[float, float, float] | None:
    if len(values) < slow + signal:
        return None
    ef, es = ema_series(values, fast), ema_series(values, slow)
    # căn hai chuỗi theo đuôi
    m = min(len(ef), len(es))
    line = [a - b for a, b in zip(ef[-m:], es[-m:])]
    sig = ema_series(line, signal)
    if not sig:
        return None
    return line[-1], sig[-1], line[-1] - sig[-1]


def compute_indicators(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [r["close"] for r in rows]
    vols = [r["volume"] for r in rows]
    last = rows[-1]
    out: dict[str, Any] = {
        "date": last["date"], "close": last["close"], "high": last["high"], "low": last["low"],
        "volume": last["volume"], "value": last["value"], "sessions": len(rows),
    }
    prev = closes[-2] if len(closes) >= 2 else None
    out["chg_1d_pct"] = (last["close"] / prev - 1) * 100 if prev else None
    out["chg_5d_pct"] = (last["close"] / closes[-6] - 1) * 100 if len(closes) >= 6 else None
    out["chg_20d_pct"] = (last["close"] / closes[-21] - 1) * 100 if len(closes) >= 21 else None
    for n in (20, 50, 200):
        s = sma(closes, n)
        out[f"sma{n}"] = s
        out[f"vs_sma{n}_pct"] = (last["close"] / s - 1) * 100 if s else None
    prev_closes = closes[:-1]
    s20_prev, s50_prev = sma(prev_closes, 20), sma(prev_closes, 50)
    out["sma20_slope"] = (out["sma20"] - s20_prev) if out["sma20"] and s20_prev else None
    out["ma_cross"] = None
    if out["sma20"] and out["sma50"] and s20_prev and s50_prev:
        if s20_prev <= s50_prev and out["sma20"] > out["sma50"]:
            out["ma_cross"] = "MA20 cắt lên MA50 (phiên này)"
        elif s20_prev >= s50_prev and out["sma20"] < out["sma50"]:
            out["ma_cross"] = "MA20 cắt xuống MA50 (phiên này)"
        else:
            out["ma_cross"] = "MA20 > MA50" if out["sma20"] > out["sma50"] else "MA20 < MA50"
    out["rsi14"] = rsi(closes, 14)
    m = macd(closes)
    out["macd"], out["macd_signal"], out["macd_hist"] = m if m else (None, None, None)
    v20 = sma(vols[:-1], 20)
    out["vol_avg20"] = v20
    out["vol_ratio"] = (last["volume"] / v20) if v20 else None
    out["high_20d"] = max(r["high"] or r["close"] for r in rows[-20:]) if len(rows) >= 20 else None
    out["low_20d"] = min(r["low"] or r["close"] for r in rows[-20:]) if len(rows) >= 20 else None
    out["high_52w"] = max(r["high"] or r["close"] for r in rows[-250:])
    out["low_52w"] = min(r["low"] or r["close"] for r in rows[-250:])
    out["avg_value_20d"] = sma([r["value"] for r in rows[:-1]], 20)
    return out


# ----------------------------------------------------------------------------- ghi file

def _f(v: Any, nd: int = 2, suffix: str = "") -> str:
    if v is None:
        return "–"
    if isinstance(v, (int, float)):
        return f"{v:,.{nd}f}{suffix}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(v)


def render_markdown(indices: dict[str, dict[str, Any]], tickers: dict[str, dict[str, Any]],
                    errors: dict[str, str], conf: MarketDataConfig, generated: datetime) -> str:
    dates = {v["date"] for v in list(indices.values()) + list(tickers.values())}
    latest = max(dates).isoformat() if dates else "–"
    lines = [
        "# Dữ liệu chỉ báo kỹ thuật cuối phiên (do backend tính)",
        "",
        f"- Tạo lúc: {generated.isoformat(timespec='minutes')}",
        f"- Phiên mới nhất trong dữ liệu: {latest}" + ("" if len(dates) <= 1 else f" (một số mã có phiên khác: {sorted(d.isoformat() for d in dates)})"),
        "- Nguồn giá: CafeF (`cafef.vn/du-lieu/.../PriceHistory.ashx`), giá điều chỉnh; **một nguồn, không phải số chính thức của HOSE/HNX**. "
        "Khi dùng phải ghi: \"theo dữ liệu CafeF, chỉ báo do backend AIGenProject tính\".",
        f"- Phạm vi: {len(tickers)} mã trong danh sách `market_data.tickers` của config.yaml (không phải toàn thị trường) và {len(indices)} chỉ số.",
        "- Công thức: SMA đơn giản; RSI(14) theo Wilder; MACD(12,26,9); khối lượng so với trung bình 20 phiên trước; "
        "hỗ trợ/kháng cự tham khảo = đáy/đỉnh 20 phiên; giá trị giao dịch đơn vị tỷ đồng (theo CafeF).",
        "- Đây là dữ liệu đầu vào, không phải khuyến nghị. Agent chọn danh sách theo dõi theo tiêu chí công khai trong file agent.",
        "",
        "## Chỉ số",
        "",
        "| Chỉ số | Phiên | Đóng cửa | ±1 phiên | ±5 phiên | ±20 phiên | SMA20 | SMA50 | SMA200 | Giá/SMA20 | Giá/SMA50 | RSI14 | MACD hist | KL/TB20 | Xu hướng MA |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for sym, v in indices.items():
        lines.append(f"| {sym} | {v['date'].isoformat()} | {_f(v['close'])} | {_f(v['chg_1d_pct'], 2, '%')} | {_f(v['chg_5d_pct'], 2, '%')} | "
                     f"{_f(v['chg_20d_pct'], 2, '%')} | {_f(v['sma20'])} | {_f(v['sma50'])} | {_f(v['sma200'])} | {_f(v['vs_sma20_pct'], 2, '%')} | "
                     f"{_f(v['vs_sma50_pct'], 2, '%')} | {_f(v['rsi14'], 1)} | {_f(v['macd_hist'], 2)} | {_f(v['vol_ratio'], 2)} | {v['ma_cross'] or '–'} |")
    lines += [
        "",
        "## Cổ phiếu",
        "",
        "Giá: nghìn đồng (giá điều chỉnh theo CafeF). GTGD TB20: tỷ đồng/phiên.",
        "",
        "| Mã | Phiên | Đóng cửa | ±1p | ±5p | ±20p | Giá/SMA20 | Giá/SMA50 | Giá/SMA200 | Xu hướng MA | RSI14 | MACD hist | KL/TB20 | GTGD TB20 | Đáy 20p | Đỉnh 20p | Đáy 52w | Đỉnh 52w |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for sym in sorted(tickers):
        v = tickers[sym]
        lines.append(f"| {sym} | {v['date'].isoformat()} | {_f(v['close'])} | {_f(v['chg_1d_pct'], 1, '%')} | {_f(v['chg_5d_pct'], 1, '%')} | "
                     f"{_f(v['chg_20d_pct'], 1, '%')} | {_f(v['vs_sma20_pct'], 1, '%')} | {_f(v['vs_sma50_pct'], 1, '%')} | {_f(v['vs_sma200_pct'], 1, '%')} | "
                     f"{v['ma_cross'] or '–'} | {_f(v['rsi14'], 1)} | {_f(v['macd_hist'], 3)} | {_f(v['vol_ratio'], 2)} | {_f(v['avg_value_20d'], 1)} | "
                     f"{_f(v['low_20d'])} | {_f(v['high_20d'])} | {_f(v['low_52w'])} | {_f(v['high_52w'])} |")
    if errors:
        lines += ["", "## Không lấy được dữ liệu", ""]
        lines += [f"- {sym}: {err}" for sym, err in sorted(errors.items())]
    lines.append("")
    return "\n".join(lines)


def build_market_data(conf: MarketDataConfig | None = None, opener: Callable[[str], str] | None = None,
                      now: datetime | None = None) -> dict[str, Any]:
    """Tải, tính và ghi file. Trả về tóm tắt {output, latest_date, ok, failed}."""
    conf = conf or load_market_config()
    indices: dict[str, dict[str, Any]] = {}
    tickers: dict[str, dict[str, Any]] = {}
    errors: dict[str, str] = {}
    for sym in conf.indices:
        try:
            rows = fetch_history(sym, conf.history_days, opener)
            if len(rows) < 30:
                raise ValueError(f"chỉ có {len(rows)} phiên")
            indices[sym] = compute_indicators(rows)
        except Exception as exc:  # noqa: BLE001 - ghi lỗi từng mã, không dừng cả bảng
            errors[sym] = str(exc)[:200]
    for sym in conf.tickers:
        try:
            rows = fetch_history(sym, conf.history_days, opener)
            if len(rows) < 30:
                raise ValueError(f"chỉ có {len(rows)} phiên")
            tickers[sym] = compute_indicators(rows)
        except Exception as exc:  # noqa: BLE001
            errors[sym] = str(exc)[:200]
    generated = now or datetime.now().astimezone()
    text = render_markdown(indices, tickers, errors, conf, generated)
    conf.output.parent.mkdir(parents=True, exist_ok=True)
    conf.output.write_text(text, encoding="utf-8", newline="\n")
    dates = [v["date"] for v in list(indices.values()) + list(tickers.values())]
    return {
        "output": conf.output, "latest_date": max(dates).isoformat() if dates else None,
        "ok": len(indices) + len(tickers), "failed": len(errors), "errors": errors,
    }


def main(argv: list[str]) -> int:
    conf = load_market_config()
    if argv:
        conf.tickers = [a.upper() for a in argv]
        conf.indices = []
        conf.output = cfg.PROJECT_ROOT / "backend" / "market_data_preview.md"
    summary = build_market_data(conf)
    print(f"Đã ghi {summary['output']} — phiên {summary['latest_date']}, {summary['ok']} mã/chỉ số, {summary['failed']} lỗi")
    for sym, err in summary["errors"].items():
        print(f"  lỗi {sym}: {err}")
    if argv:
        print(conf.output.read_text(encoding="utf-8"))
        conf.output.unlink(missing_ok=True)
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    from .config import ensure_utf8_stdout

    ensure_utf8_stdout()
    sys.exit(main(sys.argv[1:]))
