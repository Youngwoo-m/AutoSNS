"""9일차 숏크리트 리바운드 발생원인과 저감대책 — 개념도·따라쓰기 PDF·티스토리/Blogger 본문을 만든다."""
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
TITLE = '[토목시공기술사] 숏크리트 리바운드 발생원인과 저감대책 | 하루 한 문제 9일차'
PDF_NAME = '09일차_숏크리트리바운드_답안예시_따라쓰기.pdf'
FIG_NAME = '숏크리트리바운드_원인과대책_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_반발률.png', '수식2_계산예.png', '도식_반발률과_분사량.gif'
BANNER = 'banner.png'
CDN = 'https://geoai-na.web.app/civil-questions/materials/day09/'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'

# ── 계산 예(가상 예시) ───────────────────────────────────────────────
V1, RHO, R1 = 5.0, 2300, 1380                 # 분사 체적 m³, 단위질량 kg/m³, 수거 반발재 kg
S1 = V1 * RHO
RR1 = R1 / S1 * 100
NEED = 220.0                                  # 부착 소요 체적 m³
RR_A, RR_B = 16.8, 9.8                        # 논문 표 9 일반 습식(급결제 4 %, 8 %)
VA, VB = NEED / (1 - RR_A / 100), NEED / (1 - RR_B / 100)
CALC = {'S_kg': S1, 'RR_pct': round(RR1, 1), 'Y_kg': S1 - R1, 'Y_m3': round((S1 - R1) / RHO, 2),
        'V_shot_16.8': round(VA, 1), 'V_shot_9.8': round(VB, 1), 'diff_m3': round(VA - VB, 1),
        'rebound_16.8_m3': round(VA - NEED, 1), 'rebound_9.8_m3': round(VB - NEED, 1)}

# ── 개념도 (원인 → 대책, 노즐 자세) ──────────────────────────────────
def figure():
    im = Image.new('RGB', (1600, 1000), 'white'); dr = ImageDraw.Draw(im)
    f = lambda z: ImageFont.truetype(PRET, z)
    INK, TEAL, RED, GRAYC, SOFT, PINK = '#263746', '#176977', '#B6462F', '#7A8790', '#EAF2F3', '#FBEDE8'
    dr.text((60, 40), '숏크리트 리바운드 — 발생원인과 저감대책의 짝', font=f(42), fill=INK)
    rows = [('재료·배합', '급결제 함량 부족,\n미분 부족·굵은골재 큼(해석)', '급결제량 시험배합으로 결정,\n미분 보충·골재 최대치수 관리'),
            ('타설 방법', '노즐 비스듬·거리 부적정,\n압력·송출 불균일', '노즐 면에 직각, 거리 약 1 m(KCS),\n압력·송출량 일정 유지'),
            ('시공 순서·두께', '첫 층(임계두께 전),\n하부→상부 미준수, 1회 두께 과다', '하부→상부, 강지보재 먼저,\n한 번에 두껍게 쏘지 않음'),
            ('시공면', '용출수, 뜬돌·이물질,\n강지보재·철망 뒤', '용출수 처리 후 타설,\n뜬돌 제거, 철망 밀착 고정'),
            ('공법 선택', '건식 공법', '습식 공법,\n로봇 타설기(해석)')]
    x0, y0, h = 60, 130, 132
    dr.text((x0 + 10, y0 - 4), '구분', font=f(28), fill=GRAYC)
    dr.text((x0 + 280, y0 - 4), '리바운드를 늘리는 원인', font=f(28), fill=RED)
    dr.text((x0 + 720, y0 - 4), '저감대책', font=f(28), fill=TEAL)
    for i, (a, b, c) in enumerate(rows):
        yy = y0 + 46 + i * (h + 12)
        dr.rounded_rectangle([x0, yy, x0 + 250, yy + h], 14, fill=SOFT, outline=TEAL, width=3)
        dr.text((x0 + 20, yy + h / 2 - 18), a, font=f(30), fill=INK)
        dr.rounded_rectangle([x0 + 270, yy, x0 + 680, yy + h], 14, fill=PINK, outline=RED, width=3)
        dr.multiline_text((x0 + 290, yy + 22), b, font=f(26), fill=INK, spacing=12)
        dr.polygon([(x0 + 688, yy + h / 2 - 16), (x0 + 688, yy + h / 2 + 16), (x0 + 712, yy + h / 2)], fill=TEAL)
        dr.rounded_rectangle([x0 + 720, yy, x0 + 1150, yy + h], 14, fill=SOFT, outline=TEAL, width=3)
        dr.multiline_text((x0 + 740, yy + 22), c, font=f(26), fill=INK, spacing=12)
    # 오른쪽: 노즐 자세 그림
    rx = 1250
    dr.text((rx, 130), '노즐 자세', font=f(32), fill=INK)
    dr.rectangle([rx + 230, 200, rx + 270, 620], fill='#B9B2A6')            # 굴착면
    dr.text((rx + 214, 630), '굴착면', font=f(24), fill=GRAYC)
    dr.rectangle([rx + 20, 390, rx + 100, 430], fill=TEAL)                  # 노즐
    dr.line([rx + 100, 410, rx + 225, 410], fill=TEAL, width=6)
    dr.polygon([(rx + 225, 398), (rx + 225, 422), (rx + 240, 410)], fill=TEAL)
    dr.line([rx + 100, 470, rx + 230, 470], fill=INK, width=2)
    dr.text((rx + 92, 478), '약 1 m(KCS)', font=f(22), fill=INK)
    dr.text((rx + 20, 340), '직각(90°)', font=f(26), fill=TEAL)
    for k in range(6):                                                       # 반발재
        dr.ellipse([rx + 120 + k * 9, 650 + (k % 3) * 18, rx + 134 + k * 9, 664 + (k % 3) * 18], fill=RED)
    dr.text((rx - 10, 720), '바닥의 반발재 수거·계량', font=f(24), fill=RED)
    dr.text((rx - 10, 756), '→ 반발률 RR(%) 산출', font=f(24), fill=RED)
    dr.text((60, 930), '직접 작성한 개념도 / 근거: 터널표준시방서(2015) 5-3, KCS 27 30 00:2023 발췌, 전준태 외(2012) — 미분·골재·로봇은 필자 해석', font=f(23), fill=GRAYC)
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

