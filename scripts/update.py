#!/usr/bin/env python3
"""Fetch daily closes for S&P 500, Nasdaq and Dow from Yahoo Finance and
update data/days.json, data/stats.json, data/sectors.json and data.js.
Standard library only, no API key."""
import calendar
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DAYS_JSON = ROOT / "data" / "days.json"
STATS_JSON = ROOT / "data" / "stats.json"
SECTORS_JSON = ROOT / "data" / "sectors.json"
TRENDS_JSON = ROOT / "data" / "trends.json"  # written weekly by the Claude news task
DATA_JS = ROOT / "data.js"
NY = ZoneInfo("America/New_York")

SYMBOLS = {"spx": "^GSPC", "ndx": "^IXIC", "dji": "^DJI"}
# Full-history statistics start here. S&P 500 before 1950 traded six days a week, so it is left out.
HISTORY_START = {"spx": "1950-01-03", "ndx": "1971-02-05", "dji": "1992-01-02"}
SECTORS = [
    ("XLK", "기술", "애플·마이크로소프트 같은 IT 기업"),
    ("SMH", "반도체", "엔비디아·TSMC 같은 칩 기업"),
    ("XLC", "통신서비스", "구글·메타·넷플릭스 같은 미디어·인터넷"),
    ("XLY", "경기소비재", "아마존·테슬라 같은 소비·유통"),
    ("XLF", "금융", "JP모건 같은 은행·카드·보험"),
    ("XLV", "헬스케어", "제약·바이오·병원 관련"),
    ("XLI", "산업재", "항공·방산·기계·운송"),
    ("XLE", "에너지", "엑슨모빌 같은 석유·가스"),
    ("XLP", "필수소비재", "코카콜라·월마트 같은 생활필수품"),
    ("XLU", "유틸리티", "전기·가스·수도 회사"),
    ("XLB", "소재", "화학·금속·광산"),
    ("XLRE", "부동산", "리츠·부동산 임대"),
]
HOSTS = ("query1.finance.yahoo.com", "query2.finance.yahoo.com")
LOOKBACK_DAYS = 45  # re-check this window every run so missed days fill themselves
FLAT_THRESHOLD = 0.1  # |S&P 500 %| below this counts as 보합

# NYSE full-day closures. Weekdays with no data that are not listed here are left unrecorded.
HOLIDAYS = {
    "2025-11-27": "추수감사절", "2025-12-25": "크리스마스",
    "2026-01-01": "새해", "2026-01-19": "마틴 루터 킹 데이", "2026-02-16": "대통령의 날",
    "2026-04-03": "성금요일", "2026-05-25": "메모리얼 데이", "2026-06-19": "준틴스",
    "2026-07-03": "독립기념일(대체)", "2026-09-07": "노동절", "2026-11-26": "추수감사절",
    "2026-12-25": "크리스마스",
    "2027-01-01": "새해", "2027-01-18": "마틴 루터 킹 데이", "2027-02-15": "대통령의 날",
    "2027-03-26": "성금요일", "2027-05-31": "메모리얼 데이", "2027-06-18": "준틴스(대체)",
    "2027-07-05": "독립기념일(대체)", "2027-09-06": "노동절", "2027-11-25": "추수감사절",
    "2027-12-24": "크리스마스(대체)",
}


