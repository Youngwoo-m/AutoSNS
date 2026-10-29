"""10일차 하천제방의 파괴원인과 방지대책 — 개념도·따라쓰기 PDF·티스토리/Blogger 본문을 만든다."""
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
TITLE = '[토목시공기술사] 하천제방의 파괴원인과 방지대책 | 하루 한 문제 10일차'
PDF_NAME = '10일차_하천제방파괴_답안예시_따라쓰기.pdf'
FIG_NAME = '하천제방_파괴원인과대책_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_한계동수경사.png', '수식2_계산예.png', '도식_제방파이핑검토.gif'
BANNER = 'banner.png'
CDN = 'https://geoai-na.netlify.app/civil-questions/materials/day10/'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'

# ── 계산 예(가상 예시) ───────────────────────────────────────────────
GS, E, I1, I2 = 2.65, 0.65, 0.30, 0.20         # 비중, 간극비, 대책 전·후 유출부 국부 동수경사(가정)
IC = (GS - 1) / (1 + E)
FS1, FS2 = IC / I1, IC / I2
CALC = {'i_c': round(IC, 2), 'Fs_before': round(FS1, 2), 'Fs_after': round(FS2, 2)}

# ── 개념도 (파괴원인 → 방지대책, 여유고 표) ──────────────────────────
def figure():
    im = Image.new('RGB', (1600, 1000), 'white'); dr = ImageDraw.Draw(im)
    f = lambda z: ImageFont.truetype(PRET, z)
    INK, TEAL, RED, GRAYC, SOFT, PINK = '#263746', '#176977', '#B6462F', '#7A8790', '#EAF2F3', '#FBEDE8'
    dr.text((60, 40), '하천제방 — 파괴원인과 방지대책의 짝', font=f(42), fill=INK)
    rows = [('월류', '홍수위가 둑마루를 넘음\n→ 뒷비탈부터 침식', '계획홍수위 + 여유고로\n둑마루 높이 확보'),
            ('세굴·침식', '소류력으로 비탈덮기·\n호안 유실, 기초 세굴', '호안(비탈덮기·비탈멈춤·\n밑다짐), 취약부 점검'),
            ('침투·파이핑', '침윤선 상승, 기초지반\n누수 → 토사 유출', '단면확대(제내지측), 앞비탈 피복,\n앞비탈 기슭 차수벽'),
            ('비탈면 활동', '수위 급강하·강우로\n비탈면이 미끄러짐', '비탈경사 1:3보다 완만(원칙),\n안전율 검토, 기초는 압성토'),
            ('침하·접합부', '연약지반 침하, 통문 주변\n다짐 불량·공동', '더돋기·지반개량,\n통문 주변 다짐·공동 탐사')]
    x0, y0, h = 60, 130, 132
    dr.text((x0 + 10, y0 - 4), '구분', font=f(28), fill=GRAYC)
    dr.text((x0 + 270, y0 - 4), '파괴 과정', font=f(28), fill=RED)
    dr.text((x0 + 710, y0 - 4), '방지대책', font=f(28), fill=TEAL)
    for i, (a, b, c) in enumerate(rows):
        yy = y0 + 46 + i * (h + 12)
        dr.rounded_rectangle([x0, yy, x0 + 240, yy + h], 14, fill=SOFT, outline=TEAL, width=3)
        dr.text((x0 + 20, yy + h / 2 - 18), a, font=f(30), fill=INK)
        dr.rounded_rectangle([x0 + 260, yy, x0 + 670, yy + h], 14, fill=PINK, outline=RED, width=3)
        dr.multiline_text((x0 + 280, yy + 26), b, font=f(26), fill=INK, spacing=12)
        dr.polygon([(x0 + 678, yy + h / 2 - 16), (x0 + 678, yy + h / 2 + 16), (x0 + 702, yy + h / 2)], fill=TEAL)
        dr.rounded_rectangle([x0 + 710, yy, x0 + 1160, yy + h], 14, fill=SOFT, outline=TEAL, width=3)
        dr.multiline_text((x0 + 730, yy + 26), c, font=f(26), fill=INK, spacing=12)
    # 오른쪽: 여유고 표
    rx = 1260
    dr.text((rx, 130), '계획홍수량별 여유고', font=f(30), fill=INK)
    fb = [('200 미만', '0.6'), ('200~500', '0.8'), ('500~2,000', '1.0'), ('2,000~5,000', '1.2'), ('5,000~10,000', '1.5'), ('10,000 이상', '2.0')]
    dr.text((rx, 186), 'Q (㎥/s)', font=f(24), fill=GRAYC); dr.text((rx + 200, 186), '여유고(m)', font=f(24), fill=GRAYC)
    for k, (q, v) in enumerate(fb):
        yy = 230 + k * 62
        dr.rounded_rectangle([rx - 10, yy - 8, rx + 300, yy + 46], 10, fill=SOFT if k % 2 == 0 else 'white')
        dr.text((rx, yy), q, font=f(26), fill=INK); dr.text((rx + 210, yy), v + ' 이상', font=f(26), fill=TEAL)
    dr.text((rx - 10, 620), '2012 해설서 표 8.50', font=f(22), fill=GRAYC)
    dr.text((rx - 10, 690), '파이핑 안전율', font=f(28), fill=INK)
    dr.text((rx - 10, 734), '한계동수경사법 3.0~4.0', font=f(24), fill=RED)
    dr.text((rx - 10, 770), '침투압법 2.0 이상', font=f(24), fill=RED)
    dr.text((rx - 10, 806), '(표 8.54, 최소 2가지 방법)', font=f(22), fill=GRAYC)
    dr.text((60, 930), '직접 작성한 개념도 / 근거: 하천설계기준·해설 제방 개정(안) 대비표(2009), 제방 안전점검·정밀안전진단 세부지침 해설서(2012)', font=f(23), fill=GRAYC)
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

