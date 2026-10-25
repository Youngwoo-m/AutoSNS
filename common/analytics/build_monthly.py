"""지난달 활동을 분석해 월간 리포트(메일 본문 HTML, 한글 원고 md, 엑셀)를 만든다.

매월 1일에 돌면서 '방금 끝난 달'을 다룬다. 해석과 제안은 수치에서 규칙으로 뽑는다
(사람이 없는 시간에 돌아도 결과가 흔들리지 않게).

.venv 로 실행할 것: 엑셀 생성에 openpyxl 이 필요하다.
"""
import json
import os
import statistics
import sys
from collections import Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from analytics.common import OUT_DIR, log  # noqa: E402
from analytics.build_report import COLOR, MED, TYP, _table, merge  # noqa: E402

SINCE = "2026-03-01"


def prev_month(today):
    d = datetime.strptime(today, "%Y-%m-%d")
    y, m = (d.year, d.month - 1) if d.month > 1 else (d.year - 1, 12)
    return f"{y:04d}-{m:02d}"


def month_before(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y:04d}-{m - 1:02d}" if m > 1 else f"{y - 1:04d}-12"


def _avg(v):
    return round(statistics.mean(v)) if v else 0


def analyze(rows, ym):
    """이번 달·전월 수치와, 그 차이에서 뽑은 해석·제안."""
    cur = [r for r in rows if r["date"][:7] == ym]
    pre = [r for r in rows if r["date"][:7] == month_before(ym)]
    cum = [r for r in rows if r["date"] >= SINCE]

    def by(rs, key):
        return Counter(r[key] for r in rs)

    yt_cur = [r for r in cur if r["media"] == "유튜브"]
    yt_pre = [r for r in pre if r["media"] == "유튜브"]
    ig_cur = [r for r in cur if r["media"] == "인스타그램"]

    a = {
        "ym": ym, "cur": cur, "pre": pre, "cum": cum,
        "media_cur": by(cur, "media"), "media_pre": by(pre, "media"),
        "type_cur": by(cur, "type"), "type_pre": by(pre, "type"),
        "made_cur": sum(1 for r in cur if r["type"] != "게시글"),
        "made_pre": sum(1 for r in pre if r["type"] != "게시글"),
        "yt_views": sum(r.get("views", 0) for r in yt_cur),
        "yt_avg": _avg([r.get("views", 0) for r in yt_cur]),
        "yt_avg_pre": _avg([r.get("views", 0) for r in yt_pre]),
        "yt_top": sorted(yt_cur, key=lambda r: -r.get("views", 0))[:5],
        "ig_likes": _avg([r.get("likes", 0) for r in ig_cur]),
        "ig_empty": [r for r in ig_cur if r.get("caption_empty")],
        "silent": [m for m in MED if not any(r["media"] == m for r in cur)],
    }

    notes, plans = [], []
    d_total = len(cur) - len(pre)
    if pre:
        if d_total > 0:
            notes.append(f"전월보다 {d_total}건 늘어 {len(cur)}건을 발행했다.")
        elif d_total < 0:
            notes.append(f"전월보다 {-d_total}건 줄어 {len(cur)}건에 그쳤다.")
        else:
            notes.append(f"전월과 같은 {len(cur)}건을 발행했다.")
    if a["yt_avg"] and a["yt_avg_pre"]:
        r = a["yt_avg"] / a["yt_avg_pre"]
        if r >= 1.2:
            notes.append(f"유튜브 편당 평균 조회가 {a['yt_avg_pre']}회에서 {a['yt_avg']}회로 올랐다. "
                         "노출이 쌓이고 있다는 신호다.")
        elif r <= 0.8:
            notes.append(f"유튜브 편당 평균 조회가 {a['yt_avg_pre']}회에서 {a['yt_avg']}회로 내렸다. "
                         "소재나 발행 시각을 점검할 시점이다.")
    if a["made_cur"] and len(cur):
        share = round(a["made_cur"] / len(cur) * 100)
        notes.append(f"제작 콘텐츠(영상·숏츠·이미지·카드뉴스)는 {a['made_cur']}건으로 "
                     f"전체의 {share}%다. 나머지는 공지·블로그 게시글이다.")
    for m in a["silent"]:
        notes.append(f"{m}: 이번 달 발행이 없었다.")
        plans.append(f"{m} 발행 재개 — 최소 월 2건 목표")
    if a["ig_empty"]:
        plans.append(f"인스타 캡션 누락 {len(a['ig_empty'])}건 보완 — 해시태그·설명이 없으면 검색·추천 노출이 닫힌다")
    if a["yt_top"]:
        t = a["yt_top"][0]
        notes.append(f"가장 많이 본 콘텐츠는 '{t['title'][:40]}'({t.get('views', 0):,}회)다.")
        plans.append("반응이 높았던 소재(지역 재난 소식)를 다음 달 편성에 우선 배치")
    if not plans:
        plans.append("현 편성 유지 — 특이 사항 없음")
    a["notes"], a["plans"] = notes, plans
    return a


