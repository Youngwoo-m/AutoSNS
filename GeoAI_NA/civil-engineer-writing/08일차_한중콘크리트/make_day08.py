"""8일차 동절기 한중콘크리트 배합설계와 시공관리 — 개념도·따라쓰기 PDF·티스토리/Blogger 본문을 만든다."""
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
TITLE = '[토목시공기술사] 동절기 한중콘크리트 배합설계와 시공관리 | 하루 한 문제 8일차'
PDF_NAME = '08일차_한중콘크리트_답안예시_따라쓰기.pdf'
FIG_NAME = '한중콘크리트_관리흐름_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_호칭강도_적산온도.png', '수식2_계산예.png', '도식_적산온도_누적.gif'
CDN = 'https://geoai-na.netlify.app/civil-questions/materials/day08/'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'

# ── 계산 예(가상 예시) ───────────────────────────────────────────────
FCQ, TN = 24.0, 6.0                 # MPa, 품질기준강도(가상)·기온보정값(28일 예상평균 0 ℃ 이상 4 ℃ 미만)
W, B = 170.0, 340.0                 # kg/m³, 단위수량·단위결합재량(가상)
FCN = FCQ + TN
WB = W / B
FA_MAX = 0.15 * B
CURE = [(3, 10.0), (4, 5.0)]        # (일수, 양생온도 ℃) — 가상
M = sum(d * (t + 10) for d, t in CURE)
T20 = M / (20 + 10)
CALC = {'fcn_MPa': FCN, 'WB': round(WB, 3), 'WB_ok': WB <= 0.60, 'FA_max_kg': round(FA_MAX, 1),
        'M_CD': M, 't20_days': round(T20, 2)}

# ── 개념도 (관리 흐름과 온도 기준) ─────────────────────────────────────
def figure():
    im = Image.new('RGB', (1600, 1000), 'white'); dr = ImageDraw.Draw(im)
    f = lambda z: ImageFont.truetype(PRET, z)
    INK, TEAL, RED, GRAYC, SOFT = '#263746', '#176977', '#B6462F', '#7A8790', '#EAF2F3'
    dr.text((60, 40), '한중콘크리트 시공관리 흐름과 온도 기준(KCS 14 20 40)', font=f(40), fill=INK)
    steps = [('① 적용 판단', '일평균 4 ℃ 이하 또는 24시간 내 일최저 0 ℃ 이하 예상'),
             ('② 배합', 'AE콘크리트, W/B 60% 이하, 기온보정 6 MPa, FA 15%·슬래그 30% 이하'),
             ('③ 재료·운반', '동결 골재 금지, 물·골재만 가열(시멘트 직접 가열 금지)'),
             ('④ 타설', '타설 온도 5~20 ℃(가혹·단면 300 mm 이하 10 ℃ 이상), 눈·얼음 제거'),
             ('⑤ 초기양생', '소요 압축강도까지 5 ℃ 이상 → 이후 2일 0 ℃ 이상'),
             ('⑥ 확인·종료', '현장양생 공시체 강도 + 책임기술자 승인, 온도 기록')]
    x, y, w, h = 60, 125, 1000, 112
    for i, (a, b) in enumerate(steps):
        yy = y + i * (h + 26)
        dr.rounded_rectangle([x, yy, x + w, yy + h], 16, fill=SOFT, outline=TEAL, width=4)
        dr.text((x + 26, yy + 18), a, font=f(34), fill=TEAL)
        dr.text((x + 26, yy + 66), b, font=f(25), fill=RED if i in (1, 4) else INK)
        if i < 5:
            cx = x + 110
            dr.polygon([(cx - 15, yy + h + 4), (cx + 15, yy + h + 4), (cx, yy + h + 24)], fill=TEAL)
    rx = 1110
    dr.text((rx, 125), '초기양생 종료 강도', font=f(32), fill=INK)
    dr.text((rx, 168), '표 3.4-1(제3자 정리 값)', font=f(24), fill=GRAYC)
    rows = [('단면(mm)', '물 포화', '보통 노출'), ('300 이하', '15', '5'), ('300~800', '12', '5'), ('800 초과', '10', '5')]
    cw = [150, 140, 150]
    for r, row in enumerate(rows):
        cx = rx
        for c, s in enumerate(row):
            dr.rectangle([cx, 210 + r * 62, cx + cw[c], 272 + r * 62], outline=INK, width=2, fill=SOFT if r == 0 else 'white')
            dr.text((cx + 12, 226 + r * 62), s, font=f(24), fill=INK)
            cx += cw[c]
    dr.text((rx, 470), '단위 MPa. 원문 표는 열람하지 못함', font=f(22), fill=GRAYC)
    dr.text((rx, 540), '보온양생 방법', font=f(32), fill=INK)
    for i, s in enumerate(['급열: 히터·온풍으로 가열', '단열: 단열재로 수화열 보존', '피복: 시트로 바람·눈 차단',
                           '국부 가열·급격한 건조 금지', '가열 끝나면 서서히 냉각']):
        dr.text((rx, 592 + i * 46), '· ' + s, font=f(26), fill=INK)
    dr.text((60, 940), '직접 작성한 개념도 / 기온보정·혼화재 상한은 국토교통부 2024.12.17 보도자료, 나머지 값은 KCS 14 20 40:2024 제3자 정리 기준', font=f(24), fill=GRAYC)
    im.save(OUT / FIG_NAME, quality=92)

