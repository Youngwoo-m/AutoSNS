"""⓪ 기획 에이전트 — 계정별 주간 주제 제안. 발행·예약은 하지 않고 제안만 낸다.

    python planner.py <계정> <개수>     → JSON 한 줄 {proposals:[…], log, usage}
콘솔 서버가 youtube-shorts-auto/.venv 파이썬으로, youtube-shorts-auto 폴더에서 부른다.

근거: 뉴스(네이버 뉴스), 웹 검색, 구글 검색어(서치콘솔), 시즌 달력, 진행 중 시리즈, 지난 글,
(개인) 기술사 기출 우선순위, 사람이 최근에 반려한 제안과 그 이유.
"""
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent_core import CONSOLE, ROOT, Agent, Budget, Tool, load_settings, submit_tool  # noqa: E402
from drafter import Research, exam_topics, past_titles  # noqa: E402

SITES = {'dept': ['https://smuds2026.blogspot.com/'],
         'personal': ['https://geoaina.blogspot.com/', 'https://na-geoai.tistory.com/']}
CHANNELS = {'dept': ['naver_blog', 'blogger', 'instagram', 'youtube', 'x', 'threads'],
            'personal': ['blogger', 'tistory', 'youtube']}


def search_queries(days=28):
    """구글 검색에서 우리 사이트로 들어온 검색어(노출·클릭 상위). 개인 서치콘솔 토큰을 쓴다."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from shared import secret_env
    raw = secret_env.read().get('SEARCHCONSOLE_TOKEN')
    c = Credentials.from_authorized_user_info(json.loads(raw) if isinstance(raw, str) else raw)
    if not c.valid:
        c.refresh(Request())
    svc = build('searchconsole', 'v1', credentials=c, cache_discovery=False)
    end = datetime.date.today() - datetime.timedelta(days=3)
    start = end - datetime.timedelta(days=int(days))
    out = {}
    for site in SITES[ACCOUNT]:
        r = svc.searchanalytics().query(siteUrl=site, body={
            'startDate': str(start), 'endDate': str(end), 'dimensions': ['query'], 'rowLimit': 25}).execute()
        tot = svc.searchanalytics().query(siteUrl=site, body={'startDate': str(start), 'endDate': str(end)}).execute().get('rows', [{}])
        rows = [{'검색어': x['keys'][0], '노출': x['impressions'], '클릭': x['clicks'], '순위': round(x['position'], 1)}
                for x in r.get('rows', [])]
        out[site] = {'기간 전체': {'노출': (tot or [{}])[0].get('impressions', 0), '클릭': (tot or [{}])[0].get('clicks', 0)},
                     '검색어': rows or '노출이 적어 구글이 검색어를 보여 주지 않음 — 검색 유입을 늘릴 주제(사람들이 찾는 표현)를 우선 고려'}
    return out


def season_now():
    s = json.loads((CONSOLE / 'config' / 'season.json').read_text())
    today = datetime.date.today()
    nxt = (today.month % 12) + 1
    return {'오늘': str(today), '이번 달': s['months'][str(today.month)], '다음 달': s['months'][str(nxt)], '지역': s.get('region')}


def series_status():
    out = {}
    try:
        sch = json.loads((ROOT / 'channels' / 'youtube-shorts-auto' / 'publish_schedule.json').read_text())
        out['숏츠 예정'] = [f"{x['date']} {x.get('label', '')} {x.get('title', '')[:40]}" for x in sch if not x.get('published')][:5]
    except (OSError, ValueError):
        pass
    try:
        cat = json.loads((CONSOLE / 'config' / 'automations.json').read_text())['jobs']
        out['자동 작업(이미 정기로 다루는 것)'] = [f"{j['name']}: {j['what'][:60]}" for j in cat
                                          if any(c[0] == ACCOUNT for c in j['channels'])]
    except (OSError, ValueError, KeyError):
        pass
    return out


def rejections():
    p = CONSOLE / 'data' / 'proposals' / 'feedback.jsonl'
    rows = [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    rows = [r for r in rows if r.get('account') == ACCOUNT]
    return [f"{r['decision']}: {r['topic']}" + (f" — 이유: {r['reason']}" if r.get('reason') else '') for r in rows[-15:]]


def main():
    global ACCOUNT
    ACCOUNT, count = sys.argv[1], int(sys.argv[2])
    rs = Research(6)
    S = lambda **p: {'type': 'object', 'properties': p, 'required': [k for k in p if k not in ('days',)]}
    st = {'type': 'string'}
    tools = [
        Tool('season_now', '이번 달·다음 달 재난 유형과 학과 일정', S(), season_now, max_calls=1),
        Tool('series_status', '진행 중 시리즈와 이미 정기로 다루는 자동 작업(겹치지 않게)', S(), series_status, max_calls=1),
        Tool('search_queries', '구글 검색에서 우리 사이트로 들어온 검색어 상위', S(days={'type': 'integer'}), search_queries, max_calls=1),
        Tool('search_news', '네이버 뉴스 검색(최신순)', S(query=st), rs.search_news, max_calls=6),
        Tool('search_web', '네이버 웹문서·블로그 검색', S(query=st), rs.search_web, max_calls=3),
        Tool('fetch_page', '근거 문서 읽기(꼭 필요할 때만)', S(url=st), rs.fetch_page, max_calls=6),
        Tool('past_titles', '지난 글·영상 제목 검색(중복 피하기)', {'type': 'object', 'properties': {'query': st}}, past_titles, max_calls=6),
    ]
    if ACCOUNT == 'personal':
        tools.append(Tool('exam_topics', '기술사 기출 분야별 우선순위', S(), exam_topics, max_calls=1))
    chans = CHANNELS[ACCOUNT]
    tools.append(submit_tool('제안 제출', {'type': 'object', 'properties': {'proposals': {'type': 'array', 'items': {
        'type': 'object', 'properties': {
            'topic': {'type': 'string', 'description': '주제(제목처럼 짧게)'},
            'summary': {'type': 'string', 'description': '무엇을 다루나 한두 문장'},
            'why_now': {'type': 'string', 'description': '왜 지금인가(시즌·뉴스·검색어·시리즈 공백 중 해당하는 것)'},
            'evidence': {'type': 'array', 'items': {'type': 'string'}, 'description': '근거 주소(검색으로 찾은 것만)·검색어'},
            'channels': {'type': 'array', 'items': {'type': 'string', 'enum': chans}},
            'format': {'type': 'string', 'description': '블로그 글 / 카드뉴스 / 숏츠 대본 등'},
            'overlap': {'type': 'string', 'description': '겹치는 지난 글이 있으면 제목과 다른 점, 없으면 빈칸'}},
        'required': ['topic', 'summary', 'why_now', 'channels', 'format']}}}, 'required': ['proposals']}))
    who = {'dept': '세명대학교 재난안전학과 공식 채널(수험생·학부모·재학생·제천/충북 주민). 생활안전, 시즌 재난 대비, 진로·자격증, 학과 소식.',
           'personal': '공간정보·GeoAI 개인 전문가 채널(실무자·측량/토목 기술사 수험생). GeoAI 개념·실습, 기술 동향, 기술사 답안·기출.'}[ACCOUNT]
    rej = rejections()
    system = f"""너는 SNS 콘텐츠 기획자다. 채널: {who}
