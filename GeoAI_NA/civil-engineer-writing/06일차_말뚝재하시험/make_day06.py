"""6일차 말뚝기초 재하시험 — 개념도·따라쓰기 PDF·티스토리/Blogger 본문을 만든다."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
import json, math
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 말뚝기초 재하시험의 종류와 결과 해석 | 하루 한 문제 6일차'
PDF_NAME = '06일차_말뚝재하시험_답안예시_따라쓰기.pdf'
FIG_NAME = '말뚝재하시험_하중침하_개념도.jpg'
CDN = 'https://geoai-na.netlify.app/civil-questions/materials/day06/'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'

# ── 계산 예(학습용 가정) ─────────────────────────────────────────────
D, T, L, E = 508.0, 12.0, 20000.0, 200000.0           # mm, mm, mm, MPa
A = math.pi / 4 * (D**2 - (D - 2 * T)**2)              # mm²
AE = E * A                                             # N
OFFSET = 4 + D / 120                                   # mm
MEAS = [(0, 0), (500, 3.0), (1000, 6.2), (1500, 9.6), (2000, 13.2), (2500, 17.0), (3000, 26.0), (3500, 40.0)]
def elastic(q): return q * 1e3 * L / AE                # kN → mm
def limit(q): return elastic(q) + OFFSET
d1, d2 = MEAS[5][1] - limit(2500), MEAS[6][1] - limit(3000)
QF = 2500 + 500 * (-d1) / (d2 - d1)
CALC = {'A_mm2': round(A), 'AE_kN': round(AE / 1e3), 'offset_mm': round(OFFSET, 2),
        'elastic_3000_mm': round(elastic(3000), 2), 'limit_2500_mm': round(limit(2500), 2),
        'limit_3000_mm': round(limit(3000), 2), 'Q_davisson_kN': round(QF)}

# ── 개념도 (하중-침하 곡선과 Davisson 한계선) ─────────────────────────
def figure():
    im = Image.new('RGB', (1600, 1000), 'white'); dr = ImageDraw.Draw(im)
    f = lambda z: ImageFont.truetype(PRET, z)
    INK, TEAL, RED, GRAYC = '#263746', '#176977', '#B6462F', '#7A8790'
    x0, y0, x1, y1 = 190, 150, 1480, 860       # plot box: x=load, y=settlement (down)
    qmax, smax = 4000, 45
    X = lambda q: x0 + (x1 - x0) * q / qmax
    Y = lambda s: y0 + (y1 - y0) * s / smax
    dr.text((60, 40), '말뚝 압축 정재하시험의 하중-침하 곡선과 Davisson 판정', font=f(40), fill=INK)
    dr.line([(x0, y0), (x1, y0)], fill=INK, width=4); dr.line([(x0, y0), (x0, y1)], fill=INK, width=4)
    for q in range(0, 4001, 1000):
        dr.line([(X(q), y0 - 8), (X(q), y0)], fill=INK, width=3)
        dr.text((X(q) - 30, y0 - 50), f'{q:,}', font=f(26), fill=INK)
    for s in range(0, 46, 10):
        dr.line([(x0 - 8, Y(s)), (x0, Y(s))], fill=INK, width=3)
        dr.text((x0 - 60, Y(s) - 14), f'{s}', font=f(26), fill=INK)
    dr.text((x1 - 230, y0 - 95), '하중 Q (kN) →', font=f(28), fill=INK)
    dr.text((40, y1 - 20), '침하 s', font=f(28), fill=INK); dr.text((40, y1 + 16), '(mm) ↓', font=f(28), fill=INK)
    # elastic line and offset limit line
    dr.line([(X(0), Y(0)), (X(4000), Y(elastic(4000)))], fill=GRAYC, width=3)
    dr.text((X(3700) - 40, Y(elastic(3700)) - 52), '탄성 압축선 QL/AE', font=f(26), fill=GRAYC)
    dr.line([(X(0), Y(OFFSET)), (X(4000), Y(limit(4000)))], fill=RED, width=4)
    dr.text((X(250), Y(limit(1700)) + 20), 'Davisson 한계선 = QL/AE + (4 + D/120)', font=f(26), fill=RED)
    pts = [(X(q), Y(s)) for q, s in MEAS]
    dr.line(pts, fill=TEAL, width=6)
    for p in pts: dr.ellipse([p[0] - 8, p[1] - 8, p[0] + 8, p[1] + 8], fill=TEAL)
    dr.text((X(3500) - 290, Y(40) - 14), '측정 곡선(가상)', font=f(28), fill=TEAL)
    fx, fy = X(QF), Y(limit(QF))
    dr.ellipse([fx - 14, fy - 14, fx + 14, fy + 14], outline=RED, width=5)
    for yy in range(int(y0), int(fy) - 14, 18): dr.line([(fx, yy), (fx, yy + 9)], fill=RED, width=2)
    dr.text((fx - 330, fy + 40), f'교점 약 {QF:,.0f} kN', font=f(28), fill=RED)
    dr.text((fx - 330, fy + 76), '= Davisson 극한하중', font=f(26), fill=RED)
    dr.text((60, 930), f'가상 강관말뚝 D=508 mm·t=12 mm·L=20 m·E=200 GPa 가정 / 수치는 학습용 예이며 실측 자료가 아니다', font=f(25), fill=GRAYC)
    im.save(OUT / FIG_NAME, quality=92)

# ── 따라쓰기 PDF ─────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('KR', '/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
tp = PdfReader(TEMPLATE).pages[4]
W, H = float(tp.mediabox.width), float(tp.mediabox.height)
GRAY = 184 / 255

def text(c, x, y, s, size=12.5, gray=True):
    c.setFillColorRGB(*((GRAY,) * 3 if gray else (.12,) * 3)); c.setFont('KR', size); c.drawString(x, y, s)

def line(c, row, s, size=12.5):
    assert pdfmetrics.stringWidth(s, 'KR', size) < 405, s
    text(c, 202, 764 - row * 32.35, s, size)

def rule_table(c, xs, ys, cells, sizes=(11, 10.5)):
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(.9)
    for x in xs: c.line(x, ys[-1], x, ys[0])
    for y in ys: c.line(xs[0], y, xs[-1], y)
    for i, row in enumerate(cells):
        for j, s in enumerate(row):
            z = sizes[0] if j == 0 else sizes[1]
            assert pdfmetrics.stringWidth(s, 'KR', z) < xs[j + 1] - xs[j] - 8, s
            text(c, xs[j] + 5, ys[i] - 21, s, z)

def mini_curve(c, x, y, w, h):
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(1.1)
    c.line(x + 30, y + h - 14, x + w - 10, y + h - 14); c.line(x + 30, y + h - 14, x + 30, y + 8)
    sx = lambda q: x + 30 + (w - 45) * q / 4000
    sy = lambda s: y + h - 14 - (h - 28) * s / 45
    p = c.beginPath(); p.moveTo(sx(0), sy(0))
    for q, s in MEAS[1:]: p.lineTo(sx(q), sy(s))
    c.drawPath(p)
    c.setDash(4, 3); c.line(sx(0), sy(OFFSET), sx(4000), sy(limit(4000))); c.setDash()
    c.circle(sx(QF), sy(limit(QF)), 4)
    text(c, x + w - 62, y + h - 4, '하중 Q', 9.5); text(c, x + 36, y + 14, '침하 s ↓', 9.5)
    text(c, sx(150), sy(limit(1500)) - 13, '한계선(점선)', 9.5)
    text(c, sx(QF) - 112, sy(limit(QF)) - 24, f'교점 ≒ {QF:,.0f} kN', 9.5)
    text(c, sx(3500) - 150, sy(40) + 16, '측정 곡선(가상)', 9.5)

def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H))
    p1 = {
        0: ('말뚝기초 재하시험의 종류와 결과 해석', 13),
        1: ('Ⅰ. 개요', 14),
        2: ('재하시험은 시공된 말뚝에 하중을 가해 지지력과', 12.5),
        3: ('변위 거동을 직접 확인하는 시험으로, 설계 가정의', 12.5),
        4: ('검증, 근입깊이·시공기준 결정, 품질 확인에 쓴다.', 12.5),
        5: ('Ⅱ. 재하시험의 종류', 14),
        12: ('※ 정재하가 가장 직접적, 동재하는 수량 확대에 유리', 11.5),
        13: ('Ⅲ. 압축 정재하시험 방법', 14),
        14: ('① 반력: 앵커말뚝(인장) 또는 사하중 + 재하보', 12.5),
        15: ('② 재하: 유압잭, 단계별 하중 증가·유지(급속·완속)', 12),
        16: ('③ 계측: 하중계, 변위계(기준보 독립), 시간별 기록', 12),
        17: ('④ 계측말뚝: 텔테일·변형률계 → 하중전이 분석', 12),
        18: ('⑤ 재하 후 하중 제거, 회복량·잔류침하 측정', 12),
        19: ('※ 시험 수량·하중 단계·유지 시간은 적용 기준 확인', 11.5),
        20: ('', 12),
    }
    for r, (s, z) in p1.items():
        if s: line(c, r, s, z)
    text(c, 132, 731, '1', 14)
    ys = [764 - 5.4 * 32.35 - 4 - i * 30 for i in range(6)]
    rule_table(c, [202, 300, 605], ys, [
        ('구분', '내용·확인 사항'),
        ('압축 정재하', '연직 압축 하중-침하 곡선, 극한·항복 판정'),
        ('인발 정재하', '인발 저항, 오프셋 한계로 파괴하중 판정'),
        ('수평 재하', '하중-수평변위 관계, 사용성 한계로 평가'),
        ('동재하', 'PDA 항타 중 측정 → CAPWAP 지지력 추정'),
    ])
    c.showPage()
    p2 = {
        0: ('Ⅳ. 결과 해석(평가)', 14),
        1: ('1) 하중-침하 곡선에서 항복하중·극한하중 판정', 12.5),
        2: ('· 항복: P-S, logP-logS 꺾임점, S-logt 기울기 급변', 12),
        3: ('· 극한: 침하 급증(plunging) 또는 정의된 한계 침하', 12),
        4: ('2) Davisson 오프셋 한계(항타말뚝, D 약 610mm 미만)', 12.5),
        5: ('s = QL/AE + (4 + D/120) [mm] 선과 곡선의 교점', 12.5),
        13: ('3) 계산 예(가상): 강관 D508·t12, L=20m, E=200GPa', 11.5),
        14: ('A = π/4(508² - 484²) ≒ 18,699 mm², AE ≒ 3.74×10^6 kN', 11.5),
        15: ('오프셋 = 4 + 508/120 ≒ 8.23 mm', 12.5),
        16: ('Q=2,500: 한계 21.60, 측정 17.0 (차 -4.60)', 12.5),
        17: ('Q=3,000: 한계 24.28, 측정 26.0 (차 +1.72)', 12.5),
        18: ('보간 Q = 2,500 + 500×4.60/6.32 ≒ 2,864 kN', 12.5),
        19: ('→ Davisson 극한하중 ≒ 2,860 kN (학습용 가정)', 12.5),
        20: ('허용값은 적용 설계기준의 안전율·저항계수로 산정', 11.5),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '1', 14)
    mini_curve(c, 210, 764 - 12.4 * 32.35, 385, 205)
    c.showPage()
    p3 = {
        0: ('4) 기타 판정과 대구경 말뚝', 12.5),
        1: ('· AASHTO: 914mm 초과 항타말뚝은 D/30 오프셋', 12),
        2: ('· 현장타설말뚝: 말뚝 지름의 5% 침하 기준 참고', 12),
        3: ('· Chin 등 외삽법은 곡선이 파괴 전일 때 보조로만', 12),
        4: ('5) 동재하시험 해석', 12.5),
        5: ('· PDA: 변형률·가속도 → 응력, 전달에너지, 손상', 12),
        6: ('· CAPWAP 신호일치 → 주면·선단 저항 분리 추정', 12),
        7: ('· 재항타(시간경과)로 지지력 증가(set-up) 확인', 12),
        8: ('· 점성토는 감쇠가 커 정재하와 대비해 보정', 12),
        9: ('Ⅴ. 시험·해석 시 유의사항', 14),
        10: ('① 시험말뚝은 실제 말뚝과 같은 재료·장비·공법', 12),
        11: ('② 휴지기간 확보(시간 경과 효과), 기준보 독립', 12),
        12: ('③ 최대 하중을 설계하중보다 충분히 크게 계획', 12),
        13: ('④ 판정 방법·기준을 시험 전에 정하고 보고서 명시', 12),
        14: ('⑤ 결과를 근입깊이·관입량 관리기준에 반영', 12),
        15: ('Ⅵ. 결론', 14),
        16: ('재하시험은 종류 선택 → 하중-침하 곡선 해석 →', 12.5),
        17: ('설계 반영까지 이어질 때 의미가 있다. 정재하로', 12.5),
        18: ('기준을 세우고 동재하로 시공 품질을 넓게 관리한다.', 12),
        19: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
        20: ('참고: Caltrans Foundation Manual 8장, Fellenius', 10.5),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    text(c, 132, 731, '1', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(3):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2022 제128회 4교시 2번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)

# ── 본문 ─────────────────────────────────────────────────────────────
Q128 = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5210610&brdId=Q006&gSite=Q'
Q139 = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5263570&brdId=Q006&gSite=Q'
Q127 = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5210073&brdId=Q006&gSite=Q'
SOURCES = [
    ('Caltrans Foundation Manual(2015) Chapter 8 Static Pile Load Testing and Pile Dynamic Analysis — 정재하·PDA의 목적과 방법, ASTM D1143 급속재하', 'https://dot.ca.gov/-/media/dot-media/programs/engineering/documents/structureconstruction/foundation/sc-foundation-chapt8-a11y.pdf'),
    ('Fellenius, B.H.(2015) The Static Loading Test — Performance, Instrumentation, Interpretation — Davisson 오프셋 식, 기타 판정법, 양방향 재하시험', 'https://www.fellenius.net/papers/346%20The%20Static%20Loading%20Test%202nd%20CFPB%20Bolivia%202015.pdf'),
    ('GRL Engineers — Load-Movement Measurements and Failure Load Determination — Davisson 적용 범위, AASHTO 대구경 D/30·현장타설말뚝 5%D, 인발·수평 해석', 'https://www.grlengineers.com/wp-content/uploads/2023/05/load-movement-measurements-and-failure-load-interpretation.pdf'),
    ('국가건설기준센터 — KDS 11 50 15 말뚝기초 설계기준, KCS 11 50 15 말뚝기초 표준시방서 현행판 확인', 'https://www.kcsc.re.kr'),
    ('국가표준인증통합정보시스템(e-나라표준인증) — KS F 2445·KS F 2591 현행판 검색', 'https://standard.go.kr'),
]

def body(img_html, pdf_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    return f'''<p>말뚝 재하시험 답안은 시험 이름을 나열하는 데서 끝나면 25점 문제의 절반만 쓴 셈이다. 정재하·동재하·인발·수평 시험이 각각 무엇을 재는지, 그리고 측정한 하중-침하 곡선에서 항복하중과 극한하중을 어떤 기준으로 읽어 내는지까지 써야 '결과의 해석(평가)'에 답한 것이 된다. 해석 부분은 Davisson 오프셋 한계선으로 극한하중을 구하는 계산 예로 보인다.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2 data-ke-size="size26">오늘의 문제</h2>
<p><strong>시험 종목: 토목시공기술사 / 과목(학습 분류): 기초·흙막이(말뚝기초) / 유형: 논술형 / 관련 기출: 2022년 제128회 4교시 2번</strong></p>
<blockquote>기초공사에서 말뚝기초 재하시험의 종류와 시험결과의 해석(평가)에 대하여 설명하시오.</blockquote>
<p>위 문제는 2022년 제128회 4교시 2번 기출 원문이다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 3분, 작성 22분, 답안지 약 3쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이며 공식 시험 과목명이 아니다.</p>
<h3 data-ke-size="size23">출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 '말뚝'을 문제 문구에 쓴 문항은 16건이고, 그중 재하시험이나 지지력 평가를 직접 묻는 논술형은 다음 3건이다.</p>
<ul><li>2022년 제127회 4교시 3번(논술형): <a href="{Q127}">교량공사 기초 말뚝 시공 시 지지력 평가방법에 대하여 설명하시오.</a></li>
<li>2022년 제128회 4교시 2번(논술형): <a href="{Q128}">기초공사에서 말뚝기초 재하시험의 종류와 시험결과의 해석(평가)에 대하여 설명하시오.</a></li>
<li>2026년 제139회 3교시 5번(논술형): <a href="{Q139}">말뚝기초 재하시험의 종류와 목적을 열거하고 압축정재하 시험 및 평가방법에 대하여 설명하시오.</a></li></ul>
<p>제128회와 제139회는 문구가 거의 같고, 제127회는 재하시험을 포함한 지지력 평가 전반을 묻는다. 같은 문제가 세 번 나왔다는 뜻이 아니라 같은 내용으로 답할 수 있는 문제가 세 번 있었다는 뜻이다. 기초·흙막이·연약지반 등 지반 분야의 중복 허용 키워드 집계(64문항)는 분야 지표일 뿐 이번 유형의 출제 횟수나 공식 출제 비중이 아니다. 5일차 SPT N값 보정이 설계 전 지반조사의 신뢰도를 다뤘다면, 이번 글은 시공한 말뚝이 설계 지지력을 실제로 내는지 확인하는 단계를 다룬다.</p>
<h2 data-ke-size="size26">답안 목차</h2>
<p>Ⅰ. 개요 → Ⅱ. 재하시험의 종류 → Ⅲ. 압축 정재하시험 방법 → Ⅳ. 결과 해석(항복·극한 판정, Davisson 계산 예, 동재하 해석) → Ⅴ. 유의사항 → Ⅵ. 결론</p>
<h2 data-ke-size="size26">답안예시</h2>
<h3 data-ke-size="size23">Ⅰ. 개요</h3>
<p>말뚝 재하시험은 시공한 말뚝에 실제로 하중을 가하거나 타격을 주어 지지력과 변위 거동을 확인하는 시험이다. Caltrans 기초 매뉴얼은 정재하시험을 현장 말뚝의 지지력을 가장 정확하게 확인하는 방법으로 보고, 그 목적을 설계에 쓴 공칭 저항(압축·인발·수평)보다 시공된 말뚝의 지지력이 큰지 검증하는 데 둔다. 지층 변화가 크거나, 설계하중이 통상보다 크거나, 새 말뚝 형식·공법을 쓰거나, 시간 경과에 따른 지지력 변화가 예상될 때 특히 필요하다.</p>
<h3 data-ke-size="size23">Ⅱ. 재하시험의 종류</h3>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>구분</th><th>방법</th><th>얻는 결과</th></tr>
<tr><td>압축 정재하</td><td>유압잭으로 말뚝머리에 연직 하중을 단계적으로 가하고 반력은 앵커말뚝 또는 사하중으로 받음</td><td>하중-침하 곡선, 항복·극한하중</td></tr>
<tr><td>인발 정재하</td><td>말뚝을 끌어올리는 방향으로 재하</td><td>인발 저항, 오프셋 한계로 판정한 파괴하중</td></tr>
<tr><td>수평 재하</td><td>말뚝머리에 수평 하중(두 말뚝을 서로 밀거나 당기는 방식 포함)</td><td>하중-수평변위·회전 관계</td></tr>
<tr><td>동재하</td><td>항타 중 말뚝머리에 붙인 변형률계·가속도계로 측정(PDA)</td><td>추정 지지력, 항타 응력, 해머 전달에너지, 손상 위치</td></tr>
<tr><td>양방향 재하</td><td>말뚝 몸체 안에 넣은 재하 셀(bidirectional cell)이 위아래로 서로 밀어냄</td><td>셀 위 주면저항과 셀 아래 저항을 나누어 측정</td></tr>
</table>
<p>정재하시험은 결과가 가장 직접적이지만 반력 장치와 시간이 많이 든다. Caltrans는 압축·인발 시험 1회에 약 4~8시간이 걸린다고 적고, 정재하시험 대신 PDA로 말뚝 합격 기준을 정하거나 두 시험을 함께 쓰며, 함께 쓸 때 결과가 가장 좋다고 한다. 동재하시험이 반력 장치 없이 여러 말뚝에 적용하기 쉬워 시공 중 확인 수량을 늘리는 데 유리하다는 점은 필자의 정리이다. 양방향 재하시험은 말뚝 안의 셀이 위아래로 밀어내는 방식이라 말뚝머리 위에 반력 장치를 둘 필요가 없다.</p>
<h3 data-ke-size="size23">Ⅲ. 압축 정재하시험 방법</h3>
<ol><li><strong>반력:</strong> 시험말뚝 주위의 앵커말뚝(시험 중 인장을 받음)이나 사하중으로 재하보를 눌러 반력을 만든다. Caltrans는 압축 시험에 앵커말뚝 4본과 시험말뚝 1본의 5본 배치를 쓴다.</li>
<li><strong>재하:</strong> 하중을 단계별로 올리고 각 단계를 정해진 시간 동안 유지한다. Caltrans는 ASTM D1143의 급속재하(Procedure A: Quick Test)에 따라 설계하중의 약 5%씩 올린다.</li>
<li><strong>계측:</strong> 하중계와 유압 게이지로 하중을, 반력 장치와 분리된 기준보에 고정한 변위계로 말뚝머리 침하를 잰다.</li>
<li><strong>계측말뚝:</strong> 텔테일과 변형률계를 넣으면 깊이별 하중 분포를 얻어 주면저항과 선단저항을 나눌 수 있다. Fellenius는 텔테일을 말뚝의 압축량을 재는 장치로 다루고, 선단 변위는 머리 변위에서 압축량을 빼서 구하도록 한다.</li>
<li><strong>제하:</strong> 최대 하중 뒤 하중을 단계적으로 내리며 회복량과 잔류침하를 기록한다.</li></ol>
<p>국내 공사에서는 KCS 11 50 15 말뚝기초 표준시방서와 공사시방서에서 시험 수량, 하중 단계, 유지 시간, 최대 재하하중을 확인하고, 시험 방법은 KS F 2445(압축 정재하)·KS F 2591(동재하) 현행판을 따른다. 시험 수량·하중 단계·허용지지력 산정식 같은 구체 수치는 답안에 쓰기 전에 현행판 조문으로 확인한다.</p>
<h3 data-ke-size="size23">Ⅳ. 결과 해석(평가)</h3>
<p><strong>1) 항복하중과 극한하중.</strong> 재하시험 결과는 하중-침하 곡선으로 정리하고, 곡선에서 항복하중과 극한하중을 읽는다. 항복하중은 하중-침하(P-S) 곡선의 꺾임점, 양대수(logP-logS) 곡선의 꺾임점, 단계별 침하-시간(S-logt) 곡선의 기울기가 급변하는 하중 등으로 읽는 방법이 알려져 있으며, 실제 판정은 적용 기준에서 지정한 방법을 따른다. 극한하중은 하중을 더 늘리지 않아도 침하가 계속되는 상태(plunging)에서 정하거나, 곡선이 그 상태에 이르지 않으면 정의된 판정 기준으로 정한다. Fellenius는 판정 기준으로 Davisson 오프셋 한계 외에도 최대 곡률점 하중, Chin-Kondner 외삽, DeBeer 양대수 교점, Fuller-Hoy 곡선 기울기, 크리프 방법, 말뚝머리 지름 10% 침하 하중 등을 든다. 같은 곡선이라도 판정법에 따라 값이 달라지므로 어떤 방법을 썼는지 반드시 밝힌다.</p>
<p><strong>2) Davisson 오프셋 한계.</strong> 항타말뚝에서 널리 쓰는 기준이다. 말뚝을 탄성 기둥으로 보았을 때의 압축량 QL/AE에 일정한 오프셋을 더한 직선을 긋고, 측정 곡선이 이 선과 만나는 하중을 극한하중으로 본다.</p>
<p><strong>s<sub>lim</sub> = QL/AE + (4 + D/120)</strong> [mm] — Q: 하중, L: 말뚝 길이, A: 단면적, E: 탄성계수, D: 말뚝 지름(mm). 인치 단위로는 0.15 + D/120이다.</p>
<p>Fellenius는 이 식이 Davisson이 FHWA 재하시험 자료에 가장 잘 맞춘 정의일 뿐 지름이 곡선 해석에 물리적 의미를 갖는다는 뜻은 아니라고 설명한다. GRL 자료는 Davisson 기준을 지름(폭) 24인치(약 610 mm) 미만 항타말뚝에 주로 쓰고, AASHTO(2014)는 36인치(약 914 mm)보다 큰 항타말뚝에 오프셋을 D/30으로 하며 그 사이는 선형 보간한다고 정리한다. 현장타설말뚝은 AASHTO가 말뚝 지름의 5% 침하를 일반적인 파괴 기준으로 둔다고 같은 자료에 적혀 있다.</p>
{img_html}
<p><strong>3) 계산 예.</strong> 아래 조건과 측정값은 학습용 가정이다.</p>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>단계</th><th>계산</th><th>결과</th></tr>
<tr><td>조건</td><td>강관말뚝 D = 508 mm, t = 12 mm, L = 20 m, E = 200 GPa</td><td>—</td></tr>
<tr><td>단면적</td><td>A = π/4 × (508² − 484²)</td><td>≒ 18,699 mm²</td></tr>
<tr><td>축강성</td><td>AE = 200,000 MPa × 18,699 mm²</td><td>≒ 3.74 × 10⁶ kN</td></tr>
<tr><td>오프셋</td><td>4 + 508/120</td><td>≒ 8.23 mm</td></tr>
<tr><td>Q = 2,500 kN</td><td>한계 = 2,500 × 20,000 / 3.74×10⁶ + 8.23 = 13.37 + 8.23</td><td>21.60 mm (측정 17.0 → 아래)</td></tr>
<tr><td>Q = 3,000 kN</td><td>한계 = 16.04 + 8.23</td><td>24.28 mm (측정 26.0 → 넘음)</td></tr>
<tr><td>교점 보간</td><td>2,500 + 500 × 4.60 / (4.60 + 1.72)</td><td>≒ 2,864 kN</td></tr>
</table>
<p>측정 곡선은 2,500 kN에서 한계선보다 4.60 mm 위(침하가 작음)에 있고 3,000 kN에서 1.72 mm 아래로 넘어가므로, 두 점 사이를 직선 보간하면 Davisson 극한하중은 약 2,860 kN이다. 이 강관은 지름 508 mm로 24인치보다 작아 Davisson 기준을 그대로 적용할 수 있는 범위다. 설계에 쓰는 허용지지력이나 저항은 이 값을 적용 설계기준의 안전율 또는 저항계수로 나누거나 곱해 정한다. 수험 자료에 자주 나오는 '항복하중의 1/2과 극한하중의 1/3 중 작은 값' 같은 허용지지력 산정 규칙도 KDS 11 50 15 등 적용 기준의 현행 조문과 대조한 뒤 쓴다.</p>
<p><strong>4) 동재하시험 해석.</strong> PDA는 항타 때마다 말뚝머리의 변형률과 가속도를 측정해 말뚝 응력, 해머가 실제로 전달한 에너지, 콘크리트 말뚝의 균열 위치나 강관의 좌굴 지점 같은 손상을 찾는다. 측정 파형을 CAPWAP 같은 신호일치 해석에 넣으면 주면저항과 선단저항을 나누어 정적 지지력을 추정할 수 있다. 점성토에서는 시간이 지나며 지지력이 커지는(set-up) 경우가 있어, Caltrans는 말뚝을 계획 깊이보다 조금 남겨 두었다가 휴지 후 재항타로 증가량을 확인하는 절차를 둔다. 같은 매뉴얼은 PDA가 사질토에서는 신뢰도가 높지만 감쇠가 큰 실트·점토에서는 낮을 수 있다고 하므로, 점성토 현장은 정재하 결과와 대비해 해석 계수를 보정한다.</p>
<p><strong>5) 인발·수평 시험 해석.</strong> GRL 자료는 항타말뚝 인발 시험의 파괴하중을 탄성 신장량에 0.15인치를 더한 오프셋 선과의 교점으로 정의하는 경우가 많다고 하고, 수평 재하시험은 파괴하중보다 강도·사용성 한계를 만족하는 하중-변위 관계를 찾는 데 쓴다고 정리한다.</p>
<h3 data-ke-size="size23">Ⅴ. 시험·해석 시 유의사항</h3>
<ul><li>시험말뚝은 실제 말뚝과 같은 재료·장비·공법·근입 조건으로 시공한다.</li>
<li>항타 직후와 휴지 후의 지지력이 다를 수 있으므로 시험 시기를 정해 기록한다.</li>
<li>변위계 기준보는 반력 장치와 시험말뚝의 영향을 받지 않게 독립시킨다.</li>
<li>최대 재하하중은 판정에 필요한 곡선 구간을 얻도록 설계하중보다 충분히 크게 계획한다.</li>
<li>판정 방법과 합격 기준을 시험 전에 정하고 보고서에 사용한 방법을 적는다.</li>
<li>결과는 시공 말뚝의 근입깊이·최종 관입량 같은 관리 기준에 반영한다.</li></ul>
<h3 data-ke-size="size23">Ⅵ. 결론</h3>
<p>재하시험은 종류를 고르는 데서 끝나지 않고 하중-침하 곡선을 어떤 기준으로 해석해 설계에 반영하는지까지 이어져야 의미가 있다. 필자는 정재하시험으로 대표 말뚝의 지지력 기준을 세우고 동재하시험으로 시공 말뚝 전반을 넓게 확인하는 조합을 답안의 결론으로 권한다.</p>
<h2 data-ke-size="size26">핵심 암기어</h2>
<p>압축·인발·수평 정재하 · 동재하(PDA·CAPWAP) · 양방향 재하 · Davisson QL/AE + 4 + D/120 · 판정법 명시</p>
<h2 data-ke-size="size26">답안 자가점검</h2>
<ul><li>재하시험의 종류를 방법과 얻는 결과로 구분했는가?</li>
<li>정재하시험의 반력·재하·계측 구성을 썼는가?</li>
<li>항복하중과 극한하중을 구분하고 판정법을 제시했는가?</li>
<li>Davisson 식의 변수·단위와 적용 범위를 밝혔는가?</li>
<li>동재하시험의 장점과 점성토·시간 경과 한계를 적었는가?</li>
<li>결과를 설계·시공 관리 기준에 반영하는 단계까지 썼는가?</li></ul>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 형식의 3쪽 따라쓰기 PDF이다. 답안·표·하중-침하 도식이 옅은 회색 글씨로 들어 있어 출력해 그대로 따라 쓸 수 있다.</p>
<h2 data-ke-size="size26">공식 참고자료</h2>
<ul>{src}</ul>
<p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 자료 확인일은 2026년 10월 22일이다. 재하시험의 목적·방법과 PDA는 Caltrans 매뉴얼 8장, Davisson 식·판정법 목록·텔테일·양방향 재하시험 개략은 Fellenius(2015), Davisson 적용 범위와 AASHTO 대구경·현장타설말뚝·인발·수평 해석은 GRL 자료를 근거로 했다. AASHTO 규정은 GRL 자료의 정리를 인용한 것이다. 해외 자료는 시험 원리와 해석 방법의 출처이며, 국내 시험 수량·하중 단계·허용지지력은 KDS 11 50 15, KCS 11 50 15, KS F 2445·2591 현행판을 따른다.</p>
<p>#토목시공기술사 #말뚝재하시험 #정재하시험 #동재하시험 #Davisson #말뚝기초 #기술사답안 #하루한문제</p>'''

if __name__ == '__main__':
    figure(); make_pdf()
    t_img = f'<p data-ax-attach="{FIG_NAME}"></p><p>직접 작성한 개념도. 측정 곡선과 수치는 학습용 가정이다.</p>'
    t_pdf = f'<p data-ax-attach="{PDF_NAME}"></p>'
    b_img = f'<figure><img src="{CDN}pile-load-test.jpg" alt="말뚝 압축 정재하시험 하중-침하 곡선과 Davisson 한계선 개념도" style="max-width:100%;height:auto"><figcaption>직접 작성한 개념도. 측정 곡선과 수치는 학습용 가정이다.</figcaption></figure>'
    b_pdf = f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (3쪽)</a></p>'
    (OUT / '티스토리게시본문.html').write_text(body(t_img, t_pdf))
    (OUT / 'Blogger게시본문.html').write_text(body(b_img, b_pdf))
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(f'<img src="{FIG_NAME}">', f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>') + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    print(json.dumps(CALC, ensure_ascii=False))