def section(c):
    """3쪽 제방 단면 모식도(축척 없음): 여유고, 차수벽, 침투 경로, 용출."""
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(1.1)
    gy, cy, wl = 475, 580, 555
    c.line(202, gy, 605, gy)                                              # 지반선
    p = c.beginPath(); p.moveTo(250, gy); p.lineTo(355, cy); p.lineTo(445, cy); p.lineTo(560, gy); c.drawPath(p)
    c.setDash(4, 3); c.line(205, wl, 330, wl); c.setDash()                # 계획홍수위
    text(c, 207, wl + 5, '▽ 계획홍수위', 9.5)
    c.line(345, wl, 345, cy); c.line(340, wl, 350, wl); c.line(340, cy, 350, cy)
    text(c, 296, wl + 9, '여유고', 9.5)
    text(c, 382, cy + 6, '둑마루', 9.5)
    text(c, 207, gy + 8, '제외지(하천)', 9.5); text(c, 566, gy + 8, '제내지', 9.5)
    c.rect(243, gy - 55, 6, 55, stroke=1, fill=0)                         # 차수벽
    text(c, 207, gy - 72, '앞비탈 기슭 차수벽', 9.5)
    c.rect(522, gy, 34, 8, stroke=1, fill=0)                               # 뒷비탈 기슭 배수
    text(c, 470, gy + 14, '배수(드레인)', 9.5)
    c.setDash(2, 2)
    p = c.beginPath(); p.moveTo(225, gy - 8); p.lineTo(240, gy - 62); p.lineTo(255, gy - 62)
    p.lineTo(540, gy - 36); p.lineTo(572, gy - 4); c.drawPath(p); c.setDash()
    c.line(572, gy - 4, 566, gy - 12); c.line(572, gy - 4, 574, gy - 14)  # 화살촉
    text(c, 330, gy - 30, '기초지반 침투 경로(길어짐)', 9.5)
    text(c, 578, gy - 22, '용출', 9.5)
    text(c, 330, gy - 72, '※ 모식도, 축척 없음. 투수성 기초지반 가정', 9.5)

