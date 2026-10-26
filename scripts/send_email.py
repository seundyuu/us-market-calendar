#!/usr/bin/env python3
"""Email the latest trading day's summary through Gmail SMTP.

Environment:
  GMAIL_USER          Gmail address that sends the mail
  GMAIL_APP_PASSWORD  16-character Google app password for that account
  MAIL_TO             recipient(s), comma separated (defaults to GMAIL_USER)
  PREVIEW_FILE        if set, write the HTML here instead of sending
"""
import html
import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = "https://seundyuu.github.io/us-market-calendar/"
IDX = [("spx", "S&P 500", "미국 대표 기업 500곳"), ("ndx", "나스닥", "기술·성장주 중심"), ("dji", "다우", "전통 대형주 30곳")]
DOW = "월화수목금토일"
UP, DOWN, FLAT, MUTED, LINE = "#e5322d", "#2a6df4", "#8e8e93", "#86868b", "#e5e5ea"


def load(name):
    p = ROOT / "data" / name
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def pct(v):
    return ("+" if v > 0 else "−" if v < 0 else "") + f"{abs(v):.2f}%"


def color(v):
    return UP if v >= 0.1 else DOWN if v <= -0.1 else FLAT


def tag_word(v):
    a = abs(v)
    if a < 0.1:
        return "보합"
    if a >= 2:
        return "급등" if v > 0 else "급락"
    size = "조금" if a < 0.5 else "꽤" if a < 1 else "크게"
    return f"{size} {'오름' if v > 0 else '내림'}"


def date_ko(day):
    import datetime as dt
    d = dt.date.fromisoformat(day)
    return f"{d.month}/{d.day}({DOW[d.weekday()]})"


def build(days, sectors):
    trade = [k for k in sorted(days) if days[k].get("indices")]
    day = trade[-1]
    rec = days[day]
    ix = rec["indices"]
    spx = ix["spx"]["chg"]
    e = html.escape

    subject = f"[미국 증시] {date_ko(day)} S&P 500 {pct(spx)} · {tag_word(spx)}"

    if abs(spx) < 0.1:
        headline = f"미국 대표 기업 500곳을 묶은 S&P 500이 거의 변화가 없었어요({pct(spx)})."
    else:
        headline = f"미국 대표 기업 500곳을 묶은 S&P 500이 {abs(spx):.2f}% {'올랐어요' if spx > 0 else '내렸어요'}."

    rows = "".join(
        f'<tr><td style="padding:8px 0;border-top:1px solid {LINE}"><b>{name}</b><br>'
        f'<span style="font-size:12px;color:{MUTED}">{about}</span></td>'
        f'<td style="padding:8px 0;border-top:1px solid {LINE};text-align:right;color:{MUTED}">{ix[k]["close"]:,.2f}</td>'
        f'<td style="padding:8px 0 8px 14px;border-top:1px solid {LINE};text-align:right;font-weight:600;color:{color(ix[k]["chg"])}">{pct(ix[k]["chg"])}</td></tr>'
        for k, name, about in IDX
    )

    news = ""
    if rec.get("summary"):
        def items(title, key, c):
            lst = rec.get(key) or []
            if not lst:
                return ""
            lis = "".join(
                f'<li style="margin:0 0 6px"><b>{e(it.get("title", ""))}</b>'
                + (f'<br><span style="color:{MUTED}">{e(it["note"])}</span>' if it.get("note") else "")
                + "</li>"
                for it in lst
            )
            return f'<p style="margin:14px 0 6px;font-weight:600;color:{c}">{title}</p><ul style="margin:0;padding-left:18px">{lis}</ul>'

        news = (
            f'<h2 style="font-size:16px;margin:28px 0 8px">왜 이렇게 움직였을까?</h2>'
            f'<p style="margin:0;line-height:1.65">{e(rec["summary"])}</p>'
            + items("좋은 소식 (호재)", "bullish", UP)
            + items("나쁜 소식 (악재)", "bearish", DOWN)
        )
    else:
        news = f'<p style="margin:24px 0 0;color:{MUTED}">이날의 뉴스 해석은 아직 준비되지 않았어요. 캘린더에서 나중에 확인할 수 있어요.</p>'

    sector_html = ""
    rows_s = [s for s in (sectors or {}).get("sectors", []) if s.get("m1") is not None]
    if rows_s:
        rows_s.sort(key=lambda s: s["m1"], reverse=True)
        def line(s):
            return f'<li style="margin:0 0 4px">{e(s["name"])} <span style="color:{color(s["m1"])};font-weight:600">{pct(s["m1"])}</span> <span style="color:{MUTED};font-size:12px">{e(s["about"])}</span></li>'
        sector_html = (
            f'<h2 style="font-size:16px;margin:28px 0 8px">요즘 업종 흐름 (최근 1개월)</h2>'
            f'<p style="margin:0 0 4px;font-weight:600;color:{UP}">강한 업종</p><ul style="margin:0 0 10px;padding-left:18px">{"".join(line(s) for s in rows_s[:3])}</ul>'
            f'<p style="margin:0 0 4px;font-weight:600;color:{DOWN}">약한 업종</p><ul style="margin:0;padding-left:18px">{"".join(line(s) for s in rows_s[-3:][::-1])}</ul>'
        )

    body = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head><body style="margin:0;background:#f5f5f7">
