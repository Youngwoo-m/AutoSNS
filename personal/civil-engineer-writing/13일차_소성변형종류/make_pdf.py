"""13일차 아스팔트 콘크리트 포장 소성변형의 종류 — Q-net 답안지 위 따라쓰기 PDF(2쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 아스팔트 포장 소성변형의 종류와 구분법 | 하루 한 문제 13일차'
PDF_NAME = '13일차_소성변형종류_답안예시_따라쓰기.pdf'

pdfmetrics.registerFont(TTFont('KR', '/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
tp = PdfReader(TEMPLATE).pages[4]
W, H_PG = float(tp.mediabox.width), float(tp.mediabox.height)
GRAY = 184 / 255


def text(c, x, y, s, size=12.5, gray=True):
    c.setFillColorRGB(*((GRAY,) * 3 if gray else (.12,) * 3)); c.setFont('KR', size); c.drawString(x, y, s)


def line(c, row, s, size=12.5):
    assert pdfmetrics.stringWidth(s, 'KR', size) < 405, s
    text(c, 202, 764 - row * 32.35, s, size)


def rule_table(c, xs, ys, cells, size=10.5):
    """표 내용은 칸 가운데 정렬."""
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(.9)
    for x in xs: c.line(x, ys[-1], x, ys[0])
    for y in ys: c.line(xs[0], y, xs[-1], y)
    for i, row in enumerate(cells):
        for j, s in enumerate(row):
            wd = pdfmetrics.stringWidth(s, 'KR', size)
            assert wd < xs[j + 1] - xs[j] - 6, s
            text(c, (xs[j] + xs[j + 1]) / 2 - wd / 2, ys[i] - 19, s, size)


def profiles(c, top):
    """종류별 횡단 모식도 4개(축척 없음). top 은 노면 높이."""
    import math
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(1.2)
    specs = [('①유동', lambda u: 9 * math.exp(-(u / 9) ** 2) - 4 * math.exp(-((u - 17) / 6) ** 2) - 4 * math.exp(-((u + 17) / 6) ** 2)),
             ('②구조적', lambda u: 9 * math.exp(-(u / 24) ** 2)),
             ('③압밀', lambda u: 7 * math.exp(-(u / 11) ** 2)),
             ('④마모', lambda u: 3.5 * math.exp(-(u / 14) ** 2))]
    for k, (name, fn) in enumerate(specs):
        x0 = 206 + k * 100; cx = x0 + 45
        c.setDash(2, 2); c.line(x0, top, x0 + 90, top); c.setDash()
        pts = [(x0 + i, top - 1.7 * fn(x0 + i - cx)) for i in range(0, 91)]
        p = c.beginPath(); p.moveTo(*pts[0])
        for q in pts[1:]: p.lineTo(*q)
        c.drawPath(p, stroke=1, fill=0)
        layer = 26                                                 # 표층 아래 경계
        base = [(x0 + i, top - layer - (1.7 * fn(x0 + i - cx) if k == 1 else 0)) for i in range(0, 91)]
        p = c.beginPath(); p.moveTo(*base[0])
        for q in base[1:]: p.lineTo(*q)
        c.drawPath(p, stroke=1, fill=0)
        text(c, x0 + 22, 764 - 15 * 32.35, name, 10.5)
    text(c, 206, 764 - 16 * 32.35, '점선 = 원래 노면, 아래 선 = 표층 하면(②는 하부층도 처짐)', 9.5)


def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H_PG))
    p1 = {
        0: ('아스팔트 콘크리트 포장 소성변형의 종류', 12.5),
        1: ('1. 정의', 14),
        2: ('· 반복 차량하중과 고온으로 바퀴 통과 위치를 따라', 12),
        3: ('  노면이 오목하게 남는 영구변형(Rutting)', 12.5),
        4: ('· 변형이 생긴 층과 횡단 모양으로 종류를 구분', 12),
        5: ('· 종류에 따라 보수 범위(표층·하부층)가 달라짐', 12),
        6: ('2. 종류별 특징', 14),
        12: ('■ 그림. 종류별 횡단 형상(모식도, 깊이 과장)', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 6.55 * 32.35 - i * 29 for i in range(6)]
    rule_table(c, [202, 252, 326, 456, 605], ys, [
        ('종류', '발생 층', '횡단 모양', '주원인'),
        ('유동', '표층·중간층', '바퀴자국 양옆 융기', '고온·저속·배합 불량'),
        ('구조적', '기층·노상', '넓게 처짐, 융기 없음', '두께·지지력 부족'),
        ('압밀', '다짐 부족 층', '좁게 처짐, 융기 없음', '시공 다짐 부족'),
        ('마모', '표면', '얕고 표면 거칠음', '체인·스파이크 타이어'),
    ])
    profiles(c, 764 - 13.45 * 32.35)
    line(c, 17, '· 마모는 변형이 아닌 표면 마모이나 함께 분류함', 12)
    line(c, 18, '· 여러 종류가 겹치므로 횡단 측정·코어로 판별', 12)
    text(c, 132, 731, '8', 14)
    c.showPage()
    p2 = {
        0: ('3. 판별 방법', 14),
        1: ('· 횡단 프로파일: 융기 있음 → 유동', 12),
        2: ('  융기 없음 → 하부층(구조적) 또는 압밀 가능성', 12),
        3: ('· 코어 채취·트렌치: 층별 두께 변화로 변형 층 확인', 12),
        4: ('· 발생 시기: 공용 초기면 압밀, 여름 고온기면 유동 가능성', 12),
        5: ('· 위치: 교차로·정류장·오르막 저속 구간 → 유동', 12),
        6: ('4. 종류별 대책', 14),
        7: ('(1) 유동: 개질아스팔트·SMA, 쇄석 골재·입도 관리', 12),
        8: ('    적정 아스팔트량·공극률, 동적안정도 확인', 12),
        9: ('(2) 구조적: 포장 두께·노상 지지력 확보', 12),
        10: ('    배수 개선, 과적 차량 관리', 12),
        11: ('(3) 압밀: 포설 온도·시공 다짐도 관리(코어 밀도)', 12),
        12: ('(4) 마모: 내마모 골재, 체인 사용 구간 점검', 12),
        13: ('5. 보수 시 유의사항', 14),
        14: ('· 유동: 변형 층 절삭 후 내유동 혼합물로 재포장', 12),
        15: ('· 구조적: 표층 덧씌우기만으로는 재발 → 하부층 보강', 12),
        16: ('· 보수 전 종류 판별이 공법 선정의 출발점임', 12),
        18: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '8', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(2):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H_PG)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2025 제137회 1교시 8번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