def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H))
    p1 = {
        0: ('숏크리트의 리바운드 발생원인 및 저감대책', 13),
        1: ('1. 개요', 14),
        2: ('리바운드는 뿜어붙인 숏크리트가 시공면에 붙지 않고', 12.5),
        3: ('튕겨 떨어지는 현상이다. 재료 손실·공기 지연·반발재', 12.5),
        4: ('처리비를 늘리고, 섞여 들면 품질을 떨어뜨린다.', 12.5),
        5: ('2. 반발률(RR) — 바닥 반발재를 수거·계량', 14),
        6: ('RR(%) = 반발재 질량 / 분사 총질량 × 100', 12.5),
        7: ('· 첫 층(임계두께 형성 전)에 높고 이후 줄어든다', 12),
        8: ('3. 발생원인', 14),
        14: ('※ 건식이 습식보다 반발률이 크다(전준태 외 2012)', 11.5),
        15: ('4. 저감대책', 14),
        16: ('① 습식 공법 채택, 급결제량은 시험배합으로 결정', 12),
        17: ('② 노즐은 면에 직각, 거리 약 1m(KCS), 송출 일정', 12),
        18: ('③ 하부→상부, 강지보재 먼저, 한 번에 두껍게 X', 12),
        19: ('④ 용출수 처리 후 타설, 뜬돌 제거, 철망 고정', 12),
        20: ('⑤ 미분·고분말 시멘트 등 부착성 좋은 배합', 12),
    }
    for r, (s, z) in p1.items():
        line(c, r, s, z)
    text(c, 132, 731, '7', 14)
    ys = [764 - 8.45 * 32.35 - i * 30 for i in range(6)]
    rule_table(c, [202, 290, 605], ys, [
        ('구분', '원인'),
        ('재료·배합', '급결제 함량 부족, (해석) 미분 부족·골재 큼'),
        ('타설 방법', '노즐 비스듬·거리 부적정, 압력·송출 불균일'),
        ('순서·두께', '첫 층, 하부→상부 미준수, 1회 두께 과다'),
        ('시공면', '용출수, 뜬돌·이물질, 강지보재·철망 뒤'),
    ])
    c.showPage()
    p2 = {
        0: ('5. 반발재 처리와 품질관리', 14),
        1: ('· 반발재는 굳기 전에 모두 제거, 숏크리트에 혼입 금지', 11.5),
        2: ('· 버력과 선별 분리 → 폐기물관리법에 따라 보관·처리', 12),
        3: ('· 매 타설 시 부착·반발·분진 관찰, 반발률 측정', 12),
        4: ('· 공시체 몰드 70° 경사(반발재 유출), 강도·두께 관리', 12),
        5: ('6. 계산 예(가상 예시)', 14),
        6: ('분사 5.0m³ × 2,300kg/m³ = 11,500kg', 12.5),
        7: ('반발재 1,380kg → RR = 1,380/11,500 × 100 = 12.0%', 12.5),
        8: ('부착 소요 220m³: RR 16.8% → 220/0.832 = 264.4m³', 12.5),
        9: ('              RR 9.8% → 220/0.902 = 243.9m³', 12.5),
        10: ('→ 분사량 20.5m³ 감소(반발재 44.4 → 23.9m³)', 12.5),
        11: ('※ 16.8·9.8%는 논문의 급결제 4·8% 실측값 인용', 11.5),
        12: ('※ 반발재와 분사재 단위질량이 같다고 가정', 11.5),
        13: ('7. 결론', 14),
        14: ('리바운드는 0으로 만들 수 없으므로 반발률을 정기', 12.5),
        15: ('측정해 관리값으로 삼는다. 습식·적정 급결제·노즐', 12.5),
        16: ('직각 1m·하부→상부 순서가 저감의 핵심이며, 반발재는', 12.5),
        17: ('굳기 전 제거해 품질과 폐기물 처리를 함께 관리한다.', 12.5),
        20: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '7', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(2):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2026 제140회 1교시 7번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)