def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H))
    p1 = {
        0: ('하천제방의 파괴 원인과 방지대책', 13),
        1: ('1. 개요', 14),
        2: ('제방은 홍수가 하도 밖으로 넘치지 않도록 하천을', 12.5),
        3: ('따라 흙으로 쌓은 구조물이다. 월류·세굴·누수·', 12.5),
        4: ('비탈면활동·침하로 파괴되며, 무너지면 제내지가 잠긴다.', 12),
        5: ('2. 제방의 종류(축조 재료 기준)', 14),
        6: ('· 표준제: 토사로 쌓은 비탈면을 갖는 경사제', 12),
        7: ('· 특수제: 콘크리트·석재 등, 앞비탈 수직(45° 이상)', 12),
        8: ('3. 파괴 원인', 14),
        16: ('· 기타: 동물 구멍, 경작 훼손, 둑마루 중장비 과하중', 11.5),
        17: ('· 취약부: 하폭 급변, 만곡부 바깥, 횡단구조물,', 12),
        18: ('  교량·보 지점, 합류부, 호안 끝·재질 경계', 12),
        19: ('※ 2012 해설서의 제방파괴 요인·취약부 정리', 11),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    text(c, 132, 731, '2', 14)
    ys = [764 - 8.45 * 32.35 - i * 30 for i in range(8)]
    rule_table(c, [202, 300, 605], ys, [
        ('구분', '파괴 과정'),
        ('월류', '둑마루 넘친 물이 뒷비탈부터 침식 → 단면 유실'),
        ('세굴·침식', '소류력 → 비탈덮기·호안 유실, 기초 세굴'),
        ('침투·파이핑', '침윤선·간극수압 상승, 기초 용출·토사 유출'),
        ('비탈면 활동', '수위 급강하·강우로 함수비 상승 때 미끄러짐'),
        ('침하', '연약지반 침하 → 둑마루 낮아져 월류 위험'),
        ('구조물 접합부', '통문 주변 다짐 불량·부등침하 → 공동·누수'),
    ])
    c.showPage()
    p2 = {
        0: ('4. 방지대책', 14),
        1: ('① 월류: 계획홍수위+여유고로 둑마루 높이 확보', 12),
        2: ('   여유고 0.6m(200㎥/s 미만)~2.0m(10,000 이상)', 12),
        3: ('② 세굴: 호안(비탈덮기·비탈멈춤·밑다짐), 취약부 보강', 11.5),
        4: ('③ 제체 침투: 단면확대(제내지측 원칙), 앞비탈 피복,', 12),
        5: ('   침윤선을 제체 하부로, 침투수 신속 배수', 12),
        6: ('④ 기초 침투: 앞비탈 기슭 차수벽, 고수부 피복', 12),
        7: ('⑤ 활동: 비탈 1:3 이하 완만(원칙), 기초는 압성토', 12),
        8: ('⑥ 침하: 더돋기 우선 고려, 치환 등 지반개량', 12),
        9: ('⑦ 통문: 주변 다짐 철저, 공동은 물리탐사로 확인', 12),
        10: ('5. 안정성 검토 기준(2012 해설서)', 14),
        16: ('6. 계산 예(가상 예시) — 한계동수경사법', 14),
        17: ('i_c = (Gs-1)/(1+e) = (2.65-1)/(1+0.65) = 1.00', 12.5),
        18: ('Fs = i_c / i_exit = 1.00 / 0.30 = 3.33 (b등급 구간)', 12.5),
        19: ('차수벽 후 i_exit = 0.20 가정 → Fs = 5.00 (a등급 구간)', 12),
        20: ('※ 가상값. 등급 확정은 침투압 방법도 함께 검토', 11),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '2', 14)
    ys = [764 - 10.45 * 32.35 - i * 30 for i in range(6)]
    rule_table(c, [202, 330, 605], ys, [
        ('항목', '기준'),
        ('활동(균열 불고려)', '간극수압 불고려 2.0, 고려 1.4 이상'),
        ('활동(균열 고려)', '간극수압 불고려 1.8, 고려 1.3 이상'),
        ('파이핑①', '한계동수경사법 a 4.0 이상, b 3.0~4.0'),
        ('파이핑②', '침투압법 a 2.0 이상, b 1.8~2.0'),
    ])
    c.showPage()
    p3 = {
        0: ('7. 유지관리·점검', 14),
        1: ('· 홍수기 전후: 누수·비탈 균열·침하·동물 구멍 확인', 12),
        2: ('· 흐린 물(혼탁수) 누수는 즉시 관리주체에 통보', 12),
        3: ('· 통문 등 관통 구조물 공동: 전기비저항·탄성파 탐사', 12),
        4: ('■ 그림. 제방 단면과 대책 위치', 12.5),
        13: ('8. 결론', 14),
        14: ('제방 파괴는 월류·세굴·침투(파이핑)·활동·침하가', 12.5),
        15: ('겹쳐 일어난다. 여유고 확보, 호안, 차수·배수로', 12.5),
        16: ('침윤선과 동수경사 낮추기, 완경사 비탈과 침하 관리를', 12),
        17: ('설계에서 갖추고, 취약부와 통문 주변을 홍수기 전후로', 12),
        18: ('점검해 누수를 초기에 잡는 것이 핵심이다.', 12.5),
        19: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
        20: ('기준: 2009 개정(안)·2012 해설서, 현행 KDS 미대조', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    section(c)
    text(c, 132, 731, '2', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(3):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2026 제140회 3교시 2번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)

# ── 본문 ─────────────────────────────────────────────────────────────
Q = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq={}&brdId=Q006&gSite=Q'
Q126, Q127, Q131, Q136, Q138, Q139, Q140 = (Q.format(s) for s in (5209527, 5210073, 5212302, 5234958, 5253570, 5263570, 5274160))
STD2009 = 'https://www.codil.or.kr/filebank/files/201310/helpdesk/IN_20091102_00004697.pdf?atchFileId=IN_20091102_00004697&fileSn=0'
GUIDE2012 = 'https://www.codil.or.kr/filebank/original/MA/OTKCMA150044/OTKCMA150044.pdf'
SOURCES = [
    ('한국수자원학회 「하천설계기준·해설」 제방 부분 개정(안) 신·구 대비표(2009.7) — 23.4.5 비탈경사, 23.4.11 제방의 안정(파괴 형태, 누수·파이핑, 활동, 배수통문, 허용잔류침하량 표 23.10), 23.4.12 침투에 대한 보강공법(단면확대·차수공법). CODIL 공개 자료, 개정 "안"이며 현행판 아님', STD2009),
    ('한국시설안전공단 「안전점검 및 정밀안전진단 세부지침 해설서(제방)」 RD-12-E6-018(2012.12) — 8.1.2 용어 정의(표준제·특수제), 제방파괴 요인 및 취약부, 8.5 안전성평가(표 8.50 여유고, 표 8.51 활동 안전율, 표 8.54 누수 안전성), 8.7 보수·보강 방법. CODIL 공개 원문', GUIDE2012),
]

def body(img_html, f1_html, f2_html, gif_html, pdf_html, banner_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    return f'''{banner_html}<p>하천제방의 파괴원인과 방지대책은 2022~2026년 토목시공기술사에서 같은 뼈대로 두 번, 제방 누수·파이핑·외력·응급대책처럼 가까운 주제로 여러 번 나온 논술형 문제다. 답안은 제방의 종류, 월류·세굴·침투(파이핑)·비탈면 활동·침하·구조물 접합부로 나눈 파괴 원인, 원인과 짝을 맞춘 방지대책, 안정성 검토 기준(여유고·활동·파이핑 안전율), 유지관리 순서로 짠다. 기준값은 2009년 하천설계기준 개정(안)과 2012년 제방 안전점검 해설서에서 옮겼으며, 현행 KDS 원문과는 대조하지 못했다.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2 data-ke-size="size26">오늘의 문제</h2>
<p><strong>시험 종목: 토목시공기술사 / 과목(학습 분류): 하천·제방 / 유형: 논술형 / 관련 기출: 2026년 제140회 3교시 2번, 2022년 제126회 4교시 2번</strong></p>
<blockquote>하천제방의 파괴 원인과 방지대책에 대하여 설명하시오.</blockquote>
<p>위 문제는 2026년 제140회 3교시 2번 기출 원문이다. 2022년 제126회 4교시 2번은 「하천제방의 종류와 제방의 붕괴원인 및 방지대책을 설명하시오.」로, 제방의 종류를 함께 묻는다. 이 글의 답안은 두 문제를 모두 쓸 수 있도록 제방의 종류를 짧게 넣었다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 3분, 작성 22분, 답안지 3쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이며 공식 시험 과목명이 아니다.</p>
<h3 data-ke-size="size23">출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 하천제방의 파괴(붕괴) 원인과 대책을 묻는 문항과 가까운 문항은 다음과 같다.</p>
<ul><li>2026년 제140회 3교시 2번: <a href="{Q140}">하천제방의 파괴 원인과 방지대책에 대하여 설명하시오.</a></li>
<li>2022년 제126회 4교시 2번: <a href="{Q126}">하천제방의 종류와 제방의 붕괴원인 및 방지대책을 설명하시오.</a></li>
<li>2026년 제140회 4교시 2번: <a href="{Q140}">호우기 하천범람에 따른 제방의 누수원인 및 방지대책</a></li>
<li>2026년 제138회 4교시 5번: <a href="{Q138}">하천제방의 누수방지 공법</a></li>
<li>2023년 제131회 4교시 6번: <a href="{Q131}">홍수 시 하천제방에 작용하는 외력의 종류와 피해 형태·원인</a>, 3교시 1번: <a href="{Q131}">하천제방 파괴 시 응급대책공법</a></li>
<li>단답형: 2022년 제127회 1교시 5번 <a href="{Q127}">제방의 파이핑 검토방법</a>, 2025년 제136회 1교시 8번 <a href="{Q136}">대규격제방</a></li></ul>
<p>문항 제목은 줄여 적었으며 정확한 표현은 Q-net 문제지에서 확인한다. 같은 465문항에서 제방의 파괴·누수·파이핑을 다룬 문항이 5년 동안 여러 번 나왔고 2026년에만 세 번 보여 이번 회차로 골랐다. 이 횟수는 문제 제목을 대조해 센 것이며 공식 출제 비중이 아니다. 앞서 쓴 9편(흙의 다짐, 서중·한중콘크리트, 흙막이 계측, 온도균열, SPT N값, 말뚝 재하시험, 거푸집 해체, 숏크리트 리바운드)과 겹치지 않는 하천 분야의 첫 글이다.</p>
<h2 data-ke-size="size26">답안 목차</h2>
<p>1. 개요 → 2. 제방의 종류 → 3. 파괴 원인 → 4. 방지대책 → 5. 안정성 검토 기준 → 6. 계산 예 → 7. 유지관리·점검 → 8. 결론</p>
<h2 data-ke-size="size26">답안예시</h2>
<h3 data-ke-size="size23">1. 개요</h3>
<p>제방은 유수가 하도 밖으로 넘치지 않게 하천을 따라 토사 등으로 쌓은 구조물이다(2012 해설서 8.1.2). 하천설계기준·해설 개정(안)(2009) 23.4.11은 제방의 파괴가 월류, 세굴, 누수, 비탈면활동, 침하 등으로 생길 수 있다고 적고, 설계 때 누수·비탈면활동·침하에 대한 안정성 검토를 반드시 하도록 한다. 제방이 무너지면 제내지(제방 안쪽의 마을·농경지)가 잠기므로, 원인별로 설계·시공·유지관리 대책을 나눠 쓰는 것이 답안의 골격이다.</p>
<h3 data-ke-size="size23">2. 제방의 종류</h3>
<p>2012 해설서는 축조 재료에 따라 제방을 둘로 나눈다. <strong>표준제</strong>는 토사로 쌓은 비탈면을 갖는 경사제이고, <strong>특수제</strong>는 특수한 목적으로 토사와 함께 콘크리트·석재 등으로 쌓으며 석축·옹벽·말뚝 등으로 앞비탈이 수직(경사 45° 이상)인 제방이다. 호안은 제방 앞비탈이나 하안을 보호하는 구조물로 비탈덮기, 기초(비탈멈춤), 밑다짐으로 이루어진다. 제126회처럼 종류를 함께 묻는 문제에서는 이 구분을 먼저 쓰고 넘어간다.</p>
<h3 data-ke-size="size23">3. 파괴 원인</h3>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>구분</th><th>파괴 과정</th><th>근거</th></tr>
<tr><td>월류</td><td>월류수의 소류력으로 제체 표면·비탈면이 침식되고(2012 해설서는 보통 제내측 비탈면부터 유실된다고 설명), 제체 함수비가 늘어 강도가 떨어지며 무너진다.</td><td>2012 해설서 제방파괴 요인 ①</td></tr>
<tr><td>세굴·침식</td><td>홍수 때 소류력으로 비탈덮기가 파손·유실되고 기초부가 세굴되며, 호안이 무너지면 제체가 유실된다.</td><td>같은 곳 ②</td></tr>
<tr><td>침투(누수)·파이핑</td><td>강우와 하천수가 스며 간극수압과 침윤면이 오르고, 투수성 기초지반에서는 침투압이 커져 제내지 쪽으로 물이 솟는다. 파이핑으로 토사가 빠지면 누수량이 늘어 파괴로 이어진다.</td><td>같은 곳 ③, 2009 개정(안) 23.4.11(2)</td></tr>
<tr><td>비탈면 활동</td><td>하천 수위가 급히 내려갈 때나 강우로 제체 함수비가 오를 때 비탈면이 미끄러진다. 활동은 외부하중 증가, 전단강도 약화, 침투수, 지반침하·측방유동으로도 생긴다.</td><td>2012 해설서 8.5(제방이 만족할 조건 ③, 활동 해설)</td></tr>
<tr><td>침하</td><td>연약지반 위 제방은 시공 뒤에도 침하가 이어져 둑마루가 낮아진다. 그만큼 여유고가 줄어 월류 위험이 커진다(필자 해석).</td><td>2009 개정(안) 23.4.11(5), 표 23.10</td></tr>
<tr><td>횡단구조물 접합부</td><td>배수통문 같은 콘크리트 구조물은 제체 토사와 무게·강성이 달라 다짐 밀착이 어렵고, 말뚝기초가 있으면 구조물과 주변 흙의 침하 차이로 공동이 생겨 제체누수의 원인이 된다.</td><td>2009 개정(안) 23.4.11(2)⑦⑧, 2012 해설서 ④</td></tr>
<tr><td>기타</td><td>동식물 구멍, 경작 등 인위적 훼손으로 단면이 부족해짐, 둑마루를 지나는 중장비 과하중</td><td>2012 해설서 ⑤</td></tr>
</table>
<p>2012 해설서는 하폭이 갑자기 넓어지거나 좁아지는 곳, 만곡부 바깥쪽, 횡단구조물·교량·보 지점, 합류부, 호안 끝과 재질이 바뀌는 곳 같은 흐름이 불연속한 지점을 손상 확률이 높은 취약부로 든다. 같은 해설서는 누수를 "제방파괴의 가장 큰 요소 중의 하나"라고 적었다. 답안에서 침투·파이핑 항목을 조금 더 길게 쓰는 근거로 삼을 수 있다.</p>
<h3 data-ke-size="size23">4. 방지대책</h3>
{img_html}
<ul><li><strong>월류</strong> — 계획홍수위에 여유고를 더한 높이로 둑마루를 확보한다. 2012 해설서 표 8.50은 계획홍수량 200 ㎥/s 미만에서 0.6 m 이상, 10,000 ㎥/s 이상에서 2.0 m 이상까지 여유고를 계획홍수량에 따라 정한다. 침하가 예상되면 여유고가 줄지 않도록 아래의 침하 대책과 함께 본다.</li>
<li><strong>세굴·침식</strong> — 호안(비탈덮기·비탈멈춤·밑다짐)으로 비탈면과 기초를 보호하고, 만곡부 바깥쪽·교량 지점 같은 취약부를 우선 점검·보강한다.</li>
<li><strong>제체 침투</strong> — 2009 개정(안)은 제체누수의 결정적 요인이 침윤선이므로 침윤선을 낮춰 제체 하부에 오게 하라고 적는다. 공법으로는 단면확대공법과 앞비탈 피복공법이 있다. 단면확대공법은 2009 개정(안)이 제내지측 확장을 원칙으로 하고, 지형조건 등으로 불가피하게 제외지측을 보강할 때는 수리적 안정성을 유지하도록 한다. 2012 해설서는 제외지측·제내지측·병용에 따라 기능이 달라 재료 선정에 유의하라고 적는다(제외지측은 불투수성, 제내지측은 투수성이 큰 재료). 앞비탈 피복공법은 투수성이 큰 제체에서 고수위 때 앞비탈로 들어오는 침투를 막으려고 불투수성 흙이나 차수시트로 앞비탈을 덮는 공법이다. 2012 해설서는 제체에 들어온 물을 신속하게 배수한다는 원칙도 함께 든다. 뒷비탈 기슭 배수(드레인)는 이 원칙을 공법으로 옮긴 것으로 보았다(필자 해석, 해설서 공법 목록에는 없음).</li>
<li><strong>기초지반 침투(파이핑)</strong> — 차수공법은 앞비탈 기슭, 둑마루, 뒷비탈 소단 부근의 기초지반에 차수벽(시트파일, 연속지중벽, 그라우트)을 넣어 침투 수량과 수압을 줄인다. 투수층이 두꺼우면 근입깊이가 깊어지므로 다른 공법과 병용을 검토한다. 고수부 피복공법은 제외지 쪽 고수부 표층을 불투수성 재료(투수계수 1×10<sup>-5</sup> cm/s 이하)로 덮어 침투 경로를 늘린다(2012 해설서 8.7).</li>
<li><strong>비탈면 활동</strong> — 비탈경사는 제방고와 제내지반고의 차이가 0.6 m 미만인 구간을 빼고 1:3 또는 그보다 완만하게 하는 것이 원칙이며, 완만하게 하느라 여유고가 부족해져서는 안 된다(2009 개정(안) 23.4.5). 계획홍수위와 수위 급강하를 고려한 침투해석의 침윤면으로 앞·뒷비탈 안전율을 구한다. 기초지반 쪽 활동에는 압성토·완경사면공법이 기초연약지반 보강 공법으로 제시되어 있다(2012 해설서 8.7).</li>
<li><strong>침하</strong> — 2009 개정(안) 23.4.11은 연약지반 축제로 침하가 생기면 더돋기를 우선적으로 고려하고, 지하수위 저하·압밀 촉진·연약토 치환 같은 지반개량공법을 쓰도록 한다. 약액주입 같은 고결공법은 2012 해설서 8.7의 기초연약지반 보강 공법에 나온다. 2009 개정(안) 표 23.10(허용 잔류침하량 기준, 둑마루 기준)은 일반 제방 30 cm 이하, 도로겸용 제방과 배수구조물 설치 제방 10 cm 이하로 제시했으며, 표 안의 표기는 '총 침하기준'이라 적혀 있어 잔류침하량과의 관계는 원문에서 다시 확인할 필요가 있다. 연약지반 처리에 쓰는 모래·쇄석 같은 수평배수재가 홍수 때 침투유로가 될 수 있으므로 그 대책도 함께 세운다.</li>
<li><strong>횡단구조물 주변</strong> — 통문 주변은 다짐 밀착이 어려운 부위이므로 다짐 관리를 강화한다(필자 설명, 출처는 원인만 적음). 2009 개정(안)은 유지·보수 때 지반의 부등침하, 콘크리트 노후화·균열, 이음새 변형을 조사하도록 한다. 관통 구조물 주변 공동은 전기비저항·탄성파 같은 물리탐사로 확인한다(2012 해설서 점검 항목).</li></ul>
<h3 data-ke-size="size23">5. 안정성 검토 기준</h3>
<p>2012 해설서는 제방이 만족할 조건으로 ① 홍수 때 월류하지 않을 것, ② 제체가 세굴되지 않을 것, ③ 수위 급강하 때 비탈면 활동에 안전할 것, ④ 연약지반이면 파괴와 침하에 안전할 것, ⑤ 누수·파이핑에 안전할 것, ⑥ 강우로 함수비가 올라도 비탈면 붕괴에 안전할 것을 든다. 안전율 기준은 다음과 같다.</p>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>검토 항목</th><th>조건</th><th>기준</th><th>근거</th></tr>
<tr><td rowspan="2">제체 활동(원호활동)</td><td>인장균열 불고려</td><td>간극수압 불고려 2.0 이상, 고려 1.4 이상</td><td rowspan="2">2012 해설서 표 8.51</td></tr>
<tr><td>인장균열 고려</td><td>간극수압 불고려 1.8 이상, 고려 1.3 이상</td></tr>
<tr><td rowspan="2">누수(파이핑)</td><td>한계동수경사 방법</td><td>평가 a등급 4.0 이상, b등급 3.0 이상~4.0 미만(주석: 기준안전율 3.0~4.0)</td><td rowspan="2">2012 해설서 표 8.54(평가등급표), 최소 2가지 방법으로 검토하며 등급은 두 방법을 짝으로 정함</td></tr>
<tr><td>침투압 방법</td><td>평가 a등급 2.0 이상, b등급 1.8~2.0 미만(주석: 허용안전율 2.0 이상)</td></tr>
</table>
<p>이 표는 2012년 해설서의 안전성평가 기준이다. 해설서는 누수 해석 절차와 안전율 기준을 "하천설계기준·해설"에 따르도록 적고 있으므로, 실제 설계·진단에서는 현행 KDS 하천설계기준과 해당 사업의 과업지시서를 먼저 확인한다.</p>
<h3 data-ke-size="size23">6. 계산 예 (가상 예시)</h3>
<p>아래 비중·간극비·유출부 동수경사는 설명을 위해 만든 가상 예시이며 실측값이나 공식 기준값이 아니다. 유출부 국부 동수경사 i<sub>exit</sub>는 침투해석으로 얻었다고 가정한다. 한계동수경사 식은 토질역학의 일반식이며, 해설서 표 8.54의 등급 구간과 비교하는 데만 쓴다.</p>
{f1_html}
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>항목</th><th>계산</th><th>결과</th></tr>
<tr><td>한계동수경사</td><td>(2.65 − 1) / (1 + 0.65) = 1.65 / 1.65</td><td>1.00</td></tr>
<tr><td>대책 전 안전율</td><td>1.00 / 0.30</td><td>3.33 (한계동수경사 방법만 보면 b등급 구간, 3.0 이상 4.0 미만)</td></tr>
<tr><td>차수벽 설치 후(i<sub>exit</sub> 0.20 가정)</td><td>1.00 / 0.20</td><td>5.00 (한계동수경사 방법만 보면 a등급 구간, 4.0 이상)</td></tr>
</table>
{f2_html}
<p>표 8.54의 등급은 점검·진단에서 쓰는 평가 점수(a=5점, b=4점 등)이며, 한 등급은 한계동수경사 방법과 침투압 방법의 구간을 짝으로 정한다. 이 계산 예는 한계동수경사 방법 하나만 계산했으므로 등급을 확정하려면 침투압 방법(a 2.0 이상, b 1.8~2.0)도 함께 검토해야 한다. 또 주석의 기준안전율이 3.0~4.0이라는 범위로 적혀 있어, 그 안의 어느 값을 합격선으로 볼지는 해설서 원문만으로 정해지지 않는다. 이런 한계를 두고 보면, 대책 전 3.33은 한계동수경사 방법의 b등급 구간에 해당한다. 앞비탈 기슭 차수벽으로 침투 경로가 길어져 유출부 동수경사가 0.20으로 낮아졌다고 가정하면 안전율은 5.00이 된다. 차수벽이 동수경사를 얼마나 낮추는지는 현장 지반과 근입깊이에 따라 달라지므로 실제로는 침투해석으로 다시 구한다. 아래 도식은 같은 가상 조건을 그림으로 옮긴 것이다.</p>
{gif_html}
<h3 data-ke-size="size23">7. 유지관리·점검</h3>
<p>홍수기 전후에 누수, 비탈면 균열·배부름, 침하, 동식물 구멍을 확인하고 취약부를 우선 본다. 2012 해설서는 누수가 발견되면, 특히 흐린 물(혼탁수)이 나오면 즉시 관리주체에 통보하고 정밀안전진단 필요성을 판단하도록 한다. 흙 알갱이가 함께 빠져나온다는 신호로 읽히기 때문이다(필자 해석). 통문 주변 공동처럼 눈에 보이지 않는 결함은 물리탐사로 확인한다.</p>
<h3 data-ke-size="size23">8. 결론</h3>
<p>제방 파괴는 월류·세굴·침투(파이핑)·비탈면 활동·침하가 겹쳐 일어난다. 여유고 확보와 호안, 차수·배수로 침윤선과 동수경사를 낮추기, 완경사 비탈과 침하 관리를 설계에서 갖추고, 취약부와 통문 주변을 홍수기 전후로 점검해 누수를 초기에 잡는 것이 방지대책의 골격이다.</p>
<h2 data-ke-size="size26">핵심 암기어</h2>
<p>월류·세굴·침투(파이핑)·활동·침하 · 여유고 0.6~2.0 m(계획홍수량별) · 침윤선 낮추기·단면확대(제내지측) · 앞비탈 기슭 차수벽 · 비탈경사 1:3보다 완만(원칙) · 혼탁수 누수 즉시 통보</p>
<h2 data-ke-size="size26">답안 자가점검</h2>
<ul><li>제방의 정의와 파괴 시 피해를 개요에 썼는가?</li>
<li>표준제·특수제 구분을 썼는가(제126회형 문제 대비)?</li>
<li>파괴 원인을 월류·세굴·침투(파이핑)·활동·침하·구조물 접합부로 나눴는가?</li>
<li>대책이 원인과 짝을 이루는가(여유고, 호안, 차수벽·단면확대, 완경사, 더돋기 등)?</li>
<li>활동·파이핑 안전율 기준을 출처와 함께 썼는가?</li>
<li>유지관리(취약부 점검, 혼탁수 누수 통보)를 결론 전에 넣었는가?</li></ul>
<h2 data-ke-size="size26">기호·단위 정리</h2>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>기호</th><th>뜻</th><th>단위</th><th>출처</th></tr>
<tr><td>i<sub>c</sub></td><td>한계동수경사</td><td>무차원</td><td>토질역학 일반식</td></tr>
<tr><td>G<sub>s</sub></td><td>흙 입자의 비중</td><td>무차원</td><td>토질역학 일반식</td></tr>
<tr><td>e</td><td>간극비</td><td>무차원</td><td>토질역학 일반식</td></tr>
<tr><td>i<sub>exit</sub></td><td>유출부(제내지 비탈끝) 국부 동수경사</td><td>무차원</td><td>침투해석 결과로 얻는 값(이 글은 가정값)</td></tr>
<tr><td>F<sub>s</sub></td><td>파이핑 안전율(한계동수경사 방법)</td><td>무차원</td><td>2012 해설서 표 8.54 기준과 비교</td></tr>
<tr><td>Q</td><td>계획홍수량</td><td>㎥/s</td><td>2012 해설서 표 8.50</td></tr>
</table>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 형식의 3쪽 따라쓰기 PDF이다. 답안과 파괴 원인 표, 안전율 표, 제방 단면 모식도가 옅은 회색 글씨로 들어 있어 출력해 그대로 따라 쓸 수 있다.</p>
<h2 data-ke-size="size26">참고자료</h2>
<ul>{src}</ul>
<p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 자료 확인일은 2026년 10월 26일이다. 두 자료 모두 2009년·2012년에 나온 오래된 자료이고, 2009년 자료는 확정판이 아닌 개정(안) 대비표다. 하천설계기준은 이후 KDS 51(하천) 체계로 옮겨졌으나 현행 KDS 원문은 국가건설기준센터에서 열지 못해 조항 번호와 수치를 대조하지 못했다. 실제 설계·진단에 쓸 때는 현행 KDS와 제방 안전점검·진단 세부지침을 확인한다.</p>
<p>#토목시공기술사 #하천제방 #제방파괴 #파이핑 #여유고 #차수벽 #기술사답안 #하루한문제</p>'''

if __name__ == '__main__':
    figure(); make_pdf()
    cap_img = '직접 작성한 개념도. 파괴 원인과 방지대책의 짝, 계획홍수량별 여유고와 파이핑 안전율을 정리했다.'
    alt_img = '하천제방 파괴 원인(월류, 세굴·침식, 침투·파이핑, 비탈면 활동, 침하·접합부)과 방지대책을 짝지은 표, 계획홍수량별 여유고 0.6~2.0 m 표'
    alt_f1 = 'i_c = (G_s − 1)/(1 + e), F_s = i_c / i_exit'
    alt_f2 = 'i_c = (2.65 − 1)/(1 + 0.65) = 1.00, F_s = 1.00/0.30 = 3.33 (3.0 이상 4.0 미만), F_s = 1.00/0.20 = 5.00 (4.0 이상)'
    alt_gif = '가상 예시에서 홍수위가 오르며 기초지반 침투가 제내지 비탈끝에서 솟아 유출부 동수경사 0.30, 안전율 3.33이 되고, 앞비탈 기슭 차수벽으로 침투 경로가 길어져 동수경사 0.20, 안전율 5.00이 되는 제방 단면 도식'
    alt_banner = TITLE
    cap_f1 = '수식 1. 한계동수경사와 파이핑 안전율(한계동수경사 방법)'
    cap_f2 = '수식 2. 계산 예(가상 예시)'
    cap_gif = '도식. 제방 기초지반 침투와 차수벽 효과 — 학습용 가정값'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(banner_html=f'<p data-ax-attach="{BANNER}"></p>\n', img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'piping.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(banner_html=f'<p><img src="{CDN}banner.png" alt="{alt_banner}" style="max-width:100%;height:auto"></p>\n',
                   img_html=b_fig(CDN + 'levee-failure.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'piping.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (3쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(banner_html=f'<p><img src="{BANNER}" alt="배너"></p>', img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1),
                   f2_html=b_fig(F2_NAME, alt_f2, cap_f2), gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    print(json.dumps(CALC, ensure_ascii=False))