def build_html(a, channel, profile, warn=None):
    ym = a["ym"]
    H = ['<div style="font-family:-apple-system,\'Apple SD Gothic Neo\',sans-serif;'
         'max-width:720px;margin:0 auto;color:#1C1D1F;line-height:1.6">']
    H.append('<p style="font-size:12px;letter-spacing:.1em;color:#C2410C;margin:0 0 4px">'
             '세명대학교 재난안전학과</p>')
    H.append(f'<h1 style="font-size:22px;margin:0 0 6px">{int(ym[5:])}월 콘텐츠 활동 월간 리포트</h1>')
    H.append(f'<p style="color:#555;font-size:14px;margin:0 0 20px">'
             f'{ym} 발행 <b>{len(a["cur"])}건</b> '
             f'(제작 콘텐츠 {a["made_cur"]}건) · 전월 {len(a["pre"])}건</p>')
    for w in (warn or []):
        H.append('<p style="background:#FBEDE6;padding:10px 12px;border-radius:4px;font-size:13px;'
                 f'margin:0 0 10px">⚠ {w}</p>')

    H.append('<h2 style="font-size:15px;margin:22px 0 0">매체 × 유형</h2>')
    body = []
    for m in MED:
        rs = [r for r in a["cur"] if r["media"] == m]
        c = Counter(r["type"] for r in rs)
        body.append([f'<b style="color:{COLOR[m]}">{m}</b>']
                    + [str(c.get(t, 0)) if c.get(t) else "–" for t in TYP]
                    + [f"<b>{len(rs)}</b>"])
    tc = Counter(r["type"] for r in a["cur"])
    body.append(["<b>합계</b>"] + [f'<b>{tc.get(t, 0)}</b>' for t in TYP] + [f'<b>{len(a["cur"])}</b>'])
    H.append(_table(["매체"] + TYP + ["합계"], body, ["left"] + ["right"] * 6))

    H.append('<h2 style="font-size:15px;margin:22px 0 0">전월 대비</h2>')
    rows_d = []
    for m in MED:
        n, p = a["media_cur"].get(m, 0), a["media_pre"].get(m, 0)
        d = n - p
        mark = f'<span style="color:{"#C2410C" if d > 0 else "#666"}">{"+" if d > 0 else ""}{d}</span>'
        rows_d.append([m, str(p), str(n), mark])
    H.append(_table(["매체", "전월", "이번 달", "증감"], rows_d, ["left", "right", "right", "right"]))

    H.append('<h2 style="font-size:15px;margin:22px 0 0">성과</h2>')
    H.append(_table(["지표", "값"], [
        ["유튜브 이번 달 조회", f'{a["yt_views"]:,}회'],
        ["유튜브 편당 평균", f'{a["yt_avg"]}회 (전월 {a["yt_avg_pre"]}회)'],
        ["유튜브 구독자", f'{channel.get("subscribers", "—")}명'],
        ["인스타 팔로워", f'{profile.get("followers", "—")}명'],
        ["인스타 좋아요 평균", f'{a["ig_likes"]}개'],
    ], ["left", "right"]))

    if a["yt_top"]:
        H.append('<h2 style="font-size:15px;margin:22px 0 0">조회 상위</h2>')
        H.append(_table(["조회", "제목"], [
            [f'{r.get("views", 0):,}',
             f'<a href="{r["url"]}" style="color:#1C1D1F">{r["title"][:52]}</a>']
            for r in a["yt_top"]], ["right", "left"]))

    H.append('<h2 style="font-size:15px;margin:22px 0 0">해석</h2><ul style="font-size:13.5px;'
             'padding-left:18px;margin:8px 0 0">' + "".join(f"<li>{n}</li>" for n in a["notes"]) + "</ul>")
    H.append('<h2 style="font-size:15px;margin:22px 0 0">다음 달 제안</h2><ul style="font-size:13.5px;'
             'padding-left:18px;margin:8px 0 0">' + "".join(f"<li>{p}</li>" for p in a["plans"]) + "</ul>")

    H.append(f'<p style="margin-top:28px;padding-top:12px;border-top:1px solid #ddd;font-size:11px;'
             f'color:#888">첨부: 분석보고서(.hwpx), 활동목록(.xlsx) · 누적 {len(a["cum"])}건 '
             f'({SINCE} ~) · 자동 집계</p></div>')
    return "".join(H)