# ── 따라쓰기 PDF ─────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('KR', '/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
tp = PdfReader(TEMPLATE).pages[4]
PW, PH = float(tp.mediabox.width), float(tp.mediabox.height)
GRAY = 184 / 255
QNO = '6'

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
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(PW, PH))
    p1 = {
        0: ('동절기 한중콘크리트 배합설계 및 시공관리 방안', 12.5),
        1: ('1. 개요', 14),
        2: ('한중콘크리트는 일평균기온 4℃ 이하 또는 타설 후', 12.5),
        3: ('24시간 내 일최저 0℃ 이하가 예상될 때 적용한다.', 12.5),
        4: ('응결 지연·초기동해를 막도록 배합·보온양생을 계획', 12.5),
        5: ('하고 책임기술자 승인을 받는다(KCS 14 20 40:2024).', 12),
        6: ('2. 저온이 콘크리트에 주는 영향', 14),
        7: ('① 수화 지연 → 응결·강도발현 지연, 거푸집 존치 증가', 12),
        8: ('② 초기동해: 굳기 전 물이 얼어 팽창, 조직 이완', 12),
        9: ('③ 표면·내부 온도차 → 온도균열, 급랭 시 균열', 12),
        10: ('④ 혼화재 많으면 저온에서 강도발현이 더 늦어짐', 12),
        11: ('3. 배합설계', 14),
        12: ('(1) AE콘크리트 원칙, 단위수량은 가능한 한 적게', 12.5),
        13: ('(2) 물-결합재비(W/B) 60% 이하', 12.5),
        14: ('(3) 호칭강도 = 품질기준강도 + 기온보정값 Tn', 12.5),
        15: ('    28일 예상평균 0℃ 이상 4℃ 미만: Tn = 6 MPa', 12),
        16: ('(4) 혼화재 상한: 플라이애시 15%, 고로슬래그 30%', 12.5),
        17: ('    (종전 25%·50%에서 축소)', 12),
        18: ('(5) 적산온도로 강도를 정하면 기온보정 미적용', 12.5),
        19: ('(6) 신재료·신기술로 목표강도 입증 시 책임기술자', 12.5),
        20: ('    승인으로 (3)·(4) 기준 조정 가능', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    text(c, 132, 731, QNO, 14)
    c.showPage()
    p2 = {
        0: ('4. 재료 관리', 14),
        1: ('· 동결 골재, 눈·얼음 섞인 골재는 쓰지 않는다', 12.5),
        2: ('· 가열은 물 또는 골재만, 시멘트는 직접 가열 금지', 12.5),
        3: ('· 가열 재료 투입 순서를 정해 시멘트 급결 방지', 12.5),
        4: ('5. 운반·타설', 14),
        5: ('· 타설 온도 5~20℃, 기상 가혹·단면 300mm 이하는', 12.5),
        6: ('  최저 10℃ 확보, 운반 중 열손실 최소화', 12.5),
        7: ('· 철근·거푸집의 눈·얼음 제거, 언 지반·이음면 해빙', 12.5),
        8: ('· 타설 직후 시트 피복·방풍, 표면 동결 방지', 12.5),
        9: ('6. 양생', 14),
        10: ('(1) 초기양생: 소요 압축강도까지 5℃ 이상 유지,', 12.5),
        11: ('    이후 2일간 0℃ 이상(표 3.4-1)', 12.5),
        16: ('(2) 보온양생: 급열·단열·피복 또는 병용, 국부가열', 12.5),
        17: ('    금지, 시험가열 후 배치, 종료 후 서서히 냉각', 12.5),
        18: ('(3) 현장양생 공시체(1회/일·층·구획)로 강도 확인,', 12.5),
        19: ('    책임기술자 승인 후 양생 종료', 12.5),
        20: ('(4) 자기기록 온도계로 콘크리트·보온 내부·외기 기록', 12),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, QNO, 14)
    ys = [764 - 11.45 * 32.35 - i * 30 for i in range(4)]
    rule_table(c, [202, 360, 440, 520, 605], ys, [
        ('단면(mm) / MPa', '300 이하', '300~800', '800 초과'),
        ('물로 포화되는 부분', '15', '12', '10'),
        ('보통 노출 상태', '5', '5', '5'),
    ], sizes=(10.5, 11))
    line(c, 15, '※ 표 값은 제3자 정리(원문 미열람), 현행판 대조 후 사용', 11)
    c.showPage()
    p3 = {
        0: ('7. 계산 예(가상 예시)', 14),
        1: ('품질기준강도 24MPa, 28일 예상평균 0℃ 이상 4℃ 미만', 12),
        2: ('호칭강도 = 24 + 6 = 30 MPa', 12.5),
        3: ('W/B = 170/340 = 0.50 ≤ 0.60 → 만족', 12.5),
        4: ('FA 상한 = 0.15 × 340 = 51 kg/m³', 12.5),
        5: ('적산온도 M = Σ(θ+10)Δt, 10℃ 3일 + 5℃ 4일', 12.5),
        6: ('M = 3×20 + 4×15 = 120 ℃·D', 12.5),
        7: ('→ 20℃ 양생 환산 120/30 = 4.0일에 해당', 12.5),
        8: ('8. 시공관리 흐름', 14),
        9: ('기상 확인 → 배합 → 재료가열·운반 → 타설', 12.5),
        10: ('→ 초기양생(5℃↑) → 공시체 확인·승인 → 계속양생', 12.5),
        11: ('· 매일 예보 확인, 한파 시 타설 연기 기준 사전 결정', 12),
        12: ('· 보온 설비·연료·온도계를 타설 전에 준비', 12),
        13: ('9. 결론', 14),
        14: ('한중콘크리트는 배합으로 저온의 강도 손실을 메우고', 12.5),
        15: ('(기온보정 6MPa, 혼화재 제한), 시공으로 초기동해를', 12.5),
        16: ('막는다(타설 온도, 5℃ 초기양생). 종료 시점은 날짜가', 12.5),
        17: ('아닌 현장양생 공시체 강도와 승인으로 정하고, 온도', 12.5),
        18: ('기록을 남겨 품질을 증명하는 것이 핵심이다.', 12.5),
        20: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    text(c, 132, 731, QNO, 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(3):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(PW, PH)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2024 제132회 2교시 6번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)

# ── 본문 ─────────────────────────────────────────────────────────────
Q132 = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5212868&brdId=Q006&gSite=Q'
Q126 = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq=5209527&brdId=Q006&gSite=Q'
PRESS = 'https://www.korea.kr/briefing/pressReleaseView.do?newsId=156666024'
NOTICE = 'https://www.codil.or.kr/filebank/moct2014//202501/MOCT3282_0.PDF?nserialno=3282'
PAPER = 'https://koreascience.kr/article/CFKO202316447237530.pdf'
SOURCES = [
    ('국토교통부 보도자료(2024.12.17) 「추운 날, 비 오는 날에도 안전한 시공」 — 첨부 PDF의 한중콘크리트 기온보정강도·혼화재 상한·현장양생공시체 의무화 내용', PRESS),
    ('국토교통부고시 제2024-879호(2024.12.30) — KCS 14 20 40 2.1(구성재료)·2.2.2(배합) 개정 내용의 2025년 1월 1일 적용', NOTICE),
    ('후윈야오 외(2023), 「한국과 중국의 한중 콘크리트 표준시방서의 보온양생 규정 비교」, 한국건축시공학회 2023 가을학술발표대회 논문집 23(2) — KCS 14 20 40 적용범위·초기양생·보온양생 조문 인용(개정 전 판)', PAPER),
    ('국가건설기준센터 — KCS 14 20 40 한중콘크리트 현행판 확인처(이번 작성 때 원문 열람 실패)', 'https://www.kcsc.re.kr'),
]

def body(img_html, f1_html, f2_html, gif_html, pdf_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    return f'''<p>한중콘크리트 문제는 "배합으로 강도 손실을 메우고, 시공으로 초기동해를 막는다"는 두 축으로 정리된다. 국토교통부 보도자료 기준으로 2024년 12월 개정에서 일평균 4 ℃ 이하일 때 기온보정강도 6 MPa, 플라이애시 15%·고로슬래그 30% 이하라는 배합 기준이 들어왔고, 현장양생 공시체 제작이 의무가 되었다. 답안의 중심은 이 개정 배합 기준과, 5 ℃ 초기양생을 공시체 강도와 책임기술자 승인으로 끝내는 양생 절차다.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2 data-ke-size="size26">오늘의 문제</h2>
<p><strong>시험 종목: 토목시공기술사 / 과목(학습 분류): 콘크리트공(한중콘크리트) / 유형: 논술형 / 관련 기출: 2024년 제132회 2교시 6번</strong></p>
<blockquote>동절기 한중콘크리트 타설 시 배합설계 및 시공관리 방안에 대하여 설명하시오.</blockquote>
<p>위 문제는 2024년 제132회 2교시 6번 기출 원문이다. 답안예시는 학습용으로 작성한 것이며 공식 정답이나 채점기준이 아니다. 권장 연습은 목차 3분, 작성 22분, 답안지 3쪽이다. 학습 분류와 시간·분량은 연습을 위한 안내이며 공식 시험 과목명이 아니다.</p>
<h3 data-ke-size="size23">출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항 가운데 한중콘크리트의 배합과 시공을 직접 묻는 문항은 다음 2건이다.</p>
<ul><li>2022년 제126회 3교시 3번(논술형): <a href="{Q126}">한중콘크리트의 배합설계와 시공 시 유의사항에 대하여 설명하시오.</a></li>
<li>2024년 제132회 2교시 6번(논술형): <a href="{Q132}">동절기 한중콘크리트 타설 시 배합설계 및 시공관리 방안에 대하여 설명하시오.</a></li></ul>
<p>두 문제는 문장만 조금 다르고 배합설계와 시공을 함께 묻는 같은 유형이다. '콘크리트·거푸집·양생(혼화·철근·프리캐스트 포함)' 키워드 묶음(중복 허용 82문항)은 분야를 가늠하는 지표일 뿐 이번 유형의 출제 횟수나 공식 출제 비중이 아니다. 여름철 조건은 <a href="https://na-geoai.tistory.com/107">2일차 서중콘크리트</a>, 저온에서 길어지는 거푸집 존치 판단은 <a href="https://na-geoai.tistory.com/142">7일차 거푸집·동바리 해체 시기</a>와 함께 보면 좋다.</p>
<h2 data-ke-size="size26">답안 목차</h2>
<p>1. 개요(적용 범위) → 2. 저온의 영향 → 3. 배합설계 → 4. 재료 관리 → 5. 운반·타설 → 6. 양생 → 7. 계산 예 → 8. 시공관리 흐름 → 9. 결론</p>
<h2 data-ke-size="size26">답안예시</h2>
<h3 data-ke-size="size23">1. 개요</h3>
<p>한중콘크리트는 타설일의 일평균기온이 4 ℃ 이하이거나, 타설 후 24시간 안에 일최저기온이 0 ℃ 이하로 예상되거나, 그 밖에 초기동해의 위험이 있을 때 적용한다(KCS 14 20 40 1.1). 저온에서는 수화가 늦어지고, 굳기 전의 콘크리트 속 물이 얼면 조직이 손상된다. 그래서 한중콘크리트의 관리는 배합에서 저온의 강도 손실을 미리 보태고, 시공에서 초기동해를 막는 보온양생을 계획하며, 양생 종료를 시험과 승인으로 정하는 순서로 짠다.</p>
<h3 data-ke-size="size23">2. 저온이 콘크리트에 주는 영향</h3>
<ul><li>수화 반응이 느려져 응결과 강도 발현이 늦어지고, 거푸집 존치기간이 길어진다.</li>
<li>초기동해: 강도가 충분하지 않을 때 콘크리트 속 물이 얼어 부피가 늘면 조직이 이완되고, 나중에 양생해도 강도가 회복되지 않을 수 있다.</li>
<li>보온 중 내부와 표면의 온도 차, 보온을 갑자기 걷을 때의 급랭이 균열을 만든다.</li>
<li>플라이애시·고로슬래그 같은 혼화재는 저온에서 강도 발현을 더 늦춘다. 2024년 개정에서 혼화재 상한을 줄인 이유다.</li></ul>
<h3 data-ke-size="size23">3. 배합설계</h3>
<ul><li>AE콘크리트를 쓰는 것을 원칙으로 하고, 단위수량은 소요 워커빌리티를 얻는 범위에서 가능한 한 적게 한다. 물-결합재비는 60% 이하로 한다.</li>
<li>기온보정강도: 국토교통부 보도자료(첨부 설명자료 표기 기준)는 일평균 4 ℃ 이하 저온 환경에서 기온보정강도 6 MPa를 적용하고 책임기술자가 승인한 품질기준강도 확보방안을 세우도록 했다(28일 재령 기준). 종전에는 4~8 ℃ 6 MPa, 8~18 ℃ 3 MPa 보정만 있고 4 ℃ 이하 기준이 없었다.</li>
<li>혼화재 상한: 플라이애시는 25%에서 15% 이하로, 고로슬래그는 50%에서 30% 이하로 줄였다.</li>
<li>예외: 구성재료나 양생방법을 개선하는 새 기술로 목표강도를 확보할 수 있음이 입증되면 책임기술자 승인을 받아 위 두 기준을 적용하지 않을 수 있다.</li>
<li>이 배합 기준(KCS 14 20 40 2.1 구성재료, 2.2.2 배합)은 국토교통부고시 제2024-879호에 따라 2025년 1월 1일부터 적용한다.</li></ul>
<p>호칭강도와 적산온도의 관계를 식으로 쓰면 다음과 같다. 보도자료는 이 기준을 "일평균 4 ℃ 이하, 28일 재령 기준"으로 적었고, KCS 14 20 40:2024 제3자 정리 자료는 "재령 28일 예상평균기온 0 ℃ 이상 4 ℃ 미만일 때 기온보정값 6 MPa(표 2.2-1)"로 적었다. 같은 정리 자료에 따르면 초기양생 온도를 높이거나 보온양생을 늘려 관리재령까지의 예상평균기온이 4 ℃ 이상이 되면 KCS 14 20 10의 일반 보정값을 쓸 수 있고, 호칭강도를 적산온도 방식으로 정하면 기온보정값을 적용하지 않는다. 두 표현이 같은 조항을 가리키는지와 기호·표 번호는 공식 원문으로 확인하지 못했다.</p>
{f1_html}
<h3 data-ke-size="size23">4. 재료 관리</h3>
<ul><li>얼어 있는 골재나 눈·얼음이 섞인 골재는 그대로 쓰지 않는다.</li>
<li>재료를 가열할 때는 물 또는 골재를 가열하고, 시멘트는 어떤 경우에도 직접 가열하지 않는다.</li>
<li>가열한 재료를 믹서에 넣는 순서를 정해 시멘트가 급결하지 않게 한다.</li></ul>
<h3 data-ke-size="size23">5. 운반·타설</h3>
<ul><li>타설할 때의 콘크리트 온도는 5~20 ℃ 범위에서 정하고, 기상 조건이 가혹하거나 단면 두께가 300 mm 이하이면 최저 10 ℃를 확보한다. 운반 중 열손실을 줄인다.</li>
<li>철근·거푸집에 붙은 눈과 얼음을 타설 전에 없애고, 지반이나 이어치기 면이 얼어 있으면 녹인 뒤 타설한다.</li>
<li>타설 직후 시트 등으로 덮고 바람을 막아 노출면이 얼지 않게 한다.</li></ul>
<h3 data-ke-size="size23">6. 양생</h3>
<p>초기양생은 콘크리트가 아래 표의 압축강도에 이를 때까지 5 ℃ 이상을 유지하고, 그 뒤 2일 동안은 어느 부분도 0 ℃ 이상이 되도록 한다. 표의 값은 KCS 14 20 40:2024 표 3.4-1을 옮긴 제3자 정리 자료의 값이며 원문 표는 열람하지 못했으므로, 실제 적용 전에는 현행판과 공사시방서를 대조한다.</p>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>구조물의 노출 상태 \\ 단면</th><th>얇은 경우(300 mm 이하)</th><th>보통(300~800 mm)</th><th>두꺼운 경우(800 mm 초과)</th></tr>
<tr><td>계속 또는 자주 물로 포화되는 부분</td><td>15 MPa</td><td>12 MPa</td><td>10 MPa</td></tr>
<tr><td>보통의 노출 상태에 있고 물로 포화되지 않는 부분</td><td>5 MPa</td><td>5 MPa</td><td>5 MPa</td></tr>
</table>
<p>같은 정리 자료의 표 3.4-2는 보통 단면에서 이 강도를 얻는 양생일수의 표준을 5 ℃/10 ℃ 양생 기준으로 물 포화 부분 보통 시멘트 9일/7일, 혼합 시멘트 B종 12일/9일, 보통 노출 부분 4일/3일, 5일/4일로 제시한다.</p>
{img_html}
<ul><li>보온양생은 급열, 단열, 피복 가운데 하나 또는 조합으로 한다. 국부적으로 가열하거나 급격히 건조시키지 않고, 가열 설비의 배치는 시험가열을 해 보고 정한다. 가열을 끝낸 뒤 콘크리트 온도를 갑자기 떨어뜨리지 않는다.</li>
<li>양생 종료는 현장양생 공시체의 압축강도로 확인하고 책임기술자의 승인을 받는다(학술발표 논문이 인용한 3.4.1 조문과 제3자 정리 자료 기준). 국토교통부 보도자료에 따르면 2024년 개정으로 현장양생 공시체는 하루 1회, 타설 층별 1회 또는 구획별 1회 등으로 제작·시험이 의무가 되었다.</li>
<li>콘크리트 온도, 보온 시설 안의 온도, 외기온을 자기기록 온도계로 기록해 양생 관리와 품질 증명에 쓴다.</li></ul>
<h3 data-ke-size="size23">7. 계산 예 (가상 예시)</h3>
<p>아래 조건은 설명을 위해 만든 가상 예시이며 실제 배합이나 실측 온도가 아니다. 품질기준강도 24 MPa, 28일 예상평균기온 0 ℃ 이상 4 ℃ 미만, 단위수량 170 kg/m³, 단위결합재량 340 kg/m³, 급열 10 ℃ 3일 뒤 5 ℃ 4일 보온양생으로 가정한다. 플라이애시 비율은 결합재 질량에 대한 비율로 보고, 적산온도 계산의 콘크리트 온도는 보온 시설 안의 양생 온도와 같다고 단순화한다. 실제로는 보온양생으로 관리재령까지의 예상평균기온이 4 ℃ 이상이 되면 보정값이 달라질 수 있으므로, 이 예시는 보정값 6 MPa를 그대로 쓰는 경우만 보인다.</p>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>항목</th><th>계산·판정</th><th>결과</th></tr>
<tr><td>호칭강도</td><td>24 + 6</td><td>30 MPa</td></tr>
<tr><td>물-결합재비</td><td>170 / 340 = 0.50 ≤ 0.60</td><td>만족</td></tr>
<tr><td>플라이애시 상한(결합재 질량 대비)</td><td>0.15 × 340</td><td>51 kg/m³ 이하</td></tr>
<tr><td>적산온도</td><td>3 × (10 + 10) + 4 × (5 + 10) = 60 + 60</td><td>120 ℃·D</td></tr>
<tr><td>20 ℃ 양생 환산</td><td>120 / (20 + 10)</td><td>4.0일</td></tr>
</table>
{f2_html}
<p>7일 동안 보온양생을 해도 적산온도로는 20 ℃에서 4일 양생한 것과 같은 수준이다. 적산온도 식 M = Σ(θ + 10)Δt는 −10 ℃를 기준온도로 하는 일반적인 형태이며 이 글에서는 비교 설명에만 쓴다. 실제 양생 종료는 이 환산이 아니라 현장양생 공시체 강도와 승인으로 정한다. 아래 도식은 같은 가상 예시의 적산온도 누적을 보여 준다.</p>
{gif_html}
<h3 data-ke-size="size23">8. 시공관리 흐름</h3>
<p>기상 확인 → 배합 결정(기온보정·혼화재 상한) → 재료 가열·운반 → 타설(타설 온도 확인) → 초기양생(5 ℃ 이상) → 현장양생 공시체 확인·책임기술자 승인 → 계속 양생과 서서히 냉각. 매일 기상예보를 확인하고 한파 때 타설을 미룰 기준을 미리 정하며, 보온 설비·연료·온도계는 타설 전에 준비해 둔다.</p>
<h3 data-ke-size="size23">9. 결론</h3>
<p>한중콘크리트는 배합으로 저온의 강도 손실을 메우고(보도자료 기준 기온보정 6 MPa, 플라이애시 15%·고로슬래그 30% 이하), 시공으로 초기동해를 막는다(타설 온도 5~20 ℃, 5 ℃ 이상 초기양생). 양생 종료는 날짜가 아니라 현장양생 공시체 강도와 책임기술자 승인으로 정하고, 온도 기록으로 품질을 증명하는 것이 답안의 골격이다.</p>
<h2 data-ke-size="size26">핵심 암기어</h2>
<p>일평균 4 ℃·일최저 0 ℃ · 기온보정 6 MPa · FA 15%·슬래그 30% · 타설 5~20 ℃(최저 10 ℃) · 5 ℃ 초기양생 + 2일 0 ℃</p>
<h2 data-ke-size="size26">답안 자가점검</h2>
<ul><li>적용 범위(일평균 4 ℃ 이하, 24시간 내 일최저 0 ℃ 이하)를 먼저 썼는가?</li>
<li>2024년 개정 배합 기준(기온보정 6 MPa, 혼화재 상한 축소, 예외 규정)을 썼는가?</li>
<li>시멘트를 직접 가열하지 않는다는 재료 관리를 넣었는가?</li>
<li>타설 온도 범위와 초기양생 온도·강도 기준을 구분했는가?</li>
<li>현장양생 공시체 의무화와 책임기술자 승인으로 양생 종료를 정했는가?</li>
<li>보온양생 방법과 급랭 방지, 온도 기록을 언급했는가?</li></ul>
<h2 data-ke-size="size26">기호·단위 정리</h2>
<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">
<tr><th>기호</th><th>뜻</th><th>단위</th><th>출처</th></tr>
<tr><td>f<sub>cn</sub></td><td>호칭강도</td><td>MPa</td><td>KCS 14 20 40:2024 제3자 정리(원문 미열람)</td></tr>
<tr><td>f<sub>cq</sub></td><td>품질기준강도</td><td>MPa</td><td>KCS 14 20 40:2024 제3자 정리(원문 미열람)</td></tr>
<tr><td>T<sub>n</sub></td><td>기온보정값(28일 예상평균 0 ℃ 이상 4 ℃ 미만에서 6)</td><td>MPa</td><td>국토교통부 보도자료 2024.12.17(6 MPa), 조건 표현은 제3자 정리</td></tr>
<tr><td>M</td><td>적산온도</td><td>℃·D</td><td>−10 ℃ 기준 일반식(현행 조항 번호 미확인)</td></tr>
<tr><td>θ, Δt</td><td>Δt 기간의 콘크리트 온도, 기간</td><td>℃, 일</td><td>같은 식</td></tr>
<tr><td>W/B</td><td>물-결합재비</td><td>—</td><td>KCS 14 20 40:2024 제3자 정리(60% 이하)</td></tr>
</table>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 형식의 3쪽 따라쓰기 PDF이다. 답안과 양생 강도표가 옅은 회색 글씨로 들어 있어 출력해 그대로 따라 쓸 수 있다.</p>
<h2 data-ke-size="size26">공식 참고자료</h2>
<ul>{src}</ul>
<p>관련 기출 링크는 Q-net의 회차별 문제지 게시글이다. 자료 확인일은 2026년 10월 24일이다. 기온보정강도·혼화재 상한·현장양생 공시체 의무화는 국토교통부 보도자료 첨부 PDF를, 적용 시점은 고시 제2024-879호를 근거로 했다. 적용 범위·초기양생·보온양생 조문은 학술발표 논문에 인용된 개정 전 KCS 14 20 40 조문과 KCS 14 20 40:2024 제3자 정리 자료를 대조해 썼다. 타설 온도, 물-결합재비, 표 3.4-1·3.4-2 값은 제3자 정리 자료의 값이고 국가건설기준센터 원문은 열람하지 못했으므로, 실제 적용 전에는 현행판과 공사시방서를 대조한다.</p>
<p>#토목시공기술사 #한중콘크리트 #동절기콘크리트 #KCS142040 #콘크리트공 #기술사답안 #하루한문제</p>'''

if __name__ == '__main__':
    figure(); make_pdf()
    cap_img = '직접 작성한 개념도. 기온보정·혼화재 상한은 국토교통부 보도자료(2024.12.17), 나머지 값은 KCS 14 20 40:2024 제3자 정리 자료 기준이다.'
    alt_img = '한중콘크리트 적용 판단, 배합, 재료·운반, 타설, 초기양생, 확인·종료 순서의 관리 흐름과 초기양생 종료 강도 표, 보온양생 방법 개념도'
    alt_f1 = 'f_cn = f_cq + T_n (T_n = 6 MPa, 28일 예상평균기온 0 ℃ 이상 4 ℃ 미만), 적산온도 M = Σ(θ+10)Δt'
    alt_f2 = '호칭강도 24+6=30 MPa, W/B 0.50, 플라이애시 51 kg/m³ 이하, 적산온도 120 ℃·D, 20 ℃ 환산 4.0일'
    alt_gif = '10 ℃ 3일과 5 ℃ 4일 보온양생의 적산온도가 120 ℃·D까지 쌓이고, 20 ℃ 양생으로는 4.0일에 같은 값이 되는 가상 예시 도식'
    cap_f1 = '수식 1. 호칭강도와 기온보정값, 적산온도 일반식(기호는 KCS 14 20 40:2024 제3자 정리 기준)'
    cap_f2 = '수식 2. 계산 예(가상 예시, 품질기준강도 24 MPa)'
    cap_gif = '도식. 가상 양생 온도로 계산한 적산온도 누적과 20 ℃ 양생 환산 — 학습용 가정값'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'maturity.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(img_html=b_fig(CDN + 'cold-weather.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'maturity.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (3쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1), f2_html=b_fig(F2_NAME, alt_f2, cap_f2),
                   gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    print(json.dumps(CALC, ensure_ascii=False))