<div style="max-width:560px;margin:0 auto;padding:24px 16px;font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Noto Sans KR','Malgun Gothic',sans-serif;color:#1d1d1f;font-size:14px">
 <div style="background:#fff;border-radius:14px;padding:22px 20px;border:1px solid {LINE}">
  <p style="margin:0;font-size:13px;color:{MUTED}">{date_ko(day)} 뉴욕 장 마감 · 한국 시간 다음 날 새벽 확정</p>
  <p style="margin:6px 0 2px;font-size:13px;font-weight:600;color:{color(spx)}">{tag_word(spx)}</p>
  <h1 style="margin:0 0 10px;font-size:24px">S&amp;P 500 <span style="color:{color(spx)}">{pct(spx)}</span></h1>
  <p style="margin:0 0 14px;font-size:15px;line-height:1.6">{headline}</p>
  <table style="width:100%;border-collapse:collapse;font-size:14px">{rows}</table>
  {news}
  {sector_html}
  <p style="margin:28px 0 0"><a href="{SITE}" style="display:inline-block;background:#1d1d1f;color:#fff;text-decoration:none;padding:10px 16px;border-radius:8px;font-weight:600">캘린더에서 자세히 보기</a></p>
 </div>
 <p style="font-size:12px;color:{MUTED};line-height:1.6;margin:14px 4px 0">데이터: Yahoo Finance 종가. 뉴스 해석은 Claude가 기사를 찾아 요약한 내용이에요. 특정 종목을 사거나 팔라는 추천이 아니며 투자 조언이 아닙니다.</p>
</div></body></html>"""

    news_text = rec.get("summary") or "뉴스 해석은 아직 준비되지 않았어요."
    text = (
        f"{subject}\n\n{headline}\n\n"
        + "\n".join(f"{name}: {ix[k]['close']:,.2f} ({pct(ix[k]['chg'])})" for k, name, _ in IDX)
        + f"\n\n{news_text}\n\n캘린더: {SITE}\n\n투자 조언이 아닙니다."
    )
    return subject, text, body


def main():
    days = load("days.json")
    subject, text, body = build(days, load("sectors.json"))

    preview = os.environ.get("PREVIEW_FILE")
    if preview:
        Path(preview).write_text(body, "utf-8")
        print(f"preview written: {subject}")
        return

    user = os.environ["GMAIL_USER"]
    password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
    to = [a.strip() for a in (os.environ.get("MAIL_TO") or user).split(",") if a.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"미국 증시 캘린더 <{user}>"
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    msg.add_alternative(body, subtype="html")

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as smtp:
        smtp.login(user, password)
        smtp.send_message(msg)
    print(f"sent to {len(to)} recipient(s): {subject}")


if __name__ == "__main__":
    main()