def build_md(a, channel, profile):
    ym = a["ym"]
    L = [f"# 세명대학교 재난안전학과 {int(ym[5:])}월 콘텐츠 활동 분석", "",
         f"집계 기간: {ym} 한 달  ", f"대상: 유튜브, 인스타그램, 네이버 블로그, 학과 홈페이지  ",
         f"발행: {len(a['cur'])}건 (제작 콘텐츠 {a['made_cur']}건, 전월 {len(a['pre'])}건)", "",
         "## 1. 매체 × 유형", "", "| 매체 | " + " | ".join(TYP) + " | 합계 |",
         "|---|" + "---|" * (len(TYP) + 1)]
    for m in MED:
        rs = [r for r in a["cur"] if r["media"] == m]
        c = Counter(r["type"] for r in rs)
        L.append(f"| {m} | " + " | ".join(str(c.get(t, 0)) for t in TYP) + f" | {len(rs)} |")
    tc = Counter(r["type"] for r in a["cur"])
    L.append("| 합계 | " + " | ".join(str(tc.get(t, 0)) for t in TYP) + f" | {len(a['cur'])} |")

    L += ["", "## 2. 전월 대비", "", "| 매체 | 전월 | 이번 달 | 증감 |", "|---|---|---|---|"]
    for m in MED:
        n, p = a["media_cur"].get(m, 0), a["media_pre"].get(m, 0)
        L.append(f"| {m} | {p} | {n} | {n - p:+d} |")

    L += ["", "## 3. 성과 지표", "", "| 지표 | 값 |", "|---|---|",
          f"| 유튜브 이번 달 조회 | {a['yt_views']:,}회 |",
          f"| 유튜브 편당 평균 | {a['yt_avg']}회 (전월 {a['yt_avg_pre']}회) |",
          f"| 유튜브 구독자 | {channel.get('subscribers', '—')}명 |",
          f"| 인스타 팔로워 | {profile.get('followers', '—')}명 |",
          f"| 인스타 좋아요 평균 | {a['ig_likes']}개 |"]
    if a["yt_top"]:
        L += ["", "조회 상위", "", "| 조회 | 게시일 | 제목 |", "|---|---|---|"]
        for r in a["yt_top"]:
            L.append(f"| {r.get('views', 0):,} | {r['date']} | {r['title'][:46].replace('|', '·')} |")

    L += ["", "## 4. 해석", ""] + [f"- {n}" for n in a["notes"]]
    L += ["", "## 5. 다음 달 제안", ""] + [f"- {p}" for p in a["plans"]]
    L += ["", "## 6. 이번 달 활동 목록", "", "| 매체명 | 유형 | 활동명 | 게시일 |", "|---|---|---|---|"]
    for r in sorted(a["cur"], key=lambda x: x["date"], reverse=True):
        name = (r["title"] or "(제목 없음)")[:52].replace("|", "·") + (" (제목 추정)" if r.get("title_inferred") else "")
        L.append(f"| {r['media']} | {r['type']} | {name} "
                 f"| {r['date']} |")
    L += ["", "## 7. 누적 월별 추이", "", "| 월 | " + " | ".join(MED) + " | 합계 |",
          "|---|" + "---|" * (len(MED) + 1)]
    for mo in sorted({r["date"][:7] for r in a["cum"]}):
        v = [sum(1 for r in a["cum"] if r["date"][:7] == mo and r["media"] == m) for m in MED]
        L.append(f"| {mo} | " + " | ".join(map(str, v)) + f" | {sum(v)} |")
    return "\n".join(L)


