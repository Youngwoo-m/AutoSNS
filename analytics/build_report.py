"""수집 결과를 합쳐 주간 리포트(HTML)와 스냅샷을 만든다. 표준 라이브러리만 쓴다.

지난 7일 현황을 중심에 두고, 직전 스냅샷과 비교해 전주 대비 증감과 구독자·팔로워
변화를 붙인다. 스냅샷이 없으면(첫 실행) 비교 항목은 생략한다.
"""
import glob
import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import OUT_DIR, SNAP_DIR, log, load_part  # noqa: E402

MED = ["유튜브", "인스타그램", "네이버 블로그", "학과 홈페이지"]
TYP = ["영상", "숏츠", "이미지", "카드뉴스", "게시글"]
COLOR = {"유튜브": "#B0402F", "인스타그램": "#6B4E9E",
         "네이버 블로그": "#2F6E4E", "학과 홈페이지": "#35617F"}


def merge():
    rows = []
    yt = load_part("youtube") or {"items": [], "channel": {}}
    ig = load_part("instagram") or {"items": [], "profile": {}}
    bl = load_part("blog") or {"items": []}
    sm = load_part("smds") or {"items": []}
    for x in yt["items"]:
        rows.append({**x, "media": "유튜브"})
    for x in ig["items"]:
        rows.append({**x, "media": "인스타그램"})
    for x in bl["items"]:
        rows.append({**x, "media": "네이버 블로그"})
    for x in sm["items"]:
        rows.append({**x, "media": "학과 홈페이지"})
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows, yt.get("channel", {}), ig.get("profile", {}), ig.get("skipped")


def prev_snapshot(today):
    """오늘 것을 뺀 가장 최근 스냅샷."""
    files = sorted(glob.glob(os.path.join(SNAP_DIR, "20*.json")))
    files = [f for f in files if os.path.basename(f) != f"{today}.json"]
    if not files:
        return None
    with open(files[-1], "r", encoding="utf-8") as f:
        return json.load(f)


def _table(headers, body_rows, aligns=None):
    a = aligns or ["left"] * len(headers)
    th = "".join(f'<th style="text-align:{x};padding:7px 10px;border-bottom:1px solid #ddd;'
                 f'font-size:12px;color:#666;font-weight:600">{h}</th>' for h, x in zip(headers, a))
    tr = ""
    for r in body_rows:
        tds = "".join(f'<td style="text-align:{x};padding:7px 10px;border-bottom:1px solid #f0f0f0;'
                      f'font-size:13px">{c}</td>' for c, x in zip(r, a))
        tr += f"<tr>{tds}</tr>"
    return (f'<table style="border-collapse:collapse;width:100%;margin:8px 0 18px">'
            f"<thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table>")


