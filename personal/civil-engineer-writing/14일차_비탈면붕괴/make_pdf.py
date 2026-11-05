"""14일차 비탈면의 붕괴원인과 방지대책 — Q-net 답안지 위 따라쓰기 PDF(3쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 비탈면·산사태 붕괴 원인과 방지대책 | 하루 한 문제 14일차'
PDF_NAME = '14일차_비탈면붕괴_답안예시_따라쓰기.pdf'

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


def bars(c, top):
    """가상 예시 안전율 막대 3개(m=0, 0.5, 1)와 기준선."""
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setFillColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(1)
    base, k = top - 130, 75                         # Fs 1.0 = 75 pt
    c.line(214, base, 520, base)
    for v, s in [(1.5, '1.5 건기'), (1.2, '1.2 우기'), (1.0, '1.0')]:
        c.setDash(3, 2); c.line(214, base + v * k, 470, base + v * k); c.setDash()
        text(c, 476, base + v * k - 4, s, 10)
    for i, (m, fs) in enumerate([('m=0', 1.53), ('m=0.5', 1.20), ('m=1', 0.89)]):
        x = 240 + i * 75
        c.setFillColorRGB(GRAY, GRAY, GRAY); c.rect(x, base, 40, fs * k, stroke=0, fill=1)
        c.setFillColorRGB(1, 1, 1); c.rect(x, base + fs * k + 2, 26, 12, stroke=0, fill=1)
        text(c, x + 2, base + fs * k + 4, f'{fs:.2f}', 10.5)
        text(c, x + 2, base - 13, m, 10)


def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H_PG))
    p1 = {
        0: ('비탈면의 붕괴원인과 방지대책', 12.5),
        1: ('1. 개요', 14),
        2: ('· 비탈면 붕괴: 활동력이 전단저항력을 넘어 토체·', 12),
        3: ('  암괴가 비탈 아래로 이동하는 현상', 12),
        4: ('· 안전율 Fs = 전단저항력 / 활동력', 12),
        5: ('· 기준안전율(깎기): 건기 1.5, 우기 1.2~1.3', 12),
        6: ('2. 붕괴 형태', 14),
        14: ('· 흙은 원호, 암반은 불연속면 방향이 형태를 지배', 12),
        15: ('3. 붕괴 원인', 14),
        16: ('(1) 내적 원인(전단강도 감소)', 12.5),
        17: ('· 풍화·이완, 불연속면 발달, 다짐 부족·점토 연화', 12),
        18: ('· 흡수·팽창, 간극수압 증가로 유효응력 감소', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 6.55 * 32.35 - i * 33 for i in range(7)]
    rule_table(c, [202, 282, 372, 605], ys, [
        ('형태', '대상', '특징'),
        ('원호 활동', '흙·풍화토', '휘어진 활동면, 한 덩어리 이동'),
        ('평면 파괴', '암반', '비탈면 쪽으로 기운 절리 1개'),
        ('쐐기 파괴', '암반', '교차하는 절리 2개 사이 쐐기'),
        ('전도 파괴', '암반', '안쪽으로 급경사인 기둥 암괴'),
        ('표층 유실', '얕은 토층', '호우 시 표면 흙 쓸림'),
    ])
    text(c, 132, 731, '5', 14)
    c.showPage()
    p2 = {
        0: ('(2) 외적 원인(전단응력 증가)', 12.5),
        1: ('· 강우 침투·지하수위 상승, 배수시설 막힘', 12),
        2: ('· 비탈 끝 굴착·침식, 비탈 어깨 성토·상재하중', 12),
        3: ('· 지진·발파 진동, 동결융해', 12),
        4: ('4. 강우 시 안전율 저하(무한사면, 가상 예시)', 14),
        5: ("· Fs = [c' + (γz·cos²β - u)tanφ'] / (γz·sinβ·cosβ)", 11.5),
        6: ("· z=2 m, β=30°, c'=5 kPa, φ'=35°, u=m·γw·z·cos²β", 11.5),
        12: ('· 지하수위 상승만으로 Fs 1.53 → 0.89', 12),
        13: ('· 배수 확보가 안정 대책의 첫 순위임', 12),
        14: ('5. 방지대책', 14),
        15: ('(1) 억제공(활동력 감소·강도 저하 방지)', 12.5),
        16: ('· 배수: 산마루측구·소단 배수구·수평배수공', 12),
        17: ('· 표면보호: 식생·숏크리트·블록, 경사 완화', 12),
        18: ('· 두부 제거·압성토로 하중 균형', 12),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    bars(c, 764 - 6.6 * 32.35)
    text(c, 132, 731, '5', 14)
    c.showPage()
    p3 = {
        0: ('(2) 억지공(저항력 증가)', 12.5),
        1: ('· 앵커·네일·록볼트, 억지말뚝', 12),
        2: ('· 옹벽·돌망태옹벽, 낙석방지망·울타리', 12),
        3: ('(3) 형태별 우선 대책', 12.5),
        10: ('6. 시공·유지관리 시 유의사항', 14),
        11: ('· 깎기 중 노출 암질·절리 조사 → 설계 보완', 12),
        12: ('· 높이 10 m 이상 깎기 비탈면은 소단 설치', 12),
        13: ('· 우기 전 배수시설 점검·준설, 지표변위·수위 계측', 12),
        14: ('· 위험도·피해도를 함께 보고 관리 우선순위 결정', 12),
        15: ('· 붕괴 형태 판별 후 원인에 맞는 공법을 조합', 12),
        18: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    ys = [764 - 3.55 * 32.35 - i * 33 for i in range(6)]
    rule_table(c, [202, 302, 605], ys, [
        ('형태', '우선 대책'),
        ('원호 활동', '배수, 경사 완화·압성토, 억지말뚝'),
        ('평면·쐐기', '앵커·록볼트, 절리면 배수'),
        ('전도', '록볼트·앵커, 낙석방지시설'),
        ('표층 유실', '식생·표면보호, 산마루측구'),
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
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2024 제133회 2교시 5번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
