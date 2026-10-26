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
EARNINGS_JSON = ROOT / "data" / "earnings.json"
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

# Earnings calendar: these well-known names always show, plus anything worth at least EARNINGS_MIN_CAP.
EARNINGS_MIN_CAP = 150e9
EARNINGS_WINDOW = (-14, 42)  # days around today to (re)fetch each run
WATCHLIST = {
    "AAPL": ("애플", "아이폰·맥"), "MSFT": ("마이크로소프트", "윈도·클라우드"), "NVDA": ("엔비디아", "AI 반도체"),
    "AMZN": ("아마존", "온라인 쇼핑·클라우드"), "GOOGL": ("알파벳(구글)", "검색·유튜브"), "GOOG": ("알파벳(구글)", "검색·유튜브"),
    "META": ("메타", "페이스북·인스타그램"), "TSLA": ("테슬라", "전기차"), "AVGO": ("브로드컴", "통신·AI 반도체"),
    "TSM": ("TSMC", "반도체 위탁생산"), "NFLX": ("넷플릭스", "영상 스트리밍"), "AMD": ("AMD", "CPU·GPU 반도체"),
    "INTC": ("인텔", "CPU 반도체"), "MU": ("마이크론", "메모리 반도체"), "QCOM": ("퀄컴", "스마트폰 칩"),
    "ORCL": ("오라클", "데이터베이스·클라우드"), "CRM": ("세일즈포스", "기업용 소프트웨어"), "ADBE": ("어도비", "포토샵·디자인 SW"),
    "PLTR": ("팔란티어", "데이터 분석 SW"), "ASML": ("ASML", "반도체 장비"), "JPM": ("JP모건", "미국 최대 은행"),
    "V": ("비자", "카드 결제망"), "MA": ("마스터카드", "카드 결제망"), "WMT": ("월마트", "대형마트"),
    "COST": ("코스트코", "창고형 할인점"), "KO": ("코카콜라", "음료"), "PEP": ("펩시코", "음료·과자"),
    "MCD": ("맥도날드", "패스트푸드"), "SBUX": ("스타벅스", "커피"), "NKE": ("나이키", "스포츠용품"),
    "DIS": ("디즈니", "영화·테마파크"), "BA": ("보잉", "항공기"), "LLY": ("일라이 릴리", "비만·당뇨 치료제"),
    "UNH": ("유나이티드헬스", "건강보험"), "JNJ": ("존슨앤드존슨", "제약·의료기기"), "PG": ("P&G", "생활용품"),
    "XOM": ("엑슨모빌", "석유·가스"), "BRK.B": ("버크셔 해서웨이", "워런 버핏의 지주회사"),
    "SPCX": ("스페이스X", "로켓·위성 인터넷"),
}
# Korean names for other large caps that show up only because of their size.
NAMES_KO = {
    "ABBV": ("애브비", "제약"), "ABT": ("애보트", "의료기기·진단"), "ADI": ("아날로그 디바이스", "아날로그 반도체"),
    "AMAT": ("어플라이드 머티어리얼즈", "반도체 장비"), "AMGN": ("암젠", "바이오 제약"), "ANET": ("아리스타 네트웍스", "데이터센터 네트워크"),
    "APH": ("암페놀", "전자 커넥터"), "ARM": ("Arm", "반도체 설계"), "AXP": ("아메리칸 익스프레스", "신용카드"),
    "AZN": ("아스트라제네카", "제약"), "BABA": ("알리바바", "중국 전자상거래"), "BAC": ("뱅크오브아메리카", "은행"),
    "BHP": ("BHP", "광산"), "BLK": ("블랙록", "자산운용"), "BRK.A": ("버크셔 해서웨이", "워런 버핏의 지주회사"),
    "BUD": ("AB인베브", "맥주"), "C": ("씨티그룹", "은행"), "CAT": ("캐터필러", "건설·광산 장비"),
    "COP": ("코노코필립스", "석유·가스"), "CRWD": ("크라우드스트라이크", "사이버보안"), "CSCO": ("시스코", "네트워크 장비"),
    "CVX": ("셰브런", "석유·가스"), "DE": ("디어", "농기계"), "DELL": ("델", "PC·서버"), "DHR": ("다나허", "생명과학 장비"),
    "GE": ("GE 에어로스페이스", "항공기 엔진"), "GEV": ("GE 버노바", "발전 설비"), "GILD": ("길리어드", "바이오 제약"),
    "GS": ("골드만삭스", "투자은행"), "HD": ("홈디포", "집수리 용품점"), "HSBC": ("HSBC", "은행"), "IBM": ("IBM", "IT 서비스"),
    "ISRG": ("인튜이티브 서지컬", "수술 로봇"), "KLAC": ("KLA", "반도체 장비"), "LIN": ("린데", "산업용 가스"),
    "LRCX": ("램리서치", "반도체 장비"), "MRK": ("머크", "제약"), "MRVL": ("마벨", "데이터센터 반도체"),
    "MS": ("모건스탠리", "투자은행"), "MUFG": ("미쓰비시UFJ", "일본 은행"), "NEE": ("넥스트에라", "전력·신재생"),
    "NOW": ("서비스나우", "기업용 소프트웨어"), "NVO": ("노보 노디스크", "비만·당뇨 치료제"), "NVS": ("노바티스", "제약"),
    "PANW": ("팔로알토 네트웍스", "사이버보안"), "PBR": ("페트로브라스", "브라질 석유"), "PBR.A": ("페트로브라스", "브라질 석유"),
    "PFE": ("화이자", "제약"), "PM": ("필립모리스", "담배"), "RTX": ("RTX", "방산·항공"), "RY": ("캐나다왕립은행", "은행"),
    "SAN": ("산탄데르", "스페인 은행"), "SAP": ("SAP", "기업용 소프트웨어"), "SCCO": ("서던코퍼", "구리 광산"),
    "SCHW": ("찰스 슈왑", "증권사"), "SHEL": ("셸", "석유·가스"), "SHOP": ("쇼피파이", "온라인 쇼핑몰 플랫폼"),
    "SMFG": ("미쓰이스미토모", "일본 은행"), "SNDK": ("샌디스크", "저장장치"), "SONY": ("소니", "게임·전자"),
    "TD": ("TD은행", "캐나다 은행"), "TJX": ("TJX", "할인 의류점"), "TM": ("도요타", "자동차"), "TMO": ("써모피셔", "실험 장비"),
    "TMUS": ("T모바일", "이동통신"), "TTE": ("토탈에너지", "석유·가스"), "TXN": ("텍사스 인스트루먼트", "아날로그 반도체"),
    "UNP": ("유니온 퍼시픽", "철도"), "VZ": ("버라이즌", "이동통신"), "WELL": ("웰타워", "헬스케어 리츠"), "WFC": ("웰스파고", "은행"),
}
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


