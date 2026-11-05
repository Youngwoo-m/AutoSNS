"""18일차 방파제 구조형식 분류와 설계·시공 유의사항 — Q-net 답안지 위 따라쓰기 PDF(3쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 방파제 구조형식 분류와 설계·시공 유의사항 | 하루 한 문제 18일차'
PDF_NAME = '18일차_방파제구조형식_답안예시_따라쓰기.pdf'

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
        0: ('방파제의 구조형식별 분류와 설계·시공 시 유의사항', 12),
        1: ('1. 개요', 14),
        2: ('· 외해 파랑을 막아 항내 정온을 확보하고', 12),
        3: ('  항만 시설·선박을 보호하는 외곽시설', 12),
        4: ('· 심해설계파 개정(해수부 고시 제2019-146호):', 12),
        5: ('  해수면 상승·태풍 강도 반영 → 안정성 점검 필요', 12),
        6: ('2. 구조형식에 따른 분류', 14),
        13: ('· 선정: 수심·파랑·지반·재료·항내 이용 계획 종합', 12),
        14: ('· 깊은 수심·고파랑 → 케이슨 직립식·혼성식', 12),
        15: ('· 얕은 수심 → 경사식', 12),
        16: ('· 특수형: 부유식 등은 별도 검토', 12),
        17: ('(표준 단면도: 경사식·직립식·혼성식 개략도 병기)', 11),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 6.55 * 32.35 - i * 33 for i in range(6)]
    rule_table(c, [202, 292, 437, 605], ys, [
        ('구분', '장점', '단점'),
        ('경사식', '반사파 적음, 연약지반 적응', '깊은 수심 재료량 과다'),
        ('직립식', '재료 절감, 내측 계류 가능', '반사파·세굴, 견고 지반'),
        ('혼성식', '깊은 수심에서 경제적', '공종 다양, 파압 증가'),
        ('소파블록 피복제', '반사파·월파·파압 감소', '블록 이탈 시 직립부 위험'),
    ])
    text(c, 132, 731, '3', 14)
    c.showPage()
    p2 = {
        0: ('3. 설계 시 유의사항', 14),
        1: ('(1) 설계조건: 개정 심해설계파·설계조위·수심·지반', 12),
        2: ('(2) 마루높이: 허용 월파량, 항내 정온도, 침하 여유', 12),
        3: ('(3) 피복재 중량(Hudson 식)', 12.5),
        4: ('· W = ρr·H³ / {KD·(Sr - 1)³·cotα},  Sr = ρr / ρw', 12),
        5: ('· KD: 피복재 종류·층수·쇄파 여부·제두부 구분', 12),
        6: ('· 가상 예: ρr 2.30, ρw 1.03, cotα 1.5, KD 8.0', 12),
        11: ('· 파고 10 % 증가 → 중량 약 33 % 증가(1.1³ ≈ 1.33)', 12),
        12: ('(4) 소파블록 피복 경사제 소파층(KDS 64 45 20:2017)', 12.5),
        13: ('· 어깨폭: 소파블록 2개 이상', 12),
        14: ('· 어깨 마루높이 = 상치콘크리트 마루높이', 12),
        15: ('· 마루 부족 시 직립부에 충격쇄파압 작용', 12),
        16: ('(5) 직립부 안정: 활동·전도·기초 지지력 함께 검토', 12),
        17: ('(6) 세굴·침하: 근고블록·피복석으로 선단 보호,', 12),
        18: ('    연약지반 치환·개량 및 침하 예측', 12),
        19: ('(7) 항내측: 월파에 의한 항내측 피복석 안정 검토', 12),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    ys = [764 - 6.55 * 32.35 - i * 33 for i in range(4)]
    rule_table(c, [202, 297, 507, 605], ys, [
        ('설계파고 H', '계산', '소요중량 W'),
        ('4.0 m', '2.30×4.0³÷(8.0×1.875×1.5)', '약 6.5 t'),
        ('4.4 m(+10 %)', '6.54 × 1.1³', '약 8.7 t'),
    ])
    text(c, 132, 731, '3', 14)
    c.showPage()
    p3 = {
        0: ('4. 시공 시 유의사항', 14),
        1: ('(1) 기초: 준설·치환 후 사석 투하', 12),
        2: ('· 수중 고르기 마무리 확인 후 본체 시공', 12),
        3: ('(2) 케이슨: 제작 → 진수 → 예인 → 거치', 12),
        4: ('· 거치 직후 속채움·덮개콘크리트로 중량 확보', 12),
        5: ('(3) 피복: 소파블록 충분 양생 후 거치', 12),
        6: ('· 규정 층수·배치로 블록 맞물림 확보', 12),
        7: ('(4) 미완성 단면: 시공 단계별 안정 검토', 12),
        8: ('· 태풍기 이전 피복 완료 공정 계획', 12),
        9: ('(5) 해상 작업: 파고·풍속 작업 한계 설정,', 12),
        10: ('    기상 예보 기반 작업일 결정', 12),
        11: ('(6) 환경: 준설·투하 시 오탁방지막, 부유사 관리', 12),
        12: ('5. 결론', 14),
        13: ('· 구조형식은 수심·파랑·지반·항내 이용 계획을', 12),
        14: ('  종합하여 선정함', 12),
        15: ('· 설계파 변화 가능성에 대비하여 피복재·소파층', 12),
        16: ('  단면 여유를 확보하고, 태풍 후 소파층 침하·블록', 12),
        17: ('  이탈을 점검·보수하는 유지관리 체계가 필요함', 12),
        19: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    text(c, 132, 731, '3', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(3):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H_PG)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2022 제126회 2교시 3번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