def fetch_series(symbol, query="range=3mo&interval=1d"):
    """Return {YYYY-MM-DD: close} for the requested range (default: about three months)."""
    path = f"/v8/finance/chart/{urllib.parse.quote(symbol)}?{query}"
    last_err = None
    for attempt in range(3):
        host = HOSTS[attempt % len(HOSTS)]
        req = urllib.request.Request(f"https://{host}{path}", headers={"User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                result = json.load(resp)["chart"]["result"][0]
            break
        except Exception as e:  # network hiccup or rate limit: back off and retry
            last_err = e
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError(f"{symbol}: {last_err}")

    closes = result["indicators"]["quote"][0]["close"]
    series = {}
    for ts, close in zip(result["timestamp"], closes):
        if close is None:
            continue
        day = dt.datetime.fromtimestamp(ts, NY).date().isoformat()
        series[day] = round(close, 2)
    return series


def session_finished(day, now):
    """A bar for today's New York date is final only after the 16:00 close (with margin)."""
    return day < now.date().isoformat() or now.time() >= dt.time(16, 30)


def build_records(all_series, now):
    days = sorted(set.intersection(*(set(s) for s in all_series.values())))
    records = {}
    for prev, day in zip(days, days[1:]):
        if not session_finished(day, now):
            continue
        indices = {}
        for key, series in all_series.items():
            close, prev_close = series[day], series[prev]
            indices[key] = {
                "close": close,
                "prev": prev_close,
                "chg": round((close / prev_close - 1) * 100, 2),
            }
        spx = indices["spx"]["chg"]
        verdict = "up" if spx >= FLAT_THRESHOLD else "down" if spx <= -FLAT_THRESHOLD else "flat"
        records[day] = {"date": day, "verdict": verdict, "indices": indices}
    return records


def daily_changes(series):
    """[(day, close, % change vs previous close)] in date order, first day dropped."""
    days = sorted(series)
    return [(d, series[d], (series[d] / series[p] - 1) * 100) for p, d in zip(days, days[1:])]


def index_stats(series, start, now):
    """Descriptive statistics over the whole history of one index."""
    series = {d: c for d, c in series.items() if d >= start and session_finished(d, now)}
    rows = daily_changes(series)
    chg = [c for _, _, c in rows]
    n = len(chg)
    years = n / 252

    moves = {}
    for t in (0.5, 1, 2, 3):
        up = sum(c >= t for c in chg)
        down = sum(c <= -t for c in chg)
        moves[str(t)] = {"up": up, "down": down, "upPerYear": round(up / years, 1), "downPerYear": round(down / years, 1)}

    abs_sorted = sorted(abs(c) for c in chg)
    quantiles = [round(abs_sorted[min(n - 1, int(q / 100 * n))], 3) for q in range(101)]

    # streaks[up|down][k] = how many runs reached at least k+2 days in a row
    streaks = {"up": [0] * 9, "down": [0] * 9}
    run_dir, run_len = None, 0
    for c in chg + [0.0]:
        d = "up" if c > 0 else "down" if c < 0 else None
        if d and d == run_dir:
            run_len += 1
            continue
        if run_dir and run_len >= 2:
            for k in range(2, min(run_len, 10) + 1):
                streaks[run_dir][k - 2] += 1
        run_dir, run_len = d, 1 if d else 0

    best = max(rows, key=lambda r: r[2])
    worst = min(rows, key=lambda r: r[2])
    ath_day = max(series, key=series.get)

    # Calendar-month returns from month-end closes.
    month_end = {}
    for d in sorted(series):
        month_end[d[:7]] = series[d]
    months_sorted = sorted(month_end)
    by_month = {m: [] for m in range(1, 13)}
    for p, m in zip(months_sorted, months_sorted[1:]):
        by_month[int(m[5:])].append((month_end[m] / month_end[p] - 1) * 100)
    months = {}
    for m, rets in by_month.items():
        if rets:
            months[str(m)] = {"avg": round(sum(rets) / len(rets), 2), "upShare": round(100 * sum(r > 0 for r in rets) / len(rets)), "years": len(rets)}

    # Share of start days whose price was lower after holding 1 / 10 years (dividends excluded).
    closes = [c for _, c, _ in rows]
    hold = {}
    for label, span in (("1y", 252), ("10y", 2520)):
        if len(closes) > span:
            pairs = len(closes) - span
            losses = sum(closes[i + span] < closes[i] for i in range(pairs))
            hold[label] = {"lossShare": round(100 * losses / pairs, 1), "samples": pairs}

    return {
        "start": rows[0][0], "end": rows[-1][0], "days": n,
        "upShare": round(100 * sum(c > 0 for c in chg) / n, 1),
        "moves": moves, "absQuantiles": quantiles, "streaks": streaks,
        "best": {"date": best[0], "chg": round(best[2], 2)},
        "worst": {"date": worst[0], "chg": round(worst[2], 2)},
        "ath": {"date": ath_day, "close": series[ath_day]},
        "months": months, "hold": hold,
    }


def drawdowns(series):
    """{day: % below the all-time high reached so far} (0 on a new high)."""
    out, peak = {}, 0.0
    for d in sorted(series):
        peak = max(peak, series[d])
        out[d] = round((series[d] / peak - 1) * 100, 2)
    return out


def sector_stats(now):
    rows = []
    for ticker, name, about in SECTORS:
        try:
            s = fetch_series(ticker, "range=1y&interval=1d")
        except RuntimeError as e:
            print(f"skip sector {ticker}: {e}")
            continue
        days = [d for d in sorted(s) if session_finished(d, now)]
        last = s[days[-1]]
        ret = lambda back: round((last / s[days[-1 - back]] - 1) * 100, 2) if len(days) > back else None
        rows.append({"ticker": ticker, "name": name, "about": about, "asOf": days[-1],
                     "w1": ret(5), "m1": ret(21), "m3": ret(63), "y1": ret(len(days) - 1)})
        time.sleep(0.5)
    return {"asOf": max((r["asOf"] for r in rows), default=None), "sectors": rows}


def write_json(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", "utf-8")


def main():
    now = dt.datetime.now(NY)
    history = {}
    for key, sym in SYMBOLS.items():
        p1 = calendar.timegm(dt.date.fromisoformat(HISTORY_START[key]).timetuple()) - 86400 * 7
        history[key] = fetch_series(sym, f"period1={p1}&period2={int(time.time())}&interval=1d")
        time.sleep(0.5)
    recent_start = (now.date() - dt.timedelta(days=120)).isoformat()
    all_series = {k: {d: c for d, c in s.items() if d >= recent_start} for k, s in history.items()}
    fresh = build_records(all_series, now)
    dds = {k: drawdowns(s) for k, s in history.items()}
    for day, rec in fresh.items():
        for k, it in rec["indices"].items():
            it["dd"] = dds[k].get(day)

    existing = json.loads(DAYS_JSON.read_text("utf-8")) if DAYS_JSON.exists() else {}
    start = (now.date() - dt.timedelta(days=LOOKBACK_DAYS)).isoformat()
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    changed = []

    for day, rec in fresh.items():
        if day < start:
            continue
        old = existing.get(day, {})
        if old.get("indices") == rec["indices"] and old.get("verdict") == rec["verdict"]:
            continue
        # Keep any hand-written notes (summary, bullish, bearish) on the day.
        existing[day] = {**old, **rec, "updatedAt": stamp}
        changed.append(day)

    for day, name in HOLIDAYS.items():
        if start <= day <= now.date().isoformat() and day not in existing:
            existing[day] = {"date": day, "verdict": "closed", "holiday": name, "updatedAt": stamp}
            changed.append(day)

    # Older records outside the lookback window still get their drawdown filled in once.
    for day, rec in existing.items():
        for k, it in (rec.get("indices") or {}).items():
            if "dd" not in it and day in dds[k]:
                it["dd"] = dds[k][day]

    ordered = dict(sorted(existing.items()))
    write_json(DAYS_JSON, ordered)

    stats = {"asOf": max(fresh) if fresh else None,
             "indices": {k: index_stats(history[k], HISTORY_START[k], now) for k in SYMBOLS}}
    write_json(STATS_JSON, stats)
    sectors = sector_stats(now)
    write_json(SECTORS_JSON, sectors)
    trends = json.loads(TRENDS_JSON.read_text("utf-8")) if TRENDS_JSON.exists() else None

    dump = lambda o: json.dumps(o, ensure_ascii=False)
    DATA_JS.write_text(
        "// Generated by scripts/update.py. Edit data/*.json instead.\n"
        f"window.MARKET_DAYS = {dump(ordered)};\n"
        f"window.MARKET_STATS = {dump(stats)};\n"
        f"window.MARKET_SECTORS = {dump(sectors)};\n"
        f"window.MARKET_TRENDS = {dump(trends)};\n",
        "utf-8",
    )
    print(f"updated {len(changed)} day(s): {', '.join(sorted(changed)) or '-'}")


if __name__ == "__main__":
    main()
