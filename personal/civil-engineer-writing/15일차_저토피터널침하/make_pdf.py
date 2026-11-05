"""15일차 미고결 저토피 터널 지표침하 원인 및 저감대책 — Q-net 답안지 위 따라쓰기 PDF(3쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 싱크홀·지표침하, 저토피 터널 원인과 저감대책 | 하루 한 문제 15일차'
PDF_NAME = '15일차_저토피터널침하_답안예시_따라쓰기.pdf'

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
        0: ('미고결 저토피 터널 지표침하 원인 및 저감대책', 12.5),
        1: ('1. 개요', 14),
        2: ('· 미고결 지반: 고결되지 않은 토사·풍화토로', 12),
        3: ('  점착력이 작고 자립시간이 짧으며 지하수에 민감함', 12),
        4: ('· 저토피 터널: 토피가 얕아 아칭이 충분히 형성되지', 12),
        5: ('  않으므로 굴착 손실이 지표침하로 직접 전달됨', 12),
        6: ('· 도심지는 함몰·매설관·인접 건물 손상으로 이어짐', 12),
        7: ('2. 지표침하 발생 단계와 형태', 14),
        14: ('· 횡단 침하곡선: 정규분포형(Peck 1969)', 12),
        15: ('  S(x) = Smax·exp(-x²/2i²),  Vs = √2π·i·Smax', 11.5),
        16: ('  Vs = VL·πD²/4,  i = K·z0 (O\'Reilly & New 1982)', 11.5),
        17: ('· z0: 터널 중심 깊이, VL: 체적손실', 12),
        18: ('· K: 점토 약 0.5, 지반·계측 자료로 결정', 12),
        19: ('· 토피가 얕을수록 폭은 좁고 최대 침하는 커짐', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 7.55 * 32.35 - i * 33 for i in range(6)]
    rule_table(c, [202, 282, 372, 605], ys, [
        ('단계', '시기', '주된 원인'),
        ('선행 침하', '막장 도달 전', '전방 이완, 지하수위 저하'),
        ('막장 침하', '막장 통과 시', '막장 자립 부족, 여굴'),
        ('후행 침하', '지보 설치 후', '지보 변형, 폐합 지연'),
        ('장기 침하', '굴착 완료 후', '배수에 따른 압밀'),
    ])
    text(c, 132, 731, '5', 14)
    c.showPage()
    p2 = {
        0: ('3. 지표침하 원인', 14),
        1: ('(1) 지반 요인', 12.5),
        2: ('· 아칭 효과 부족, 이완영역의 지표 도달', 12),
        3: ('· 낮은 점착력·짧은 자립시간', 12),
        4: ('(2) 시공 요인', 12.5),
        5: ('· 막장 붕락·여굴, 1회 굴진장 과다', 12),
        6: ('· 지보 설치·인버트 폐합 지연, 배면 공극', 12),
        7: ('· 숏크리트 두께·품질 부족', 12),
        8: ('(3) 지하수 요인', 12.5),
        9: ('· 용수와 함께 세립분 유출 → 지중 공동 형성', 12),
        10: ('· 지하수위 저하에 따른 압밀침하', 12),
        11: ('(4) 외부 요인: 상재·교통하중, 노후관 누수', 12.5),
        12: ('4. 토피별 침하 비교(가상 예시)', 14),
        13: ('· D 10 m, VL 1.0 %, K 0.5 → Vs = 0.785 m³/m', 12),
        18: ('· 같은 체적손실에서도 토피가 얕으면 침하 증가', 12),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    ys = [764 - 13.55 * 32.35 - i * 33 for i in range(4)]
    rule_table(c, [202, 302, 402, 502, 605], ys, [
        ('z0', 'i', 'Smax', 'x = i 침하'),
        ('15 m', '7.5 m', '41.8 mm', '25.3 mm'),
        ('10 m', '5.0 m', '62.7 mm', '38.0 mm'),
    ])
    text(c, 132, 731, '5', 14)
    c.showPage()
    p3 = {
        0: ('5. 저감대책', 14),
        8: ('· 쉴드 TBM: 막장압 관리, 뒤채움 즉시 주입', 12),
        9: ('· 도심지: 착공 전 지하안전평가·지장물 조사', 12),
        10: ('· 계측 관리기준을 단계별로 정하고 초과 시 대응', 12),
        11: ('6. 이상 징후 시 조치', 14),
        12: ('· 관리기준 초과 시 굴진 중지, 막장면 폐합·되메움', 12),
        13: ('· 지중 공동 그라우팅 충전, 함몰부 통제 후 복구', 12),
        14: ('· 매설관 점검, 계측 빈도 상향 후 굴진 재개', 12),
        15: ('7. 결론', 14),
        16: ('· 침하는 막장 전방에서 시작하므로 선행 보강,', 12),
        17: ('  조기 폐합, 계측관리를 함께 적용해야 함', 12),
        18: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    ys = [764 - 0.55 * 32.35 - i * 33 for i in range(7)]
    rule_table(c, [202, 272, 470, 605], ys, [
        ('구분', '대책', '대응 원인'),
        ('천단 보강', '강관다단 그라우팅, 훠폴링', '아칭 부족, 이완'),
        ('막장 보강', '막장 숏크리트·볼트, 링컷', '막장 붕락, 여굴'),
        ('굴착 방법', '분할굴착·굴진장 축소·조기 폐합', '지보·폐합 지연'),
        ('지하수', '차수 그라우팅, 지반개량', '세립분 유출, 압밀'),
        ('계측', '지표·천단침하, 내공변위', '이상 징후 파악'),
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
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2022 제126회 4교시 5번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