# ── 본문 ─────────────────────────────────────────────────────────────
Q = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq={}&brdId=Q006&gSite=Q'
Q126, Q129, Q133, Q134, Q135, Q140 = (Q.format(s) for s in (5209527, 5211642, 5213322, 5213590, 5226372, 5274160))
SPEC2015 = 'https://www.codil.or.kr/filebank/moctroadguide/LS/CIKCLS126060/CIKCLS126060.pdf'
PAPER2012 = 'https://www.koreascience.or.kr/article/JAKO201212049739927.pdf'
PAPER2015 = 'https://koreascience.kr/article/CFKO201526857080028.pdf'
KCS_SUM = 'https://nogada.kwoody01.com/409/'
SOURCES = [
    ('국토교통부 「터널표준시방서」(2015) 5-3 숏크리트 — 2.1.1·2.1.4(성능·강도), 3.1·3.2(시공, 노즐 방향·하부→상부·반발재 제거), 3.3(분진 및 반발량 처리), 3.6(현장 품질관리, 표 5-3.3, 3.6.12 반발률 측정). CODIL 공개 원문', SPEC2015),
    ('KCS 27 30 00:2023 터널 지보재 — 2.1.2, 3.3.2(노즐 방향·거리 1 m 정도, 하부→상부, 반발재 제거), 3.6.2(12) 반발률 측정. 국가건설기준센터 원문을 열지 못해 제3자 발췌 페이지(건설 다모아)로 확인, 공식 원문 아님', KCS_SUM),
    ('전준태·박홍태·이양규(2012) 「급결제 함유량에 따른 습식 Shotcrete 리바운드 감소량에 대한 실험적 연구」, 대한토목학회논문집 32(6D), 615~622쪽 — 반발률 식, 표 9·10, 철도터널 현장 1개소 시공 자료', PAPER2012),
    ('김영선 외(2015) 「숏크리트 리바운드율에 미치는 시멘트 분말도 영향에 관한 실험적 연구」, 한국건축시공학회 학술발표대회 논문집 — 고분말 시멘트의 리바운드율 저감', PAPER2015),
]

