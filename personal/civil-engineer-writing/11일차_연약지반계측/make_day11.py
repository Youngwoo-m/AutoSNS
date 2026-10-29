"""11일차 연약지반 성토 시 계측항목과 계측기 — 개념도·따라쓰기 PDF·티스토리/Blogger 본문을 만든다."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
import json
from PIL import Image, ImageDraw, ImageFont
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 연약지반 성토 시 계측항목과 계측기 | 하루 한 문제 11일차'
PDF_NAME = '11일차_연약지반계측_답안예시_따라쓰기.pdf'
FIG_NAME = '연약지반성토_계측기배치_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_쌍곡선법.png', '수식2_계산예.png', '도식_쌍곡선법침하예측.gif'
BANNER = 'banner.png'
CDN = 'https://geoai-na.netlify.app/civil-questions/materials/day11/'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'

# ── 계산 예(가상 예시): 쌍곡선법 ──────────────────────────────────────
S0 = 0.80                                  # 성토 완료 시점 침하량(m)
OBS = [(30, 0.20), (90, 0.40)]             # (성토 완료 후 경과일, 그 뒤 추가 침하 m)
Y = [t / d for t, d in OBS]                # t/(St−S0)
BETA = (Y[1] - Y[0]) / (OBS[1][0] - OBS[0][0])
ALPHA = Y[0] - BETA * OBS[0][0]
SINF = S0 + 1 / BETA
S90 = S0 + OBS[1][1]
U90 = S90 / SINF
CALC = {'y30': Y[0], 'y90': Y[1], 'beta': BETA, 'alpha': ALPHA, 'S_inf': round(SINF, 3), 'S90': S90,
        'U90': round(U90, 3), 'residual': round(SINF - S90, 3)}

# ── 개념도: 성토 단면과 계측기 배치 ─────────────────────────────────
def figure():
    im = Image.new('RGB', (1600, 1000), 'white'); dr = ImageDraw.Draw(im)
    f = lambda z: ImageFont.truetype(PRET, z)
    INK, TEAL, RED, GRAYC, SOFT, SOIL, CLAY = '#263746', '#176977', '#B6462F', '#7A8790', '#EAF2F3', '#E9DFC9', '#D9D2C3'
    dr.text((60, 36), '연약지반 성토 — 계측기 배치 개념(축척 없음)', font=f(40), fill=INK)
    gy, by = 430, 820                                                  # 원지반면, 지지층 윗면
    dr.rectangle([60, gy, 1000, by], fill=CLAY)                         # 연약 점토층
    dr.rectangle([60, by, 1000, 900], fill='#C9C2B2')                   # 지지층
    dr.rectangle([60, gy - 14, 1000, gy], fill='#F2E3B3')               # 수평배수층(샌드매트)
    dr.polygon([(170, gy - 14), (390, 250), (690, 250), (910, gy - 14)], fill=SOIL, outline=INK)
    for x in range(250, 860, 60): dr.line([(x, gy), (x, 700)], fill='#B9B09E', width=2)   # 연직배수재
    dr.text((470, 300), '성토', font=f(30), fill=INK)
    dr.text((80, 750), '연약 점토층', font=f(26), fill=INK)
    dr.text((80, by + 20), '지지층(부동층)', font=f(24), fill=INK)
    dr.text((125, gy + 18), '↑ 수평배수층(노란 띠)', font=f(20), fill=GRAYC)
    dr.text((470, 712), '연직배수재', font=f(20), fill=GRAYC)
    def tag(x, y, n): dr.ellipse([x - 17, y - 17, x + 17, y + 17], fill=RED); dr.text((x - 8, y - 15), n, font=f(24), fill='white')
    # ① 지표침하판(성토 바닥 중앙·어깨)
    for x in (540, 410):
        dr.rectangle([x - 26, gy - 22, x + 26, gy - 12], fill=TEAL); dr.line([(x, gy - 22), (x, 238)], fill=TEAL, width=4)
    tag(540, 205, '1'); tag(410, 205, '1')
    # ② 층별침하계(중앙 부근 시추공, 지층 경계 소자)
    dr.line([(610, 250), (610, by + 30)], fill=TEAL, width=5)
    for y in (500, 600, 700, by - 6): dr.rectangle([598, y - 5, 622, y + 5], fill=RED)
    tag(650, 545, '2')
    # ③ 간극수압계(점토층 중간 깊이)
    for y in (540, 680): dr.ellipse([470 - 11, y - 11, 470 + 11, y + 11], fill=TEAL)
    tag(430, 610, '3')
    # ④ 지하수위계(수평배수층·사업지구 바깥)
    dr.line([(100, gy - 60), (100, gy + 60)], fill=TEAL, width=6); tag(100, gy - 85, '4')
    # ⑤ 지중경사계(비탈끝, 하단 부동층 근입)
    dr.line([(945, gy - 40), (945, by + 50)], fill=TEAL, width=7); tag(945, gy - 70, '5')
    # ⑥ 지표변위말뚝(비탈끝 바깥)
    for x in (965, 990): dr.rectangle([x - 4, gy - 40, x + 4, gy + 10], fill=INK)
    tag(985, 365, '6')
    rx = 1060
    items = [('1', '지표침하판', '지표 침하량·침하속도'), ('2', '층별침하계', '지층별 침하'), ('3', '간극수압계', '과잉간극수압 증가·소산'),
             ('4', '지하수위계', '지하수위·배수층 기능'), ('5', '지중경사계', '깊이별 수평변위'), ('6', '지표변위말뚝', '비탈끝 바깥 측방이동·융기')]
    dr.text((rx, 130), '번호  계측기 → 계측항목', font=f(26), fill=GRAYC)
    for k, (n, a, b) in enumerate(items):
        yy = 180 + k * 105
        dr.rounded_rectangle([rx - 10, yy - 10, rx + 500, yy + 82], 12, fill=SOFT)
        tag(rx + 20, yy + 18, n)
        dr.text((rx + 52, yy), a, font=f(28), fill=INK); dr.text((rx + 52, yy + 42), b, font=f(22), fill=TEAL)
    dr.text((60, 940), '직접 작성한 개념도 / 위치는 일반적 배치 예시이며 실제 위치·수량은 계측계획서로 정한다. 근거: 한국지반공학회논문집 38(12), 2022', font=f(22), fill=GRAYC)
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

def section(c, gy):
    """2쪽 계측기 배치 모식도(축척 없음)."""
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(1.1)
    by = gy - 80
    c.line(202, gy, 605, gy); c.line(202, by, 605, by)                    # 원지반면, 지지층 윗면
    p = c.beginPath(); p.moveTo(260, gy); p.lineTo(340, gy + 55); p.lineTo(470, gy + 55); p.lineTo(550, gy); c.drawPath(p)
    text(c, 345, gy + 30, '성토', 10); text(c, 207, gy - 40, '연약 점토층', 9.5); text(c, 207, by - 13, '지지층', 9.5)
    c.rect(400, gy, 14, 5, stroke=1, fill=0); c.line(407, gy + 5, 407, gy + 70); text(c, 395, gy + 74, '①침하판', 9.5)
    c.line(445, gy + 55, 445, by - 10)
    for y in (gy - 25, gy - 50, gy - 75): c.rect(441, y - 3, 8, 6, stroke=1, fill=0)
    text(c, 452, gy - 30, '②층별침하계', 9.5)
    for y in (gy - 35, gy - 70): c.circle(372, y, 4, stroke=1, fill=0)
    text(c, 300, gy - 60, '③간극수압계', 9.5)
    c.line(230, gy + 25, 230, gy - 20); text(c, 207, gy + 30, '④수위계', 9.5)
    c.setLineWidth(2); c.line(565, gy, 565, by - 8); c.setLineWidth(1.1)
    text(c, 570, gy - 45, '⑤경사계', 9.5)
    c.rect(588, gy, 4, 14, stroke=1, fill=0); text(c, 548, gy + 30, '⑥변위말뚝', 9.5)

def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H))
    p1 = {
        0: ('연약지반 성토 시 주요 계측항목과 계측기의 종류', 12.5),
        1: ('1. 개요', 14),
        2: ('연약지반에 성토하면 압밀침하와 측방변위가 함께', 12.5),
        3: ('생긴다. 계측은 시공 중 자료로 성토 안정성과 침하', 12.5),
        4: ('거동을 분석해 설계를 보완하고 개량 품질을 확인한다.', 12),
        5: ('2. 계측 목적', 14),
        6: ('① 안정관리: 성토 중 활동파괴 방지, 성토속도 조절', 12),
        7: ('② 침하관리: 최종·잔류침하, 압밀도 → 제거·포장 시기', 12),
        8: ('3. 계측항목과 계측기', 14),
        16: ('4. 설치 유의사항', 14),
        17: ('· 경사계: 하단을 부동층에 근입(KCS 11 10 15:2018)', 12),
        18: ('· 층별침하계: 지층 경계, 두꺼우면 10~15m 간격,', 12),
        19: ('  개량·미개량 경계와 미개량층에도 설치', 12),
        20: ('· 간극수압계: 예상 측정범위 1.5배 이상 게이지', 12),
        21: ('· 성토 전에 설치하고 초기치를 측정한다', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    text(c, 132, 731, '3', 14)
    ys = [764 - 8.45 * 32.35 - i * 30 for i in range(8)]
    rule_table(c, [202, 290, 380, 605], ys, [
        ('계측항목', '계측기', '목적'),
        ('지표침하', '지표침하판', '전체 침하량·속도, 최종침하 추정'),
        ('층별침하', '층별침하계', '지층별 침하, 미개량층 확인'),
        ('간극수압', '간극수압계', '과잉간극수압 증가·소산 경향'),
        ('지하수위', '지하수위계', '정수압 기준, 수평배수층 기능'),
        ('지중수평변위', '지중경사계', '깊이별 측방변위, 활동 징후'),
        ('지표변위', '변위말뚝', '비탈끝 바깥 측방이동·융기'),
    ], sizes=(10.5, 10.5))
    c.showPage()
    p2 = {
        0: ('5. 계측관리', 14),
        1: ('① 안정관리: 수평변위·침하·간극수압을 함께 보고', 12),
        2: ('   변위속도가 커지면 성토 중지·속도 조절', 12),
        3: ('② 침하관리: 쌍곡선법·Asaoka법으로 최종침하 추정', 12),
        4: ('③ 수준측량: 폐합·결합측량, 허용오차 관리', 12),
        5: ('6. 계산 예(가상 예시) — 쌍곡선법', 14),
        6: ('t/(St-S0) = α + βt, S∞ = S0 + 1/β', 12.5),
        7: ('30/0.20 = 150, 90/0.40 = 225 (일/m)', 12.5),
        8: ('β = 75/60 = 1.25, α = 150 - 1.25×30 = 112.5', 12.5),
        9: ('S∞ = 0.80 + 1/1.25 = 1.60m, U = 1.20/1.60 = 75%', 12),
        10: ('※ 가상값. 자료 구간 선택에 따라 결과가 달라진다', 11),
        11: ('■ 그림. 계측기 배치(모식도)', 12.5),
        18: ('7. 결론', 14),
        19: ('안정관리(경사계·간극수압계)와 침하관리(침하판·', 12.5),
        20: ('층별침하계)를 짝지어 배치하고 성토속도·제거시기 결정', 11.5),
        21: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    section(c, 764 - 14.3 * 32.35)
    text(c, 132, 731, '3', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(2):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2024 제132회 1교시 3번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)

# ── 본문 ─────────────────────────────────────────────────────────────
Q = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq={}&brdId=Q006&gSite=Q'
Q126, Q128, Q130, Q132, Q134, Q140 = (Q.format(s) for s in (5209527, 5210610, 5211903, 5212868, 5213590, 5274160))
KGS = 'https://doi.org/10.7843/kgs.2022.38.12.67'
SOURCES = [
    ('정나영·강승찬·김태형, 「준설점토가 상부에 매립된 대심도 연약지반 계측관리」, 한국지반공학회논문집 제38권 제12호(2022.12), pp.67~78 — 2장 국내 기준 현황(KDS 11 10 15, KCS 11 10 15:2018, EXCS 11 10 15 검토), 3장 계측기별 선정·설치·분석 제안, 표 3 수준측량 허용오차(10 mm√L·5 mm√L 표기 원문 확인)', KGS),
    ('국가건설기준센터 — KCS 11 10 15 시공 중 지반계측, KDS 11 10 15 지반계측(원문은 이 글에서 직접 열지 못함, 위 논문이 검토한 2018년판 내용만 옮김)', 'https://www.kcsc.re.kr/'),
]

def body(img_html, f1_html, f2_html, gif_html, pdf_html, banner_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    return f'''{banner_html}<p>연약지반 성토 계측은 2024년 토목시공기술사 1교시 단답형에 두 번(제132회 3번, 제134회 3번) 나왔다. 답안은 계측 목적(안정관리·침하관리), 계측항목과 계측기의 짝(지표침하판·층별침하계·간극수압계·지하수위계·지중경사계·변위말뚝), 설치 유의사항, 계측관리 방법 순서로 짠다. 설치 기준은 KCS 11 10 15(2018)와 이를 검토한 2022년 한국지반공학회 논문에서 옮겼고, 시방서 원문과 최신 개정판은 직접 대조하지 못했다.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2 data-ke-size="size26">오늘의 문제</h2>
<p><strong>시험 종목: 토목시공기술사 / 과목(학습 분류): 기초·연약지반 / 유형: 단답형 / 관련 기출: 2024년 제132회 1교시 3번, 2024년 제134회 1교시 3번</strong></p>
<blockquote>연약지반 성토 시 주요 계측항목과 계측기의 종류</blockquote>
<p>위 문제는 2024년 제132회 1교시 3번 기출 원문이다. 같은 해 제134회 1교시 3번은 「연약지반의 계측」으로 범위를 넓혀 물었으며, 이 글의 답안은 두 문제에 모두 쓸 수 있도록 계측 목적과 관리 방법을 함께 넣었다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 1분, 작성 8분, 답안지 1~2쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이며 공식 시험 과목명이 아니다.</p>
<h3 data-ke-size="size23">출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 연약지반 성토·계측과 가까운 문항은 다음과 같다.</p>
<ul><li>2024년 제132회 1교시 3번: <a href="{Q132}">연약지반 성토 시 주요 계측항목과 계측기의 종류</a></li>
<li>2024년 제134회 1교시 3번: <a href="{Q134}">연약지반의 계측</a></li>
<li>2023년 제130회 2교시 3번: <a href="{Q130}">연약지반 공사 시 발생하는 사고유형과 대책방안</a></li>
<li>2022년 제128회 2교시 3번: <a href="{Q128}">연약지반 위에 설치된 교대의 측방유동 발생 시 문제점과 대책</a></li>
<li>2022년 제126회 3교시 4번: <a href="{Q126}">점성토지반에서 연직배수공법의 종류, 특징 및 시공 시 유의사항</a>, 2026년 제140회 1교시 11번: <a href="{Q140}">흙의 압밀침하</a></li></ul>
<p>문항 제목은 일부 줄여 적었으며 정확한 표현은 Q-net 문제지에서 확인한다. 같은 465문항에서 '연약'이 들어간 문항은 8개이고, 그중 계측을 직접 묻는 단답형이 2024년에 두 번 나와 이번 회차로 골랐다. 이 횟수는 문제 제목을 대조해 센 것이며 공식 출제 비중이 아니다. 3일차 흙막이 계측관리와는 대상(굴착 흙막이와 성토 하부 연약지반)과 관리 목표가 달라 겹치지 않게 썼다.</p>
<h2 data-ke-size="size26">답안 목차</h2>
<p>1. 개요 → 2. 계측 목적 → 3. 계측항목과 계측기 → 4. 설치 유의사항 → 5. 계측관리 → 6. 계산 예 → 7. 결론</p>
<h2 data-ke-size="size26">답안예시</h2>
<h3 data-ke-size="size23">1. 개요</h3>
<p>연약지반 위에 흙을 쌓으면 압밀침하가 오래 이어지고, 성토 속도가 지반의 강도 증가보다 빠르면 측방변위가 커지며 활동파괴로 이어질 수 있다. 2022년 한국지반공학회 논문(이하 '2022 논문')은 연약지반 계측의 목적을 시공 중 수집한 자료로 성토 중 안정성과 침하 거동을 분석해 설계를 보완·수정하고 최종 지반개량 품질을 확인하는 것으로 정리한다.</p>
<h3 data-ke-size="size23">2. 계측 목적</h3>
<ul><li><strong>안정관리</strong> — 성토 중 활동파괴를 막도록 변위와 간극수압을 보며 성토 속도와 단계를 조절한다.</li>
<li><strong>침하관리</strong> — 계측 침하량으로 최종침하량·잔류침하량·압밀도를 추정해 재하성토 제거, 포장·구조물 시공 시기를 정한다.</li></ul>
<p>2022 논문은 계측관리의 기본 방향을 ① 지반조사로 추정한 설계 지반정수의 수정, ② 시공 중 조사와 계측 역해석으로 얻은 지반정수로 설계 수정, ③ 계측결과와 확인 지반조사로 최종 시공 품질 확인의 세 가지로 든다. 같은 논문은 KCS 11 10 15(2018)가 주로 안정관리를 목적으로 기술되어 있고 침하관리의 구체 기준은 제시하지 않는다고 평가했다.</p>
<h3 data-ke-size="size23">3. 계측항목과 계측기</h3>
{img_html}
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>계측항목</th><th>계측기</th><th>목적·활용</th><th>설치 위치(예)</th></tr>
<tr><td>지표침하</td><td>지표침하판(수준측량)</td><td>전체 침하량·침하속도, 최종침하량·압밀도 추정</td><td>성토 중앙·비탈어깨 아래 원지반면</td></tr>
<tr><td>층별침하</td><td>층별침하계(침하소자식(마그네틱형)·스크류형 등)</td><td>지층별 침하, 미개량층 침하 확인</td><td>압축특성이 바뀌는 지층 경계, 개량·미개량 경계</td></tr>
<tr><td>간극수압</td><td>간극수압계</td><td>과잉간극수압의 증가·소산 경향, 하중·응력 변화 확인</td><td>압밀대상 점토층 안</td></tr>
<tr><td>지하수위</td><td>지하수위계</td><td>정수압 기준값, 수평배수층·집수정 기능 확인</td><td>수평배수층, 점토층 하부 투수층, 사업지구 바깥</td></tr>
<tr><td>지중 수평변위</td><td>지중경사계</td><td>깊이별 측방변위, 활동 징후 파악</td><td>비탈끝 부근, 하단은 부동층까지</td></tr>
<tr><td>지표 수평변위·융기</td><td>지표변위말뚝</td><td>비탈끝 바깥 지표의 측방이동·융기</td><td>비탈끝 바깥 원지반</td></tr>
</table>
<p>앞의 다섯 항목(지표침하·층별침하·간극수압·지하수위·지중경사)은 2022 논문이 연약지반 개량공사의 계측기별 제안을 정리한 항목이다. 지표변위말뚝은 그 논문의 정리에는 없으나 비탈끝 바깥의 측방이동을 눈으로 확인하는 보조 계측으로 함께 쓰는 것으로 보아 넣었다(필자 정리). 설치 위치 열은 일반적인 배치 예이며, 실제 위치·수량은 현장의 계측계획서로 정한다.</p>
<h3 data-ke-size="size23">4. 설치 유의사항</h3>
<ul><li><strong>지중경사계</strong> — 2022 논문에 따르면 KCS 11 10 15(2018)는 경사계를 반드시 부동층(예: 기반암)에 설치하도록 한다. 경사계는 맨 아래를 '0'으로 두고 깊이별 상대변위를 더해 전체 변위를 구하므로, 하단이 움직이면 그 아래의 수평변위를 알 수 없다. 같은 논문은 준설매립 대심도 연약지반이라면 N치 40 이상의 풍화암이나 연약층 하부 자갈층에 설치해도 수평변위 파악에 문제가 없다고 보았다(부산항 신항 사례에 근거한 제안).</li>
<li><strong>층별침하계</strong> — 압축특성이 바뀌는 지층 경계에 두고, 연약층이 15 m 이상으로 두꺼우면 토질이 비슷해도 10~15 m 간격으로 나누며, 배수재 시공 경계(개량층·미개량층)와 미개량층에도 설치한다(2022 논문 제안). 같은 논문은 KCS 11 10 15(2018)가 침하소자식(마그네틱형) 설치 방법만 다루며, 조사한 현장에서 마그네틱형이 휨 변형과 가이드관 마찰로 침하를 대부분 작게 쟀다고 보고하고, 대심도 연약지반에서는 스크류형이 바람직해 보인다고 했다. 다만 지반이 매우 연약하면 자중으로 관입될 수 있어, 결론에서 중량과 스크류 관입심도를 지반특성에 맞게 검토한 뒤 설치하라고 적었다.</li>
<li><strong>간극수압계</strong> — 2022 논문은 현행 시방서가 기본적으로 1 MPa 이상 측정을 요구하지만 측정범위가 넓을수록 정밀도가 떨어지므로, 예상 측정범위의 1.5배 이상 정도의 게이지를 쓰는 것이 바람직하다고 제안한다.</li>
<li><strong>지하수위계</strong> — 사업지구 바깥에 성토 영향이 없는 곳이 있으면 토공 전에 먼저 설치해 초기 지하수위 경향을 확인하고, 성토 중에는 지하수위가 수평배수층 안에 머물도록 관리한다(2022 논문).</li>
<li><strong>공통</strong> — 성토 전에 설치해 초기치를 잡아야 성토로 생긴 변화만 가려낼 수 있다(필자 설명).</li></ul>
<h3 data-ke-size="size23">5. 계측관리</h3>
<p><strong>안정관리</strong>는 지중경사계·지표변위말뚝의 수평변위, 지표침하판의 침하, 간극수압계의 과잉간극수압을 함께 보고, 변위 속도가 갑자기 커지면 성토를 멈추거나 속도를 늦추는 방식으로 한다. 침하와 수평변위의 관계를 도표로 보는 판정법(Matsuo-Kawamura 방법 등)이 쓰이지만, 이 글은 그 판정 기준값을 원문으로 확인하지 못해 수치를 적지 않는다. 관리기준치는 현장 계측계획서에 정한 값을 따른다.</p>
<p><strong>침하관리</strong>는 지표침하판·층별침하계 자료로 쌍곡선법이나 Asaoka법 같은 침하 예측법을 써서 최종침하량과 압밀도를 추정한다. 2022 논문은 압축특성이 다른 다층지반이면 층별침하계로 지층마다 따로 분석해야 하고, 그렇게 합산하면 전체층으로 한 번에 분석할 때보다 잔류침하량이 크게 나온다고 적었다. 간극수압계 결과만으로 개량도를 판정하기는 어렵다고 보고, 과잉간극수압의 소산 여부를 층별침하계의 침하속도·침하량과 비교하는 정성 자료로 쓰도록 권한다.</p>
<p><strong>수준측량</strong>은 침하 예측의 바탕이다. 2022 논문 표 3은 준설매립지처럼 침하가 큰 곳은 3등 수준측량 허용오차(10 mm√L, L은 편도거리 km), 일반 연약지반이나 정밀도가 필요한 곳은 2등(5 mm√L) 정도로 관리하도록 제안하며, 폐합·결합측량으로 오차를 보정한다. 측량 오차를 5 mm 이내로 관리한 경우와 50 mm 이내로 관리한 경우 장래침하량 예측범위가 10배 이상 차이 났다는 인용 결과도 함께 실었다. 측정 빈도는 KCS 11 10 15가 정하므로 현장 시방서를 확인한다.</p>
<h3 data-ke-size="size23">6. 계산 예 (가상 예시) — 쌍곡선법</h3>
<p>아래 침하량은 설명을 위해 만든 가상 예시이며 실측값이나 공식 기준값이 아니다. 쌍곡선법은 성토 완료 뒤 침하가 쌍곡선 모양으로 수렴한다고 보고, t/(S<sub>t</sub> − S<sub>0</sub>)와 t가 직선 관계라는 성질로 최종침하량을 구하는 경험적 예측법이다.</p>
{f1_html}
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>항목</th><th>계산</th><th>결과</th></tr>
<tr><td>가정</td><td>성토 완료 때 S<sub>0</sub> = 0.80 m, 그 뒤 30일 0.20 m, 90일 0.40 m 추가 침하</td><td>—</td></tr>
<tr><td>t/(S<sub>t</sub> − S<sub>0</sub>)</td><td>30/0.20, 90/0.40</td><td>150, 225 (일/m)</td></tr>
<tr><td>β, α</td><td>(225 − 150)/(90 − 30), 150 − 1.25 × 30</td><td>β = 1.25 m<sup>-1</sup>, α = 112.5 일/m</td></tr>
<tr><td>최종침하량</td><td>0.80 + 1/1.25</td><td>S<sub>∞</sub> = 1.60 m</td></tr>
<tr><td>90일 압밀도(침하량 기준)</td><td>(0.80 + 0.40)/1.60</td><td>0.75 (75 %)</td></tr>
<tr><td>90일 이후 남은 침하</td><td>1.60 − 1.20</td><td>0.40 m</td></tr>
</table>
{f2_html}
<p>점 두 개로 직선을 정했으므로 이 결과는 계산 순서를 보이기 위한 것이다. 실제로는 성토가 끝난 뒤 여러 번 잰 자료로 회귀직선을 구하며, 2022 논문이 지적하듯 분석 구간과 자료 선택 기준이 정해져 있지 않아 같은 자료로도 결과가 달라질 수 있다. 또 침하량 기준 압밀도는 간극수압 소산으로 본 압밀도와 같지 않을 수 있어 두 자료를 함께 본다. 아래 도식은 같은 가상 조건을 그림으로 옮긴 것이다.</p>
{gif_html}
<h3 data-ke-size="size23">7. 결론</h3>
<p>연약지반 성토 계측은 안정관리(지중경사계·지표변위말뚝·간극수압계)와 침하관리(지표침하판·층별침하계)로 짝지어 배치하고, 지하수위계는 정수압 기준값과 배수층 기능을 확인하는 보조 계측으로 둔다(이 짝짓기는 필자 정리). 성토 전 초기치와 정밀한 수준측량을 바탕으로 성토속도 조절과 재하성토 제거·포장 시기를 정하는 것이 답안의 골격이다.</p>
<h2 data-ke-size="size26">핵심 암기어</h2>
<p>안정관리·침하관리 · 침하판·층별침하계·간극수압계·수위계·경사계·변위말뚝 · 경사계 하단 부동층 · 성토 전 초기치 · 쌍곡선법 S∞ = S0 + 1/β</p>
<h2 data-ke-size="size26">답안 자가점검</h2>
<ul><li>계측 목적을 안정관리와 침하관리로 나눠 썼는가?</li>
<li>계측항목과 계측기를 짝지어 표로 정리했는가?</li>
<li>경사계 근입(부동층), 층별침하계 위치, 성토 전 초기치를 썼는가?</li>
<li>계측 결과를 성토속도 조절과 재하성토 제거 시기 판단에 연결했는가?</li>
<li>제134회형(연약지반의 계측) 문제라면 계측관리 방법과 침하 예측법을 더 길게 썼는가?</li></ul>
<h2 data-ke-size="size26">기호·단위 정리</h2>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>기호</th><th>뜻</th><th>단위</th><th>출처</th></tr>
<tr><td>t</td><td>성토 완료 뒤 경과 시간</td><td>일</td><td>쌍곡선법 일반식</td></tr>
<tr><td>S<sub>0</sub></td><td>성토 완료(기준) 시점 침하량</td><td>m</td><td>쌍곡선법 일반식</td></tr>
<tr><td>S<sub>t</sub></td><td>시간 t의 침하량</td><td>m</td><td>쌍곡선법 일반식</td></tr>
<tr><td>α, β</td><td>t/(S<sub>t</sub> − S<sub>0</sub>)–t 직선의 절편·기울기</td><td>일/m, m<sup>-1</sup></td><td>쌍곡선법 일반식</td></tr>
<tr><td>S<sub>∞</sub></td><td>최종침하량 추정값</td><td>m</td><td>쌍곡선법 일반식</td></tr>
<tr><td>U</td><td>침하량 기준 압밀도</td><td>무차원(%)</td><td>S<sub>t</sub>/S<sub>∞</sub></td></tr>
<tr><td>L</td><td>수준측량 편도거리</td><td>km</td><td>2022 논문 표 3</td></tr>
</table>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 형식의 2쪽 따라쓰기 PDF이다. 답안과 계측항목·계측기 표, 계산 예, 계측기 배치 모식도가 옅은 회색 글씨로 들어 있어 출력해 그대로 따라 쓸 수 있다.</p>
<h2 data-ke-size="size26">참고자료</h2>
<ul>{src}</ul>
<p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 자료 확인일은 2026년 10월 27일이다. 2022 논문은 부산항 신항 일대 준설매립 대심도 연약지반 자료에 바탕을 둔 제안이라 일반 육상 연약지반에 그대로 옮길 때는 현장 조건을 따져야 한다. KCS 11 10 15는 논문이 검토한 2018년판 내용만 옮겼고, 이후 개정 여부와 조항 번호는 국가건설기준센터 원문에서 확인하지 못했다.</p>
<p>#토목시공기술사 #연약지반 #계측관리 #지중경사계 #층별침하계 #간극수압계 #쌍곡선법 #하루한문제</p>'''

if __name__ == '__main__':
    figure(); make_pdf()
    cap_img = '직접 작성한 개념도. 성토 단면에 계측기 6종의 일반적 배치 예와 계측항목을 정리했다.'
    alt_img = '연약 점토층 위 성토 단면에 지표침하판, 층별침하계, 간극수압계, 지하수위계, 지중경사계, 지표변위말뚝을 배치한 개념도와 계측기별 계측항목 목록'
    alt_f1 = 'S_t = S_0 + t/(α + βt), t/(S_t − S_0) = α + βt, S_∞ = S_0 + 1/β'
    alt_f2 = '30/0.20 = 150, 90/0.40 = 225, β = (225 − 150)/(90 − 30) = 1.25, α = 150 − 1.25×30 = 112.5, S_∞ = 0.80 + 1/1.25 = 1.60 m, U = 1.20/1.60 = 0.75, 남은 침하 0.40 m'
    alt_gif = '가상 예시에서 성토 완료 뒤 침하 계측값 세 점과 t/(S−S0)–t 직선(β 1.25, α 112.5)을 그리고, 최종침하량 1.60 m 점근선과 90일 압밀도 75%를 보이는 도식'
    cap_f1 = '수식 1. 쌍곡선법 침하 예측식'
    cap_f2 = '수식 2. 계산 예(가상 예시)'
    cap_gif = '도식. 쌍곡선법으로 최종침하량 추정 — 학습용 가정값'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(banner_html=f'<p data-ax-attach="{BANNER}"></p>\n', img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'hyperbolic.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(banner_html=f'<p><img src="{CDN}banner.png" alt="{TITLE}" style="max-width:100%;height:auto"></p>\n',
                   img_html=b_fig(CDN + 'instruments.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'hyperbolic.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (2쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(banner_html=f'<p><img src="{BANNER}" alt="배너"></p>', img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1),
                   f2_html=b_fig(F2_NAME, alt_f2, cap_f2), gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    print(json.dumps(CALC, ensure_ascii=False))