def build(rows, channel, profile, skipped, today, since="2026-03-01"):
    d0 = datetime.strptime(today, "%Y-%m-%d")
    wk_start = (d0 - timedelta(days=7)).strftime("%Y-%m-%d")
    pw_start = (d0 - timedelta(days=14)).strftime("%Y-%m-%d")
    week = [r for r in rows if wk_start <= r["date"] < today]
    prev_week = [r for r in rows if pw_start <= r["date"] < wk_start]
    cum = [r for r in rows if r["date"] >= since]
    prev = prev_snapshot(today)

    def delta(now, before):
        if before is None:
            return ""
        d = now - before
        color = "#C2410C" if d > 0 else "#666"
        sign = "+" if d > 0 else ""
        return f' <span style="color:{color};font-size:12px">({sign}{d})</span>'

    H = []
    H.append('<div style="font-family:-apple-system,\'Apple SD Gothic Neo\',sans-serif;'
             'max-width:720px;margin:0 auto;color:#1C1D1F;line-height:1.6">')
    H.append(f'<p style="font-size:12px;letter-spacing:.1em;color:#C2410C;margin:0 0 4px">'
             f'세명대학교 재난안전학과</p>')
    H.append(f'<h1 style="font-size:22px;margin:0 0 6px">SNS 주간 리포트</h1>')
    H.append(f'<p style="color:#555;font-size:14px;margin:0 0 20px">'
             f'{wk_start} ~ {(d0 - timedelta(days=1)).strftime("%Y-%m-%d")} · '
             f'이번 주 <b>{len(week)}건</b> 발행'
             f'{delta(len(week), len(prev_week) if prev_week else None)}</p>')

    if skipped:
        H.append('<p style="background:#FBEDE6;padding:10px 12px;border-radius:4px;font-size:13px;'
                 'margin:0 0 18px">인스타그램 세션이 만료되어 이번 주 인스타 수치는 빠져 있습니다. '
                 '크롬 프로필로 다시 로그인해 주세요.</p>')

    H.append('<h2 style="font-size:15px;margin:22px 0 0">이번 주 매체별 발행</h2>')
    body = []
    for m in MED:
        n = sum(1 for r in week if r["media"] == m)
        p = sum(1 for r in prev_week if r["media"] == m)
        bar = (f'<span style="display:inline-block;height:8px;border-radius:2px;'
               f'background:{COLOR[m]};width:{min(n * 12, 180)}px"></span>')
        body.append([f'<b style="color:{COLOR[m]}">{m}</b>', f"{n}{delta(n, p)}", bar])
    H.append(_table(["매체", "건수", ""], body, ["left", "right", "left"]))

    H.append('<h2 style="font-size:15px;margin:22px 0 0">이번 주 유형별</h2>')
    wc, pc = Counter(r["type"] for r in week), Counter(r["type"] for r in prev_week)
    H.append(_table(["유형", "건수"], [[t, f"{wc.get(t, 0)}{delta(wc.get(t, 0), pc.get(t))}"]
                                     for t in TYP if wc.get(t) or pc.get(t)], ["left", "right"]))

    subs, fol = channel.get("subscribers"), profile.get("followers")
    ps = (prev or {}).get("subscribers")
    pf = (prev or {}).get("followers")
    H.append('<h2 style="font-size:15px;margin:22px 0 0">채널 규모</h2>')
    H.append(_table(["지표", "현재"], [
        ["유튜브 구독자", f"{subs}명{delta(subs, ps) if subs is not None else ''}"],
        ["인스타 팔로워", f"{fol}명{delta(fol, pf) if fol is not None else ''}" if fol else "—"],
        ["유튜브 누적 조회", f"{channel.get('total_views', 0):,}회"],
    ], ["left", "right"]))

    ytw = [r for r in week if r["media"] == "유튜브"]
    if ytw:
        H.append('<h2 style="font-size:15px;margin:22px 0 0">이번 주 유튜브 조회</h2>')
        H.append(_table(["조회", "제목"], [
            [f"{r['views']:,}", f'<a href="{r["url"]}" style="color:#1C1D1F">{r["title"][:52]}</a>']
            for r in sorted(ytw, key=lambda x: -x["views"])[:5]], ["right", "left"]))

    H.append('<h2 style="font-size:15px;margin:22px 0 0">이번 주 발행 목록</h2>')
    if week:
        H.append(_table(["매체", "유형", "활동명", "게시일"], [
            [f'<span style="color:{COLOR[r["media"]]}">{r["media"]}</span>', r["type"],
             f'<a href="{r["url"]}" style="color:#1C1D1F;text-decoration:none">{r["title"][:46] or "(제목 없음)"}</a>',
             r["date"]] for r in week]))
    else:
        H.append('<p style="font-size:13px;color:#666">이번 주 발행이 없습니다.</p>')

    H.append(f'<h2 style="font-size:15px;margin:22px 0 0">누적 추이 ({since} ~)</h2>')
    months = sorted({r["date"][:7] for r in cum})
    H.append(_table(["월"] + MED + ["합계"], [
        [mo] + [str(sum(1 for r in cum if r["date"][:7] == mo and r["media"] == m)) for m in MED]
        + [f'<b>{sum(1 for r in cum if r["date"][:7] == mo)}</b>']
        for mo in months], ["left"] + ["right"] * 5))

    alerts = []
    empty = [r for r in week if r["media"] == "인스타그램" and r.get("caption_empty")]
    if empty:
        alerts.append(f"인스타 {len(empty)}건이 캡션 없이 발행됐습니다. 해시태그·검색 노출이 닫힙니다.")
    for m in MED:
        if not any(r["media"] == m for r in week):
            alerts.append(f"{m}: 이번 주 발행 0건")
    if alerts:
        H.append('<h2 style="font-size:15px;margin:22px 0 0">점검 필요</h2>'
                 '<ul style="font-size:13px;color:#333;padding-left:18px;margin:8px 0 0">'
                 + "".join(f"<li>{a}</li>" for a in alerts) + "</ul>")

    H.append(f'<p style="margin-top:28px;padding-top:12px;border-top:1px solid #ddd;'
             f'font-size:11px;color:#888">누적 {len(cum)}건 · {today} 자동 집계 · '
             f'유튜브 Data API, 인스타 계정 조회, 블로그·홈페이지 공개 목록</p></div>')

    snap = {"date": today, "week_count": len(week), "cum_count": len(cum),
            "subscribers": subs, "followers": fol,
            "total_views": channel.get("total_views"),
            "by_media": {m: sum(1 for r in week if r["media"] == m) for m in MED}}
    return "".join(H), snap


if __name__ == "__main__":
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    rows, channel, profile, skipped = merge()
    html, snap = build(rows, channel, profile, skipped, today)
    out = os.path.join(OUT_DIR, f"weekly_{today}.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    with open(os.path.join(SNAP_DIR, f"{today}.json"), "w", encoding="utf-8") as f:
        json.dump(snap, f, ensure_ascii=False, indent=1)
    log(f"리포트 생성: {out} (이번 주 {snap['week_count']}건, 누적 {snap['cum_count']}건)")
    print(out)