def build_xlsx(a, path):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "활동목록"
    head, fill = Font(bold=True, color="FFFFFF", size=10), PatternFill("solid", fgColor="3F4448")
    ws.append(["매체명", "유형", "활동명", "게시일", "조회수", "좋아요", "링크"])
    for c in ws[1]:
        c.font, c.fill = head, fill
        c.alignment = Alignment(horizontal="center")
    for r in sorted(a["cur"], key=lambda x: x["date"], reverse=True):
        ws.append([r["media"], r["type"],
                   (r["title"] or "(제목 없음)") + (" (제목 추정)" if r.get("title_inferred") else ""), r["date"],
                   r.get("views") or None, r.get("likes") or None, r["url"]])
    for w, l in zip([13, 10, 60, 12, 10, 9, 46], "ABCDEFG"):
        ws.column_dimensions[l].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:G{ws.max_row}"

    st = wb.create_sheet("통계")
    st.append(["매체"] + TYP + ["합계"])
    for c in st[1]:
        c.font, c.fill = head, fill
    for m in MED:
        rs = [r for r in a["cur"] if r["media"] == m]
        c = Counter(r["type"] for r in rs)
        st.append([m] + [c.get(t, 0) for t in TYP] + [len(rs)])
    st.append([])
    st.append(["전월 대비"])
    st.append(["매체", "전월", "이번 달", "증감"])
    for m in MED:
        n, p = a["media_cur"].get(m, 0), a["media_pre"].get(m, 0)
        st.append([m, p, n, n - p])
    st.append([])
    for k, v in [("유튜브 이번 달 조회", a["yt_views"]), ("유튜브 편당 평균", a["yt_avg"]),
                 ("인스타 좋아요 평균", a["ig_likes"]), ("캡션 누락", len(a["ig_empty"]))]:
        st.append([k, v])
    st.column_dimensions["A"].width = 24
    wb.save(path)


if __name__ == "__main__":
    today = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    ym = sys.argv[2] if len(sys.argv) > 2 else prev_month(today)
    rows, channel, profile, warn = merge()
    a = analyze(rows, ym)

    html_path = os.path.join(OUT_DIR, f"monthly_{ym}.html")
    md_path = os.path.join(OUT_DIR, f"monthly_{ym}.md")
    xlsx_path = os.path.join(OUT_DIR, f"monthly_{ym}.xlsx")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(build_html(a, channel, profile, warn))
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_md(a, channel, profile))
    build_xlsx(a, xlsx_path)
    with open(os.path.join(OUT_DIR, f"monthly_{ym}.subject.txt"), "w", encoding="utf-8") as f:
        f.write(f"[재난안전학과] {int(ym[5:])}월 콘텐츠 활동 월간 리포트")
    log(f"월간 리포트 생성: {ym} — {len(a['cur'])}건 (제작 {a['made_cur']}건)")
    print(html_path)
