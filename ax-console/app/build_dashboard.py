"""AutoSNS 운영 대시보드: 저장소의 상태 파일을 읽어 dashboard/index.html 한 장을 만든다.

실행: python3 ax-console/app/build_dashboard.py  → ax-console/data/dashboard/index.html 을 브라우저로 연다.
질문 큐는 사용자가 보낸 글이므로 제목만 이스케이프해서 보여 주고 본문·닉네임은 싣지 않는다.
"""
import datetime, html, json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'ax-console' / 'data' / 'dashboard' / 'index.html'
TODAY = datetime.date.today()


def load(path, default):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def esc(s):
    return html.escape(str(s))


def shorts():
    items = load(ROOT / 'channels/youtube-shorts-auto/publish_schedule.json', [])
    done = [x for x in items if x.get('published')]
    todo = sorted((x for x in items if not x.get('published')), key=lambda x: x['date'])
    overdue = [x for x in todo if x['date'] < TODAY.isoformat()]
    return items, done, todo, overdue


def series():
    rows = []
    for d in sorted((ROOT / 'GeoAI_NA' / 'civil-engineer-writing').glob('*일차_*')):
        st = load(d / '발행결과.json', None) or load(d / '작성상태.json', {})
        rows.append((st.get('종목', ''), st.get('일차', d.name), d.name.split('_', 1)[-1], st.get('상태', '상태 파일 없음')))
    return rows


def queue():
    jobs = load(ROOT / 'GeoAI_NA' / 'engineer-question-worker' / 'state.json', {}).get('jobs', {}).values()
    return Counter(j.get('status') for j in jobs), sorted(jobs, key=lambda j: j.get('created_at', ''), reverse=True)[:8]


LABEL = {'queued': '대기', 'processing': '작성 중', 'published': '발행됨', 'done': '완료', 'failed': '실패'}


def build():
    items, done, todo, overdue = shorts()
    rows = series()
    qc, jobs = queue()
    nxt = todo[0] if todo else None
    kpi = [
        ('숏츠 발행', f'{len(done)}<small>/{len(items)}</small>', ''),
        ('다음 발행', esc(nxt['date'][5:]) if nxt else '—', esc(nxt.get('label', '')) if nxt else '예정 없음'),
        ('지난 예정 미발행', str(len(overdue)), 'warn' if overdue else 'ok'),
        ('질문 대기', str(qc.get('queued', 0) + qc.get('processing', 0)), f"완료 {qc.get('done', 0) + qc.get('published', 0)}"),
    ]
    kpi_html = ''.join(
        f'<div class="kpi {c if c in ("warn","ok") else ""}"><span>{t}</span><b>{v}</b>'
        f'<em>{"" if c in ("warn","ok") else c}</em></div>' for t, v, c in kpi)

    sched = ''.join(
        f'<tr class="{"late" if x["date"] < TODAY.isoformat() else ""}"><td>{esc(x["date"])}</td>'
        f'<td><span class="tag">{esc(x.get("label") or x.get("series",""))}</span></td>'
        f'<td>{esc(x["title"].replace(" #Shorts",""))}</td></tr>' for x in todo[:10])
    recent = ''.join(
        f'<tr><td>{esc(x["date"])}</td><td><span class="tag">{esc(x.get("label",""))}</span></td>'
        f'<td>{"<a href=" + chr(34) + esc(x["published"]["youtube"]) + chr(34) + ">유튜브</a>" if str(x["published"].get("youtube","")).startswith("http") else ""}'
        f'{" · 인스타" if x["published"].get("instagram") else ""}</td></tr>'
        for x in sorted(done, key=lambda x: x['date'], reverse=True)[:6])
    ser = ''.join(f'<tr><td>{esc(a)}</td><td>{esc(b)}일차</td><td>{esc(c)}</td><td>{esc(d)}</td></tr>' for a, b, c, d in rows) \
        or '<tr><td colspan="4">연재 폴더가 없습니다</td></tr>'
    q = ''.join(f'<tr><td>{esc(j.get("created_at","")[:10])}</td><td><span class="st {esc(j.get("status"))}">'
                f'{LABEL.get(j.get("status"), esc(j.get("status")))}</span></td><td>{esc(j.get("title",""))}</td></tr>'
                for j in jobs) or '<tr><td colspan="3">접수된 질문이 없습니다</td></tr>'

    page = TEMPLATE.format(today=TODAY.isoformat(), built=datetime.datetime.now().strftime('%m-%d %H:%M'),
                           kpi=kpi_html, sched=sched or '<tr><td colspan="3">예정된 숏츠가 없습니다</td></tr>',
                           recent=recent, ser=ser, q=q)
    OUT.write_text(page)
    print(OUT)


TEMPLATE = '''<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>AutoSNS 운영 현황</title>
<style>
@font-face{{font-family:P;src:url(../../../assets/FONTS/Pretendard-Bold.otf);font-weight:700}}
:root{{--bg:#f4f6f8;--card:#fff;--ink:#17202a;--sub:#5f6b78;--line:#e3e7ec;--accent:#1f6feb;--warn:#c2410c;--ok:#15803d}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0f1419;--card:#182029;--ink:#e6edf3;--sub:#93a1b0;--line:#2a3541;--accent:#58a6ff;--warn:#fb923c;--ok:#4ade80}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:700 15px/1.5 P,-apple-system,sans-serif}}
main{{max-width:1180px;margin:auto;padding:24px 16px}}header{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px}}
h1{{font-size:24px;margin:0}}h2{{font-size:16px;margin:0 0 12px;color:var(--sub)}}header p{{color:var(--sub);margin:0;font-size:13px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}}
.kpi span{{color:var(--sub);font-size:13px}}.kpi b{{display:block;font-size:32px;line-height:1.2}}.kpi small{{font-size:16px;color:var(--sub)}}
.kpi em{{font-style:normal;color:var(--sub);font-size:13px}}.kpi.warn b{{color:var(--warn)}}.kpi.ok b{{color:var(--ok)}}
.grid{{display:grid;grid-template-columns:3fr 2fr;gap:12px}}@media(max-width:820px){{.grid{{grid-template-columns:1fr}}}}
section{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:14px}}td{{padding:8px 6px;border-top:1px solid var(--line);vertical-align:top}}
td:first-child{{white-space:nowrap;color:var(--sub)}}tr.late td:first-child{{color:var(--warn)}}
.tag{{background:color-mix(in srgb,var(--accent) 14%,transparent);color:var(--accent);border-radius:6px;padding:2px 8px;font-size:12px;white-space:nowrap}}
.st{{border-radius:6px;padding:2px 8px;font-size:12px;background:var(--line)}}.st.done,.st.published{{color:var(--ok)}}.st.failed{{color:var(--warn)}}
a{{color:var(--accent)}}.stack{{display:grid;gap:12px}}
</style></head><body><main>
<header><h1>AutoSNS 운영 현황</h1><p>세명대학교 재난안전학과 · 기준일 {today} · 생성 {built}</p></header>
<div class="kpis">{kpi}</div>
<div class="grid">
<section><h2>다가오는 숏츠 발행</h2><table>{sched}</table></section>
<div class="stack">
<section><h2>최근 발행</h2><table>{recent}</table></section>
<section><h2>기술사 질문 큐</h2><table>{q}</table></section>
</div></div>
<section style="margin-top:12px"><h2>기술사 답안 연재</h2><table>{ser}</table></section>
</main></body></html>'''

if __name__ == '__main__':
    build()