이번 주에 쓸 주제 {count}개를 제안한다. 순서:
1. season_now, series_status 로 시기와 이미 하는 일을 본다. 정기 자동 작업과 같은 주제는 피한다.
2. search_queries 로 사람들이 실제로 찾는 표현을 보고, search_news 로 최근 1~2주 소식을 본다.
3. past_titles 로 후보마다 지난 글과 겹치는지 확인한다.
4. 제안마다 '왜 지금인가'와 근거(실제로 검색한 주소·검색어)를 단다. 근거를 지어내지 않는다.
5. 사고 현장·피해 묘사보다 대비·대응·진로 중심으로. 특정인 비난·정치적 주장은 제안하지 않는다.
사람이 전에 반려·채택한 기록(이 취향을 따른다):
{chr(10).join('- ' + r for r in rej) or '- (아직 없음)'}"""
    b = load_settings().get('planner', {}).get('budget', {})
    a = Agent('planner', system, tools, Budget(max_tokens=int(b.get('max_tokens', 150000)), max_tool_calls=30, max_turns=20, max_output=6000))
    r = a.run(f'{ACCOUNT} 계정의 이번 주 주제를 {count}개 제안하라.')
    if r.status != 'submitted':
        print(json.dumps({'error': f'{r.status}: {r.detail}', 'log': r.log}, ensure_ascii=False))
        return
    props = r.result.get('proposals') or []
    for p in props:
        p['channels'] = [c for c in p.get('channels', []) if c in chans] or chans[:2]
    print(json.dumps({'proposals': props[:count], 'log': r.log, 'usage': r.usage}, ensure_ascii=False))


ACCOUNT = 'dept'
if __name__ == '__main__':
    main()