def money(s):
    """'$1,234.5' / '($0.12)' / 'N/A' -> float or None."""
    s = (s or "").strip().replace("$", "").replace(",", "")
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        return -float(s) if neg else float(s)
    except ValueError:
        return None


def clean_name(name):
    """'The Goldman Sachs Group, Inc.' -> 'Goldman Sachs Group' for companies without a Korean name."""
    name = name.strip()
    if name.startswith("The "):
        name = name[4:]
    for tail in (" (The)", ", Inc.", " Inc.", " Inc", " Corporation", " Corp.", " Company", " plc", " PLC", " Ltd Ord",
                 " Limited", " S.A.", " A/S", " SE", " AG", " N.V.", " Holdings", " Holding"):
        if name.endswith(tail):
            name = name[: -len(tail)]
    return name.strip(" ,")


def fetch_earnings_day(day):
    req = urllib.request.Request(
        f"https://api.nasdaq.com/api/calendar/earnings?date={day}",
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return ((json.load(resp).get("data") or {}).get("rows")) or []
        except Exception as e:
            last = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"earnings {day}: {last}")


def earnings_calendar(now):
    """{YYYY-MM-DD: [large-cap reports]} for the window around today, merged into the stored file."""
    stored = json.loads(EARNINGS_JSON.read_text("utf-8")) if EARNINGS_JSON.exists() else {}
    today = now.date()
    for offset in range(EARNINGS_WINDOW[0], EARNINGS_WINDOW[1] + 1):
        day = today + dt.timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        key = day.isoformat()
        try:
            rows = fetch_earnings_day(key)
        except RuntimeError as e:
            print(f"skip {e}")
            continue
        picked = []
        for r in rows:
            sym = (r.get("symbol") or "").upper()
            cap = money(r.get("marketCap"))
            if sym not in WATCHLIST and (cap or 0) < EARNINGS_MIN_CAP:
                continue
            ko, what = WATCHLIST.get(sym) or NAMES_KO.get(sym) or (None, None)
            surprise = money(r.get("surprise"))
            picked.append({
                "symbol": sym,
                "name": ko or clean_name(r.get("name") or sym),
                "what": what,
                "time": {"time-pre-market": "pre", "time-after-hours": "after"}.get(r.get("time"), "unknown"),
                "capB": round(cap / 1e9) if cap else None,
                "epsForecast": money(r.get("epsForecast")),
                "eps": money(r.get("eps")),
                "surprise": surprise,
            })
        picked.sort(key=lambda x: (x["symbol"] not in WATCHLIST, -(x["capB"] or 0)))
        # One row per company: GOOG/GOOGL, BRK.A/BRK.B, PBR/PBR.A share a name.
        seen = set()
        picked = [p for p in picked if not (p["name"] in seen or seen.add(p["name"]))]
        if picked:
            stored[key] = picked
        else:
            stored.pop(key, None)
        time.sleep(0.3)
    return dict(sorted(stored.items()))


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
    earnings = earnings_calendar(now)
    write_json(EARNINGS_JSON, earnings)

    dump = lambda o: json.dumps(o, ensure_ascii=False)
    DATA_JS.write_text(
        "// Generated by scripts/update.py. Edit data/*.json instead.\n"
        f"window.MARKET_DAYS = {dump(ordered)};\n"
        f"window.MARKET_STATS = {dump(stats)};\n"
        f"window.MARKET_SECTORS = {dump(sectors)};\n"
        f"window.MARKET_TRENDS = {dump(trends)};\n"
        f"window.MARKET_EARNINGS = {dump(earnings)};\n",
        "utf-8",
    )
    print(f"updated {len(changed)} day(s): {', '.join(sorted(changed)) or '-'}")


if __name__ == "__main__":
    main()
