"""16일차 댐 기초처리 그라우팅 공법의 종류·특징·선정 시 고려사항 — Q-net 답안지 위 따라쓰기 PDF(3쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 댐 기초 그라우팅의 종류와 공법 선정 기준 | 하루 한 문제 16일차'
PDF_NAME = '16일차_댐기초그라우팅_답안예시_따라쓰기.pdf'

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
        0: ('댐 기초처리 그라우팅 공법의 종류·특징·선정 고려사항', 12),
        1: ('1. 개요', 14),
        2: ('· 기초 암반의 절리·단층 등 불연속면에 주입재를', 12),
        3: ('  압입하여 차수성과 강도를 개선하는 공법', 12),
        4: ('· 목적: 누수·양압력 감소, 파이핑 방지(차수)', 12),
        5: ('        지지력·변형 특성 개선(보강)', 12),
        6: ('· 댐 형식·지질에 맞게 선정, 루전값으로 효과 확인', 12),
        7: ('2. 그라우팅 공법의 종류 및 특징', 14),
        15: ('· 주입재 선정', 12.5),
        16: ('  - 시멘트: 일반 균열 / 미립자 시멘트: 미세 균열', 12),
        17: ('  - 벤토나이트 혼합: 넓은 공극, 유실 억제', 12),
        18: ('  - 약액: 세립 지반·용수부, 환경 영향 검토', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 7.55 * 32.35 - i * 33 for i in range(7)]
    rule_table(c, [202, 272, 412, 605], ys, [
        ('종류', '목적', '위치·특징'),
        ('커튼', '차수, 양압력 감소', '상류 측 1~2열, 깊게'),
        ('압밀', '지지력·변형 개선', '기초 전면, 얕고 조밀'),
        ('블랭킷', '코어 접촉부 차수', '필댐 코어 하부, 얕게'),
        ('콘택트', '접촉면 공극 충전', '콘크리트·암반 경계'),
        ('림', '우회 누수 차단', '양안부 지반·산비탈'),
    ])
    text(c, 132, 731, '5', 14)
    c.showPage()
    p2 = {
        0: ('3. 선정 시 고려사항', 14),
        1: ('(1) 댐 형식', 12.5),
        2: ('· 콘크리트댐: 커튼 + 압밀(양압력·지지력)', 12),
        3: ('· 필댐: 블랭킷 + 커튼(코어 접촉부 차수)', 12),
        4: ('· CFRD: 플린스 하부 커튼·압밀 집중', 12),
        5: ('(2) 기초 지질', 12.5),
        6: ('· 절리 간격·개구 폭, 단층·파쇄대 분포', 12),
        7: ('· 시추 루전값 분포로 범위·심도 결정', 12),
        8: ('(3) 수두: 저수위가 높을수록 커튼 심도·열 수 증가', 12),
        9: ('(4) 주입재: 균열 폭에 맞는 입도, 유속 구간 급결재', 12),
        10: ('(5) 주입압', 12.5),
        11: ('· 과압 시 암반 들뜸·할렬 → 새 누수 경로 형성', 12),
        12: ('· 심도별 단계 설정, 지표 변위 계측', 12),
        13: ('(6) 시공 순서', 12.5),
        14: ('· 압밀 그라우팅 후 커튼 그라우팅', 12),
        15: ('· 1차 → 2차 → 3차공 분할 내삽, 주입량 감소 확인', 12),
        16: ('(7) 시험 그라우팅: 배합·압력·공 간격 결정', 12),
        17: ('(8) 환경: 주입재의 하천·지하수 유출 방지', 12),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '5', 14)
    c.showPage()
    p3 = {
        0: ('4. 효과 확인(루전 시험)', 14),
        1: ('· Lu = (Q / L) × (P0 / P),  P0 = 1 MPa(10 bar)', 12),
        2: ('· 1 Lu ≈ 1×10^-7 m/s (참고 환산, 한계 있음)', 12),
        3: ('· 가상 예시: 시험 구간 L 5 m, 시험 압력 P 0.5 MPa', 12),
        8: ('· 감소율 (4.8 - 0.8) / 4.8 ≈ 83 % → 개량 효과 확인', 12),
        9: ('· 목표치 미달 구간은 추가공 시공 후 재확인', 12),
        10: ('5. 시공 시 유의사항', 14),
        11: ('· 천공 후 공내 세척, 수압 시험 시행', 12),
        12: ('· 주입 중 유량·압력 기록, 인접공 연통 확인', 12),
        13: ('· 지표 누출 시 압력 저감 및 주입 중지', 12),
        14: ('· 담수 후 양압력·누수량 계측으로 성능 확인', 12),
        15: ('6. 결론', 14),
        16: ('· 차수는 커튼, 보강은 압밀로 목적을 구분하고', 12),
        17: ('  지질·수두에 맞춰 배치한 뒤 루전값으로 확인함', 12),
        19: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    ys = [764 - 3.55 * 32.35 - i * 33 for i in range(4)]
    rule_table(c, [202, 272, 382, 472, 605], ys, [
        ('구분', '주입량 Q', '루전값', 'k 환산(m/s)'),
        ('전', '12 L/min', '4.8 Lu', '4.8×10^-7'),
        ('후', '2 L/min', '0.8 Lu', '8×10^-8'),
    ])
    text(c, 132, 731, '5', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(3):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H_PG)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2026 제138회 2교시 5번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
