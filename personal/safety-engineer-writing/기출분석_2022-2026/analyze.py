"""Reproducible descriptive counts from the 15 downloaded Q-net papers.

Topic groups overlap and measure literal wording, not an official taxonomy.
"""
import csv
import json
import re
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent
# 영문 약어는 대소문자를 구분하고 앞뒤가 영문자가 아닐 때만 센다(re.I 로 'Earth'·'Hazard' 안의 ar 이 AR 로 잡히던 문제)
def ACR(*xs): return '(?-i:(?<![A-Za-z])(?:' + '|'.join(xs) + ')(?![A-Za-z]))'

THEMES = {
    '법령·제도(산안법·중처법·건진법)': '산업안전보건법|산안법|중대재해|처벌법|건설기술진흥법|건진법|시행령|시행규칙|고시|법령|법률',
    '안전관리 체계·계획·위험성평가': '안전관리계획|안전보건관리체계|위험성평가|안전관리비|안전보건관리비|관리책임자|관리감독자|안전보건대장|유해위험방지계획|설계안전성|DFS|안전교육|도급',
    '가설구조물·추락·낙하': '가설|비계|거푸집|동바리|추락|개구부|작업발판|안전난간|낙하|비래|안전대',
    '토공·굴착·흙막이·붕괴': '굴착|흙막이|토공|사면|비탈면|붕괴|지반|옹벽|터널|발파|함몰',
    '건설기계·양중': '크레인|건설기계|양중|리프트|고소작업대|차량계|항타|항발|굴삭기|지게차|인양',
    '구조물 공종(콘크리트·철골·해체)': '콘크리트|철골|해체|용접|프리캐스트|교량|' + ACR('PC', 'PSC'),
    '화재·폭발·전기·질식': '화재|폭발|전기|감전|질식|밀폐공간|가스|화학',
    '보건·작업환경': '(?<!안전)보건|근골격|온열|폭염|열사병|한랭|소음|분진|석면|건강|휴게|작업환경|직무스트레스',
    '재해이론·인간공학·안전심리': '재해발생이론|인간공학|휴먼에러|착오|심리|하인리히|버드|도미노|스위스치즈|안전문화|리더십|동기|재해통계|재해율',
    '점검·유지관리·시설물안전': '안전점검|정밀안전|시설물|유지관리|노후|진단|내진|안전등급',
    '스마트안전·디지털': '스마트|가상현실|증강현실|인공지능|디지털|드론|웨어러블|센서|로봇|' + ACR('VR', 'AR', 'BIM', 'ICT', 'IoT', 'CCTV', 'AI'),
}
REQUESTS = {
    '원인·대책 요구': '원인|대책',
    '유의·주의·고려·검토 요구': '유의|주의|고려|검토|착안|준수',
    '비교·장단점 요구': '비교|장.?단점',
    '안전관리·점검 요구': '안전관리|안전점검|관리방안|관리대책|점검사항',
    '기준·법령 요구': '기준|법률|법령|시행령|시행규칙|시방서|고시|법규|지침',
}

sources = json.loads((ROOT/'회차목록.json').read_text())
assert sorted(r['round'] for r in sources) == list(range(126, 141))
questions = []
instructions = {}
for source in sorted(sources, key=lambda r: r['round']):
    pages = []
    manual = ROOT/f"{source['round']}_수기전사.txt"
    with pdfplumber.open(ROOT/f"{source['round']}.pdf") as pdf:
        assert len(pdf.pages) == 4
        # 제136회는 문항이 그림으로만 들어 있어 쪽 그림을 보고 받아 적은 파일을 쓴다
        texts = (manual.read_text().split('\f') if manual.exists()
                 else [page.extract_text(x_tolerance=1) for page in pdf.pages])
        for period, text in enumerate(texts, 1):
            pages.append(text)
            # 제138회 3교시 1번은 원문에 번호 뒤 점이 빠져 있다(‘1 「사업장…’)
            matches = list(re.finditer(r'^\s*(\d{1,2})\s*(?:\.\s*|\s+(?=[「『(가-힣A-Za-z]))', text, re.M))
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
