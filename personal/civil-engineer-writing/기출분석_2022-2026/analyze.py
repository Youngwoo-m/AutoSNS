"""Reproducible descriptive counts from the 15 downloaded Q-net papers.

Topic groups overlap and measure literal wording, not an official taxonomy.
"""
import csv
import json
import re
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent
THEMES = {
    '콘크리트·거푸집·양생': '콘크리트|거푸집|양생|혼화|철근|프리캐스트',
    '토공·다짐': '토공|다짐|흙쌓기|성토|절토|뒤채움|노체|노상',
    '지반·기초·흙막이': '지반|기초|말뚝|흙막이|앵커|압밀|지하수|옹벽',
    '터널': '터널|NATM|TBM|숏크리트',
    '교량·강교': '교량|강교|거더|사장교|현수교|교대|교각|FCM|ILM|FSM',
    '도로·포장': '도로|포장|아스팔트',
    '하천·댐·항만': '하천|제방|댐|항만|방파제|케이슨|준설|안벽|매립',
    '상하수도·관로': '상수|하수|관로|수격',
    '유지관리·노후·갱생': '유지관리|노후|갱생',
    '스마트·디지털': '스마트|BIM|인공지능|데이터센터|지능형|디지털|드론|ICT|IoT|(?<![A-Z])AI(?![A-Z])',
}
REQUESTS = {
    '원인·대책 요구': '원인|대책',
    '유의·주의·고려·검토 요구': '유의|주의|고려|검토|착안|준수',
    '비교·장단점 요구': '비교|장.?단점',
    '시공관리·품질관리 요구': '시공관리|품질관리|중점관리',
    '기준·법령 요구': '기준|법률|법령|시행령|시방서|법규',
}

sources = json.loads((ROOT/'회차목록.json').read_text())
assert sorted(r['round'] for r in sources) == list(range(126, 141))
questions = []
instructions = {}
for source in sorted(sources, key=lambda r: r['round']):
    pages = []
    with pdfplumber.open(ROOT/f"{source['round']}.pdf") as pdf:
        assert len(pdf.pages) == 4
        for period, page in enumerate(pdf.pages, 1):
            text = page.extract_text(x_tolerance=1)
            pages.append(text)
            matches = list(re.finditer(r'^\s*(\d{1,2})\s*\.\s*', text, re.M))
            expected = list(range(1, 14 if period == 1 else 7))
            assert [int(m[1]) for m in matches] == expected, (source['round'], period)
            instructions[f"{source['round']}-{period}"] = text[:matches[0].start()]
            for i, match in enumerate(matches):
                end = matches[i+1].start() if i+1 < len(matches) else len(text)
                content = text[match.end():end]
                content = re.split(r'\n\s*\d+\s*[-–—]\s*\d+|\n\s*[“"※]?\s*채점기준', content)[0]
                content = re.sub(r'\s+', ' ', content).strip()
                assert '채점기준' not in content and content
                questions.append(dict(
                    id=f"{source['round']}-{period}-{match[1]}",
                    year=source['year'], round=source['round'], period=period,
                    number=int(match[1]), kind='단답형' if period == 1 else '논술형',
                    question=content, source=source['url'],
                ))
    (ROOT/f"{source['round']}_layout.txt").write_text('\n\f\n'.join(pages))

assert len(questions) == 465
assert len({q['id'] for q in questions}) == 465
assert sum(q['period'] == 1 for q in questions) == 195
assert all(sum(q['year'] == y for q in questions) == 93 for y in range(2022, 2027))

def hits(pattern, pool):
    return [q for q in pool if re.search(pattern, re.sub(r'\s+', '', q['question']), re.I)]

themes = []
for name, pattern in THEMES.items():
    matched = hits(pattern, questions)
    themes.append(dict(theme=name, rule=pattern, count=len(matched),
                       round_count=len({q['round'] for q in matched}),
                       by_year={str(y):sum(q['year'] == y for q in matched) for y in range(2022, 2027)},
                       ids=[q['id'] for q in matched]))
essays = [q for q in questions if q['period'] > 1]
requests = [dict(name=name, rule=pattern, count=len(hits(pattern, essays)),
                 ids=[q['id'] for q in hits(pattern, essays)]) for name, pattern in REQUESTS.items()]
stats = dict(scope='2022~2026, 제126~140회', total=465, short=195, essay=270,
             method='공백 제거 후 정규식 검색. 문항당 각 그룹에서 1회, 그룹 간 중복 허용. 공종별 배타 분류나 공식 출제 비중이 아님.',
             themes=themes, essay_requests=requests)
(ROOT/'전체465문항.json').write_text(json.dumps(questions, ensure_ascii=False, indent=2))
with (ROOT/'전체465문항.csv').open('w', encoding='utf-8-sig', newline='') as f:
    writer=csv.DictWriter(f, fieldnames=list(questions[0]));writer.writeheader();writer.writerows(questions)
(ROOT/'키워드집계.json').write_text(json.dumps(stats, ensure_ascii=False, indent=2))
(ROOT/'교시별문항안내.json').write_text(json.dumps(instructions, ensure_ascii=False, indent=2))
print(json.dumps(stats, ensure_ascii=False, indent=2))