def body(img_html, f1_html, f2_html, gif_html, pdf_html, banner_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    return f'''{banner_html}<p>숏크리트 리바운드는 2022~2026년 토목시공기술사 1교시 단답형에서 같은 주제로 세 번 나온 문제다. 답안은 반발률을 정의하는 식 하나, 재료·배합과 타설 방법·순서·시공면으로 나눈 원인, 원인과 짝을 맞춘 저감대책, 반발재 처리와 측정 방법으로 짠다. 터널표준시방서(2015)는 반발률의 상한값을 정하지 않고(KCS 27 30 00은 확인한 발췌본 기준으로 같다) 측정 방법과 시공 원칙을 정하므로, 수치는 출처를 밝혀 실측 사례로만 쓴다.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.web.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2 data-ke-size="size26">오늘의 문제</h2>
<p><strong>시험 종목: 토목시공기술사 / 과목(학습 분류): 터널(숏크리트) / 유형: 단답형 / 관련 기출: 2026년 제140회 1교시 7번, 2024년 제134회 1교시 9번, 2022년 제126회 1교시 7번</strong></p>
<blockquote>숏크리트의 리바운드 발생원인 및 저감대책</blockquote>
<p>위 문제는 2026년 제140회 1교시 7번 기출 원문이다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 1분, 작성 8분, 답안지 1~2쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이며 공식 시험 과목명이 아니다.</p>
<h3 data-ke-size="size23">출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항에서 숏크리트 리바운드를 직접 묻는 문항은 다음 3건이며 모두 1교시 단답형이다.</p>
<ul><li>2022년 제126회 1교시 7번: <a href="{Q126}">숏크리트 리바운드(NATM)</a></li>
<li>2024년 제134회 1교시 9번: <a href="{Q134}">숏크리트의 리바운드(Rebound) 최소화 방안</a></li>
<li>2026년 제140회 1교시 7번: <a href="{Q140}">숏크리트의 리바운드 발생원인 및 저감대책</a></li></ul>
<p>숏크리트 자체를 묻는 단답형도 2023년 제129회 1교시 11번 <a href="{Q129}">숏크리트(Shotcrete) 시공관리</a>, 2024년 제133회 1교시 5번 <a href="{Q133}">숏크리트의 응력측정</a>, 2025년 제135회 1교시 2번 <a href="{Q135}">터널공사의 숏크리트(Shotcrete)</a>로 세 번 더 있다. 같은 465문항(단답형 195문항)에서 리바운드라는 같은 주제가 5년 동안 세 번 출제되어 이번 회차로 골랐다. 이 횟수는 문제 제목을 대조해 센 것이며 공식 출제 비중이 아니다. 앞서 쓴 8편(흙의 다짐, 서중·한중콘크리트, 흙막이 계측, 온도균열, SPT N값, 말뚝 재하시험, 거푸집 해체)과 겹치지 않는 터널 분야의 첫 글이다.</p>
<h2 data-ke-size="size26">답안 목차</h2>
<p>1. 개요 → 2. 반발률(정의·측정) → 3. 발생원인 → 4. 저감대책 → 5. 반발재 처리와 품질관리 → 6. 계산 예 → 7. 결론</p>
<h2 data-ke-size="size26">답안예시</h2>
<h3 data-ke-size="size23">1. 개요</h3>
<p>리바운드(rebound)는 뿜어붙인 숏크리트가 굴착면이나 먼저 친 숏크리트 면에 붙지 않고 튕겨 바닥에 떨어지는 현상이다. 적은 양은 공법상 피할 수 없지만, 많아지면 재료비와 타설 시간이 늘고 반발재를 치우는 비용이 생긴다(전준태 외, 2012). 시방서는 반발재가 숏크리트에 혼합되지 않도록 모두, 굳기 전에 제거하도록 한다.</p>
<h3 data-ke-size="size23">2. 반발률 — 정의와 측정</h3>
{f1_html}
<p>반발률 RR은 바닥에 떨어진 반발재 질량 R<sub>sum</sub>을 분사한 숏크리트 총질량 S<sub>sum</sub>으로 나눈 백분율이다. 터널표준시방서(2015) 3.6.12와 KCS 27 30 00:2023 3.6.2(12)는 현장에서 숏크리트를 타설하고 바닥에 떨어진 반발재를 수거·계량해 반발률을 산출하도록 한다. 전준태 외(2012)는 터널 바닥에 시트를 깔고 숏크리트 1 m³를 뿜어붙인 뒤 시트 위 반발재를 계량하는 방법을 썼다. 같은 논문은 반발률이 첫 단계에 높고 최초 임계두께가 생긴 뒤 점점 줄어든다고 설명한다. 맨 바위면에 처음 쏠 때 많이 튕기고, 숏크리트 층이 생기면 그 층이 재료를 붙잡아 준다는 뜻으로 읽힌다.</p>
<p>터널표준시방서와 KCS 27 30 00(발췌본 기준)에는 반발률의 상한값이 보이지 않는다. 전준태 외(2012)는 2009년 이후 콘크리트표준시방서와 발주청이 전체 반발률 10~20% 범위를 기준으로 삼는다고 적었으나, 이 범위를 현행 KCS 원문에서는 확인하지 못했다. 답안에는 "공사시방서·발주처 기준에 따른다"로 쓰고, 10~20%는 문헌에 소개된 예로만 덧붙이는 편이 안전하다.</p>
<h3 data-ke-size="size23">3. 발생원인</h3>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>구분</th><th>리바운드를 늘리는 원인</th><th>근거</th></tr>
<tr><td>재료·배합</td><td>급결제 함량이 적음(4%일 때 16.8%, 8%일 때 9.8%). 0.2 mm 이하 미분이 부족하거나 굵은골재가 큰 배합(필자 해석: 논문은 미분을 넣으면 부착이 좋아지고 리바운드가 적다, 굵은골재 최대치수는 시험시공 반발률로 정한다고만 씀)</td><td>전준태 외(2012) 3.1.1, 표 9</td></tr>
<tr><td>타설 방법</td><td>노즐이 시공면에 비스듬함, 노즐과 면의 거리가 맞지 않음, 압력·송출량이 일정하지 않음</td><td>터널표준시방서 3.2.9, KCS 27 30 00 3.3.2</td></tr>
<tr><td>순서·두께</td><td>임계두께가 생기기 전 첫 층, 하부→상부 순서를 지키지 않음, 1회 타설 두께 과다(논문은 5 cm 이내 권장)</td><td>전준태 외(2012) 2.2.2(임계두께)·3.3.1(1회 5 cm 이내), 시방서 3.2.10(하부→상부)</td></tr>
<tr><td>시공면</td><td>용출수, 뜬돌·이물질, 강지보재·철망 뒤의 틈</td><td>터널표준시방서 3.1, 3.2.5, 3.4</td></tr>
<tr><td>공법</td><td>건식 공법(습식보다 반발률이 큼)</td><td>전준태 외(2012) 1.1·2.1</td></tr>
</table>
<p>시방서가 노즐 방향·거리를 "반발량이 최소화되도록" 유지할 관리 항목으로 둔 것으로 보아, 노즐 자세를 주요 원인으로 볼 수 있다(필자 해석). 논문은 과거 시방서와 발주청이 상부·천장·수직벽처럼 부위별로 반발률 범위를 따로 두었다고만 소개하고 이유는 적지 않았다. 천장부는 중력 때문에 더 튕길 것이라는 풀이는 필자 추정이다.</p>
<h3 data-ke-size="size23">4. 저감대책</h3>
{img_html}
<ul><li><strong>공법·재료</strong> — 습식 공법을 쓴다. 전준태 외(2012)의 철도터널 시험에서 일반 습식은 급결제 4·6·8%일 때 반발률 16.8·12.7·9.8%, 강섬유 습식은 15.6·12.1·10.6%였다. 두 습식 모두 급결제를 늘릴수록 반발률이 줄었다. 논문은 결론에서 강섬유 습식이 일반 습식보다 반발률이 적다고 보고했지만, 급결제 8%에서는 수치가 역전되어(10.6% > 9.8%) 강섬유를 독립된 저감책으로 단정하기는 어렵다고 본다(필자 해석). 이 값은 현장 1곳의 한 배합 결과이므로 다른 현장에 그대로 옮길 수는 없고, 급결제를 늘리면 단가·장기강도 영향도 함께 봐야 하므로 사용량은 시험배합으로 정한다. 김영선 외(2015)는 분말도를 약 1,000 cm²/g 높인 고분말 시멘트가 반발률을 낮췄다고 보고했다(학술발표 수준의 실험).</li>
<li><strong>타설 방법</strong> — 노즐은 숏크리트 면에 직각으로 두고, 거리는 반발량이 최소가 되도록 유지한다. 터널표준시방서(2015)는 거리를 수치로 정하지 않고, KCS 27 30 00:2023 발췌본은 1 m 정도, 전준태 외(2012)는 1 m 정도(적정 0.75~1.25 m)로 적었다. 건식은 시공 관리 항목으로 물의 압력을 압축공기 압력보다 100 kPa 정도 높게 유지한다(3.2.11).</li>
<li><strong>순서·두께</strong> — 하부에서 상부로 타설하고 강지보재 부분을 먼저 채운다. 여러 층으로 나눠 칠 때는 층끼리 확실히 붙게 한다.</li>
<li><strong>시공면</strong> — 뜬돌과 부착을 방해하는 것을 없애고, 용출수는 배수관 배수 등으로 먼저 처리한다. 철망은 굴착면에 밀착시켜 흔들리지 않게 고정한다.</li>
<li><strong>관리</strong> — 노즐맨 숙련도와 장비 상태가 반발률을 크게 좌우하므로, 로봇 타설기 사용과 작업원 교육을 대책에 넣을 수 있다(필자 해석, 시방서 조항 아님).</li></ul>
<h3 data-ke-size="size23">5. 반발재 처리와 품질관리</h3>
<p>반발재는 숏크리트에 섞이지 않도록 모두 제거하고(3.2.7), 굳기 전에 치우며(3.3.2), 버력과 따로 골라 폐기물관리법에 따라 보관·처리한다(3.3.3). 터널표준시방서 표 5-3.3은 매 타설 때 숏크리트의 부착·성상·반발·분진을 관찰하는 일상관리와 반발률 측정을 품질관리 항목으로 둔다. 강도 공시체는 몰드를 70° 정도 기울여 반발재가 흘러내리게 한 뒤 뿜어붙여 만든다(3.6.6). 반발재가 공시체에 섞이지 않게 하려는 장치다.</p>
<h3 data-ke-size="size23">6. 계산 예 (가상 예시)</h3>
<p>아래 분사량·단위질량·반발재 질량·부착 소요량은 설명을 위해 만든 가상 예시이며 실측값이나 공식 기준값이 아니다. 반발률 16.8%와 9.8%만 전준태 외(2012) 표 9의 일반 습식 숏크리트(급결제 4%, 8%) 측정값을 빌려 왔다. 반발재와 분사한 숏크리트의 단위질량은 같다고 가정한다.</p>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>항목</th><th>계산</th><th>결과</th></tr>
<tr><td>분사 총질량</td><td>5.0 m³ × 2,300 kg/m³</td><td>11,500 kg</td></tr>
<tr><td>반발률</td><td>1,380 / 11,500 × 100</td><td>12.0 %</td></tr>
<tr><td>부착량</td><td>11,500 − 1,380</td><td>10,120 kg (4.40 m³)</td></tr>
<tr><td>부착 소요 220 m³, RR 16.8 %</td><td>220 / (1 − 0.168)</td><td>264.4 m³ 분사</td></tr>
<tr><td>부착 소요 220 m³, RR 9.8 %</td><td>220 / (1 − 0.098)</td><td>243.9 m³ 분사</td></tr>
<tr><td>차이</td><td>264.4 − 243.9 (반발재 44.4 → 23.9 m³)</td><td>20.5 m³</td></tr>
</table>
{f2_html}
<p>같은 양을 붙이려 해도 반발률이 16.8%면 9.8%일 때보다 20.5 m³를 더 쏘아야 하고, 그만큼이 버려질 반발재가 된다. 반발률을 몇 % 낮추는 일이 재료비와 폐기물을 함께 줄인다는 점을 숫자로 보이는 것이 계산 예의 요점이다. 아래 도식은 같은 가상 조건을 그림으로 옮긴 것이다.</p>
{gif_html}
<h3 data-ke-size="size23">7. 결론</h3>
<p>리바운드는 없앨 수 없으므로 반발률을 측정해 관리값으로 삼는다. 습식·적정 급결제·부착성 좋은 배합, 노즐 직각·적정 거리(KCS 발췌 1 m 정도)·하부에서 상부로의 순서, 용출수와 뜬돌 처리가 저감의 골격이며, 반발재는 굳기 전에 제거해 품질 저하와 폐기물 문제를 함께 막는다.</p>
<h2 data-ke-size="size26">핵심 암기어</h2>
<p>RR = 반발재/분사량 × 100 · 노즐 직각·거리 약 1 m(KCS) · 하부→상부, 강지보재 먼저 · 습식·급결제 시험배합 · 반발재 굳기 전 제거</p>
<h2 data-ke-size="size26">답안 자가점검</h2>
<ul><li>리바운드 정의와 영향(재료 손실, 반발재 처리, 품질 저하)을 개요에 썼는가?</li>
<li>반발률 식과 측정 방법(바닥 반발재 수거·계량)을 썼는가?</li>
<li>원인을 재료·배합, 타설 방법, 순서·두께, 시공면으로 나눴는가?</li>
<li>대책이 원인과 짝을 이루는가(노즐 직각·거리, 하부→상부, 용출수 처리 등)?</li>
<li>반발재 처리(굳기 전 제거, 혼입 금지, 폐기물 처리)를 언급했는가?</li>
<li>반발률 기준값을 출처 없이 단정하지 않았는가?</li></ul>
<h2 data-ke-size="size26">기호·단위 정리</h2>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>기호</th><th>뜻</th><th>단위</th><th>출처</th></tr>
<tr><td>RR</td><td>반발률(rebound ratio)</td><td>%</td><td>전준태 외(2012) 식 (2)·(8), 시방서 3.6.12</td></tr>
<tr><td>R<sub>sum</sub></td><td>리바운드된 총질량(반발재)</td><td>kg</td><td>전준태 외(2012) 식 (2)</td></tr>
<tr><td>S<sub>sum</sub></td><td>분사한 총질량</td><td>kg</td><td>전준태 외(2012) 식 (1)·(2)</td></tr>
<tr><td>Y<sub>sum</sub></td><td>부착된 총질량(S<sub>sum</sub> − R<sub>sum</sub>)</td><td>kg</td><td>전준태 외(2012) 2.2.3</td></tr>
<tr><td>V<sub>need</sub>, V<sub>shot</sub></td><td>부착 소요 체적, 필요한 분사 체적</td><td>m³</td><td>이 글에서 붙인 기호(단위질량 같다고 가정)</td></tr>
</table>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 형식의 2쪽 따라쓰기 PDF이다. 답안과 원인 표가 옅은 회색 글씨로 들어 있어 출력해 그대로 따라 쓸 수 있다.</p>
<h2 data-ke-size="size26">참고자료</h2>
<ul>{src}</ul>
<p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 자료 확인일은 2026년 10월 25일이다. 시방서 조항 번호는 터널표준시방서(2015) 기준이며, 이 시방서는 KCS 27 30 00(터널 지보재)으로 옮겨졌다. KCS 27 30 00:2023의 조항은 국가건설기준센터 원문을 열지 못해 제3자 발췌로 확인했으므로, 실제 적용 전에는 현행 원문과 공사시방서를 대조한다. 논문 두 편의 수치는 특정 현장·배합 조건의 결과다.</p>
<p>#토목시공기술사 #숏크리트 #리바운드 #반발률 #NATM #터널시공 #기술사답안 #하루한문제</p>'''

if __name__ == '__main__':
    figure(); make_pdf()
    cap_img = '직접 작성한 개념도. 원인과 대책의 짝, 노즐 자세(면에 직각, 약 1 m)를 정리했다.'
    alt_img = '숏크리트 리바운드의 원인(재료·배합, 타설 방법, 순서·두께, 시공면, 공법)과 저감대책, 노즐을 굴착면에 직각으로 약 1 m 거리에 두는 그림'
    alt_f1 = 'RR = R_sum / S_sum × 100 (%), Y_sum = S_sum − R_sum, V_shot = V_need / (1 − RR/100)'
    alt_f2 = 'S_sum = 5.0 × 2300 = 11500 kg, RR = 1380/11500 × 100 = 12.0 %, V_shot = 220/(1−0.168) = 264.4 m³, 220/(1−0.098) = 243.9 m³, 차이 20.5 m³'
    alt_gif = '가상 예시에서 분사량 11,500 kg 중 반발 1,380 kg(반발률 12.0 %)과, 부착 220 m³를 얻기 위한 분사량이 반발률 16.8 %에서 264.4 m³, 9.8 %에서 243.9 m³로 20.5 m³ 차이 나는 막대 도식'
    alt_banner = TITLE
    cap_f1 = '수식 1. 반발률과 부착량, 부착 소요량에 필요한 분사량'
    cap_f2 = '수식 2. 계산 예(가상 예시, 반발률 16.8·9.8 %는 논문 측정값 인용)'
    cap_gif = '도식. 반발률에 따른 분사량 차이 — 학습용 가정값'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(banner_html=f'<p data-ax-attach="{BANNER}"></p>\n', img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'rebound.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(banner_html=f'<p><img src="{CDN}banner.png" alt="{alt_banner}" style="max-width:100%;height:auto"></p>\n',
                   img_html=b_fig(CDN + 'rebound-causes.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'rebound.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (2쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(banner_html=f'<p><img src="{BANNER}" alt="배너"></p>', img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1),
                   f2_html=b_fig(F2_NAME, alt_f2, cap_f2), gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    print(json.dumps(CALC, ensure_ascii=False))
