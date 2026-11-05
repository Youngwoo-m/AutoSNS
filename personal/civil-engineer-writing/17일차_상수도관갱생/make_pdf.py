"""17일차 노후 상수도관 갱생공법 — Q-net 답안지 위 따라쓰기 PDF(2쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 노후 수도관 갱생공법, 세척·갱생·교체 가르는 기준 | 하루 한 문제 17일차'
PDF_NAME = '17일차_상수도관갱생_답안예시_따라쓰기.pdf'

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


def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H_PG))
    p1 = {
        0: ('노후 상수도관 갱생공법', 13),
        1: ('1. 정의', 14),
        2: ('· 노후로 수질·통수능·누수 기능이 저하된 관을', 12),
        3: ('  굴착 교체 없이 내면에 도막 또는 라이너를 형성하여', 12),
        4: ('  부식 방지·구조 기능을 회복하는 공법', 12),
        5: ('· 세척(침전물 배출)과 교체(신관 대체)의 중간 단계', 12),
        6: ('2. 갱생공법의 종류', 14),
        12: ('· 비구조적: 보호 도막만 형성, 관체 보강 효과 없음', 12),
        13: ('· 구조적: 라이너가 내압·외압 분담 또는 단독 지지', 12),
        14: ('3. 개념도(관 단면)', 14),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 6 * 32.35 - 12 - i * 32.35 for i in range(6)]
    rule_table(c, [202, 272, 432, 605], ys, [
        ('구분', '공법', '특징'),
        ('비구조적', '에폭시·모르타르 라이닝', '내면 부식·적수 방지'),
        ('구조적', '반전삽입(CIPP)', '수지 라이너 열 경화'),
        ('구조적', '관 삽입 밀착', '라이닝관 축경 삽입·복원'),
        ('구조적', '삽입관(slip lining)', '견인 삽입 후 그라우팅'),
    ])
    # 단면도 3개: 노후관 / 비구조적 도막 / 구조적 라이너
    c.setStrokeColorRGB(GRAY, GRAY, GRAY)
    cy = 764 - 16.9 * 32.35
    for k, (cx, lab, t) in enumerate([(250, '노후관(스케일)', 0), (400, '비구조적(얇은 도막)', 3), (550, '구조적(라이너)', 9)]):
        c.setLineWidth(5); c.circle(cx, cy, 38, stroke=1, fill=0)
        if k == 0:
            c.setLineWidth(1)
            for a in range(0, 360, 30):
                import math
                c.line(cx + 33 * math.cos(math.radians(a)), cy + 33 * math.sin(math.radians(a)), cx + 22 * math.cos(math.radians(a + 12)), cy + 22 * math.sin(math.radians(a + 12)))
        else:
            c.setLineWidth(t); c.circle(cx, cy, 35.5 - t / 2, stroke=1, fill=0)
        wd = pdfmetrics.stringWidth(lab, 'KR', 10.5); text(c, cx - wd / 2, cy - 58, lab, 10.5)
    text(c, 132, 731, '6', 14)
    c.showPage()
    p2 = {
        0: ('4. 공법 선정 기준', 14),
        1: ('(1) 관 상태(정밀조사 직접평가 등급)', 12.5),
        2: ('· Ⅱ 세척 / Ⅲ 비구조적 갱생 / Ⅳ 갱생·교체 / Ⅴ 교체', 12),
        3: ('· 주철관 안전계수: 2.5 초과 Ⅲ, 1.0 초과~2.5 이하 Ⅳ, 1.0 이하 Ⅴ', 11.5),
        4: ('(2) 관경·통수능: 라이너 두께만큼 단면 감소 검토', 12),
        5: ('(3) 분기관·굴곡부: 급수 분기 재연결, 굴곡 통과성', 12),
        6: ('(4) 시공 조건: 단수 허용 시간, 도로 굴착 제약', 12),
        7: ('(5) 위생 안전: 위생 기준 적합 재료, 소독 후 통수', 12),
        8: ('(6) 경제성: 교체 대비 공사비·잔존 수명 비교', 12),
        9: ('5. 시공 순서', 14),
        10: ('· 단수·배수 → 세관 → 관내 조사·건조 → 라이닝', 12),
        11: ('  → 양생 → 소독·플러싱 → 수질 확인 후 통수', 12),
        12: ('6. 유의사항', 14),
        13: ('· 세관 불량 시 라이닝 부착 불량·조기 박리', 12),
        14: ('· 안전계수 낮은 관에 비구조적 라이닝 적용 금지', 12),
        15: ('7. 결론', 14),
        16: ('· 정밀조사 등급으로 세척·갱생·교체를 가르고', 12),
        17: ('  관체 강도에 따라 비구조적·구조적 공법을 선정함', 12),
        19: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '6', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(2):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H_PG)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2026 제140회 1교시 6번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
