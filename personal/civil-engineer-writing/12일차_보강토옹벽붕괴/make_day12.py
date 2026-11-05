"""12일차 보강토옹벽 붕괴 원인(다짐·배면수압·상재토압)과 대책 — 개념도·따라쓰기 PDF·티스토리/Blogger 본문을 만든다."""
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
TITLE = '[토목시공기술사] 보강토옹벽 붕괴 원인과 대책(다짐·배면수압·상재토압) | 하루 한 문제 12일차'
PDF_NAME = '12일차_보강토옹벽붕괴_답안예시_따라쓰기.pdf'
FIG_NAME = '보강토옹벽_붕괴원인과대책_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_랭킨토압.png', '수식2_계산예.png', '도식_배면수압토압비교.gif'
BANNER = 'banner.png'
CDN = 'https://geoai-na.web.app/civil-questions/materials/day12/'
PRET = '/Volumes/USB256/devAPP/AutoSNS/assets/FONTS/Pretendard-Bold.otf'

# ── 계산 예(가상 예시): 배면 수위 유무에 따른 수평력 ─────────────────
H, PHI, GT, GSAT, GW, Q = 6.0, 30.0, 19.0, 20.0, 9.81, 10.0
KA = math.tan(math.radians(45 - PHI / 2)) ** 2
P_DRY = 0.5 * KA * GT * H ** 2
P_Q = KA * Q * H
G_SUB = GSAT - GW
P_SUB = 0.5 * KA * G_SUB * H ** 2
P_W = 0.5 * GW * H ** 2
TOT_DRY, TOT_WET = P_DRY + P_Q, P_SUB + P_W + P_Q
CALC = {'Ka': round(KA, 4), 'P_dry': round(P_DRY, 1), 'P_q': round(P_Q, 1), 'gamma_sub': round(G_SUB, 2),
        'P_sub': round(P_SUB, 1), 'P_w': round(P_W, 1), 'total_dry': round(TOT_DRY, 1), 'total_wet': round(TOT_WET, 1),
        'ratio': round(TOT_WET / TOT_DRY, 2)}

# ── 개념도: 단면과 원인 세 갈래 ─────────────────────────────────────
def figure():
    im = Image.new('RGB', (1600, 1000), 'white'); dr = ImageDraw.Draw(im)
    f = lambda z: ImageFont.truetype(PRET, z)
    INK, TEAL, RED, GRAYC, SOFT, SOIL, BACK, WATER = '#263746', '#176977', '#B6462F', '#7A8790', '#EAF2F3', '#E9DFC9', '#D9D2C3', '#9FC9DD'
    dr.text((60, 36), '보강토옹벽 단면 — 붕괴 원인 세 갈래(축척 없음)', font=f(40), fill=INK)
    top, base, x0, x1 = 250, 820, 200, 620                      # 보강토체 윗면·밑면, 전면·보강재 끝
    dr.rectangle([60, base, 1000, 900], fill='#C9C2B2')          # 기초지반
    dr.rectangle([x1, top, 1000, base], fill=BACK)               # 배면 원지반·뒤채움
    dr.rectangle([x0, top, x1, base], fill=SOIL)                 # 보강토체
    for y in range(top + 20, base, 40):                          # 전면 블록
        dr.rectangle([x0 - 50, y - 20, x0, y + 18], fill='#B9B09E', outline=INK)
    dr.rectangle([x0, top, x0 + 24, base], fill='#CFCFC4')       # 자갈 배수층
    for y in range(top + 40, base, 80): dr.line([(x0, y), (x1 - 10, y)], fill=TEAL, width=4)   # 보강재
    # 배면 수위
    wy = 470
    dr.rectangle([x1, wy, 1000, base], fill=WATER)
    dr.line([(x1, wy), (1000, wy)], fill='#2A6F97', width=3)
    dr.polygon([(900, wy - 18), (920, wy - 18), (910, wy - 2)], fill='#2A6F97')
    dr.text((850, wy + 12), '배면 수위', font=f(22), fill='#1D4F6B')
    # 상재하중
    dr.rectangle([500, top - 70, 900, top], fill='#DCD3C0', outline=INK)
    dr.text((610, top - 58), '상부 성토·L형 옹벽', font=f(22), fill=INK)
    for x in range(520, 900, 60): dr.line([(x, top - 120), (x, top - 78)], fill=RED, width=4); dr.polygon([(x - 8, top - 86), (x + 8, top - 86), (x, top - 74)], fill=RED)
    dr.text((700, top - 155), '차량하중 q', font=f(22), fill=RED)
    dr.text((330, 520), '보강토체', font=f(30), fill=INK)
    dr.text((x1 + 30, 300), '배면 흙', font=f(26), fill=INK)
    dr.text((80, base + 20), '기초지반', font=f(24), fill=INK)
    dr.text((140, top - 34), '전면벽체·자갈 배수층', font=f(20), fill=GRAYC)
    dr.text((x0 + 230, 300), '보강재', font=f(20), fill=TEAL)

    def tag(x, y, n): dr.ellipse([x - 19, y - 19, x + 19, y + 19], fill=RED); dr.text((x - 9, y - 16), n, font=f(26), fill='white')
    tag(260, 680, '1'); tag(x1 + 40, 650, '2'); tag(465, top - 100, '3')
    rx = 1060
    items = [('1', '다짐', '다짐 부족·전면 대형장비', '→ 층 다짐·들밀도시험, 전면 소형장비'),
             ('2', '배면 수압', '세립분 많은 흙·배수층 누락', '→ 투수성 재료, 자갈필터·유공관'),
             ('3', '상재토압', '상부 성토·구조물 미반영', '→ 설계하중 반영, 전체 안정 검토')]
    dr.text((rx, 150), '원인 → 대책', font=f(26), fill=GRAYC)
    for k, (n, a, b, c) in enumerate(items):
        yy = 200 + k * 190
        dr.rounded_rectangle([rx - 10, yy - 10, rx + 510, yy + 160], 12, fill=SOFT)
        tag(rx + 22, yy + 22, n)
        dr.text((rx + 56, yy + 2), a, font=f(30), fill=INK)
        dr.text((rx + 10, yy + 58), b, font=f(23), fill=RED); dr.text((rx + 10, yy + 104), c, font=f(23), fill=TEAL)
    dr.text((60, 940), '직접 작성한 개념도 / 근거: KDS 11 80 10:2021(제3자 요약), 한국산학기술학회논문지 14(4) 2013, 국토부 사고조사 결과 보도(2026.2)', font=f(21), fill=GRAYC)
    im.save(OUT / FIG_NAME, quality=92)

# ── 따라쓰기 PDF ─────────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('KR', '/System/Library/Fonts/Supplemental/AppleGothic.ttf'))
tp = PdfReader(TEMPLATE).pages[4]
W, H_PG = float(tp.mediabox.width), float(tp.mediabox.height)
GRAY = 184 / 255

def text(c, x, y, s, size=12.5, gray=True):
    c.setFillColorRGB(*((GRAY,) * 3 if gray else (.12,) * 3)); c.setFont('KR', size); c.drawString(x, y, s)

def line(c, row, s, size=12.5):
    assert pdfmetrics.stringWidth(s, 'KR', size) < 405, s
    text(c, 202, 764 - row * 32.35, s, size)

def rule_table(c, xs, ys, cells, sizes=(11, 10.5)):
    """표 내용은 칸 가운데 정렬."""
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(.9)
    for x in xs: c.line(x, ys[-1], x, ys[0])
    for y in ys: c.line(xs[0], y, xs[-1], y)
    for i, row in enumerate(cells):
        for j, s in enumerate(row):
            z = sizes[0] if j == 0 else sizes[1]
            wd = pdfmetrics.stringWidth(s, 'KR', z)
            assert wd < xs[j + 1] - xs[j] - 8, s
            text(c, (xs[j] + xs[j + 1]) / 2 - wd / 2, ys[i] - 20, s, z)

def section(c, gy):
    """2쪽 원인 위치 모식도(축척 없음). gy 는 기초면 높이."""
    c.setStrokeColorRGB(GRAY, GRAY, GRAY); c.setLineWidth(1.1)
    tp_ = gy + 120; x0, x1 = 260, 420
    c.line(202, gy, 605, gy)
    c.rect(x0 - 14, gy, 14, 120, stroke=1, fill=0)                       # 전면벽체
    c.rect(x0, gy, x1 - x0, 120, stroke=1, fill=0)                       # 보강토체
    for y in range(int(gy) + 18, int(tp_), 22): c.line(x0, y, x1 - 8, y)  # 보강재
    c.setDash(3, 2); c.line(x1, gy + 60, 600, gy + 60); c.setDash()       # 배면 수위
    c.rect(440, tp_, 140, 18, stroke=1, fill=0)                           # 상재
    for x in (505, 535, 565): c.line(x, tp_ + 40, x, tp_ + 21)
    text(c, 300, gy + 47, '①다짐', 10); text(c, 470, gy + 30, '②배면 수압', 10)
    text(c, 440, tp_ + 24, '③상재하중', 10); text(c, 205, gy + 55, '전면벽체', 9.5)
    text(c, 320, gy + 91, '보강재', 9.5); text(c, 540, gy + 65, '수위', 9.5)

def make_pdf():
    buf = BytesIO(); c = canvas.Canvas(buf, pagesize=(W, H_PG))
    p1 = {
        0: ('보강토옹벽 붕괴 원인(다짐·배면수압·상재토압)·대책', 12),
        1: ('1. 개요', 14),
        2: ('· 구성: 전면벽체 + 보강재 + 뒤채움 보강토체 + 배수', 12),
        3: ('· 흙-보강재 마찰·인발저항으로 토압에 저항', 12.5),
        4: ('· 외적안정(활동·전도·지지력·전체안정)과 내적안정', 12),
        5: ('  (보강재 파단·인발) 상실 시 붕괴', 12.5),
        6: ('· 다짐·배수·상재하중이 겹쳐 작용하는 경우 많음', 12),
        7: ('2. 붕괴 형태', 14),
        14: ('3. 원인 분석', 14),
        15: ('(1) 다짐 측면', 12.5),
        16: ('· 다짐 부족 → 보강토체 침하, 보강재 마찰 저하', 12),
        17: ('· 침하로 배수관 휨·기능 상실 → 빗물 유입 확대', 12),
        18: ('· 전면 가까이 대형장비 다짐 → 벽체 밀림·배부름', 12),
        19: ('· 층두께 과다, 함수비 관리 미흡, 이물질 혼입', 12),
        20: ('(2) 보강토체 배면 수압 측면', 12.5),
        21: ('· 세립분 많은 흙 → 투수성 저하, 배면 수압 발생', 12),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    text(c, 132, 731, '3', 14)
    ys = [764 - 7.45 * 32.35 - i * 30 for i in range(6)]
    rule_table(c, [202, 280, 430, 605], ys, [
        ('구분', '형태', '주요 징후'),
        ('외적', '활동·전도·지지력', '전면 밀림·기울어짐'),
        ('내적', '보강재 파단·인발', '배부름·블록 균열'),
        ('전체', '전체 사면활동', '상부 땅꺼짐·침하'),
        ('국부', '전면벽체 탈락', '블록 이탈·흙 유출'),
    ], sizes=(10.5, 10.5))
    c.showPage()
    p2 = {
        0: ('· 상부 배수로·포장 균열 → 빗물 지속 유입', 12),
        1: ('· 포화 → 수평력 증가, 유효응력·전단강도 저하', 12),
        2: ('· 전면 배수층(자갈필터) 누락 → 블록 틈 흙 유출', 12),
        3: ('(3) 상재토압 측면', 12.5),
        4: ('· 상부 성토사면·L형 옹벽·차량하중 미반영', 12),
        5: ('· 상재하중 → 수평토압·보강재 인장력 증가', 12),
        6: ('· 2단·복합구조에서 전체 사면활동 검토 누락', 12),
        7: ('4. 계산 예(가상 예시) — 배면 수압 영향', 13),
        8: ('H=6m, φ=30°, γt=19, γsat=20, γw=9.81, q=10kPa', 11.5),
        9: ('Ka = tan²(45°-φ/2) = 1/3 (Rankine, 벽마찰 무시)', 12),
        10: (f'배수 정상: ½KaγtH² = {P_DRY:.1f}, KaqH = {P_Q:.1f}', 12),
        11: (f'  → 합계 {TOT_DRY:.1f} kN/m', 12.5),
        12: (f"배면 만수: ½Kaγ'H² = {P_SUB:.1f}, ½γwH² = {P_W:.1f}", 12),
        13: (f'  → 합계 {TOT_WET:.1f} kN/m (약 {TOT_WET / TOT_DRY:.1f}배)', 12.5),
        14: ('※ 가상값. 배면 수위가 벽 높이까지 찬 극단 가정', 11),
        15: ('■ 그림. 원인별 위치(모식도)', 12.5),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    section(c, 764 - 21 * 32.35 + 8)
    text(c, 132, 731, '3', 14)
    c.showPage()
    p3 = {
        0: ('5. 대책', 14),
        1: ('(1) 다짐', 12.5),
        2: ('· 층별 다짐두께 관리, 들밀도시험으로 다짐도 확인', 12),
        3: ('· 전면 가까이는 소형 다짐장비 사용', 12),
        4: ('· 이물질 제거, 함수비 관리, 보강재 평탄 포설', 12),
        5: ('(2) 배수·수압', 12.5),
        6: ('· 투수성 양호한 뒤채움재(KCS 11 80 10 2.1.3)', 12),
        7: ('· 전면벽체 배면 자갈필터층 0.3m 이상', 12),
        8: ('· 밑면·배면 배수층, 유공관을 외부 배수로에 연결', 12),
        9: ('· 상부 배수로·포장 균열 보수, 빗물 유입 차단', 12),
        10: ('(3) 상재토압', 12.5),
        11: ('· 상재하중·복합구조를 설계하중에 반영', 12),
        12: ('· 보강재 길이·간격과 전체 사면안정 검토', 12),
        13: ('· 준공 뒤 상부 성토·구조물 추가 시 재검토', 12),
        14: ('(4) 유지관리', 12.5),
        15: ('· 배부름·균열·배수구 막힘 정기 점검', 12),
        16: ('· 전면 변위·상부 침하 계측으로 변화 추적', 12),
        17: ('6. 결론', 14),
        18: ('· 다짐 불량·배수 불량·상재하중이 겹치면 붕괴', 12),
        19: ('· 재료·다짐·배수를 시공 단계에서 확인하고', 12),
        20: ('  하중이 바뀌면 다시 검토하는 관리가 핵심임', 12),
        21: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
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
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2026 제140회 4교시 3번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)

# ── 본문 ─────────────────────────────────────────────────────────────
Q = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq={}&brdId=Q006&gSite=Q'
Q137, Q138, Q139, Q140 = (Q.format(s) for s in (5242759, 5253570, 5263570, 5274160))
SOURCES = [
    ('KDS 11 80 10:2021 보강토옹벽 — 3.1.1(1) 전면벽체 주변 다짐 응력, 3.1.3 뒤채움재료(KCS 11 80 10 2.1.3 준용)·유효전단강도정수, 4.1.1 보강재 길이, 4.8 배수(자갈필터층 0.3 m 이상, 수중 시 내외수면 같게). 국가건설기준센터 원문은 열지 못해 제3자 요약 페이지로 확인', 'https://nogada.kwoody01.com/156'),
    ('국가건설기준센터 — KDS 11 80 10, KCS 11 80 10 원문 조회처(이 글에서 원문 대조 못 함)', 'https://www.kcsc.re.kr/'),
    ('김병일·유완규·김경모·이봉열, 「블록식 보강토옹벽의 붕괴사례 연구」, 한국산학기술학회논문지 제14권 제4호(2013), pp.2006~2012', 'https://doi.org/10.5762/KAIS.2013.14.4.2006'),
    ('뉴스서울, 「국토교통부, 오산 보강토옹벽 붕괴사고 조사 결과」(2026.2.26) — 중앙시설물사고조사위원회 발표 보도', 'https://www.newsseoul.co.kr/news/view/1065605418924837'),
    ('머니투데이, 오산 옹벽 붕괴 사고조사 결과 보도(2026.2.26)', 'https://www.mt.co.kr/estate/2026/02/26/2026022609525831573'),
    ('FHWA Federal Lands FP-14 Section 255 Mechanically-Stabilized Earth Walls(벽면 900 mm 이내 경량 다짐기 조항, 검색 발췌로 확인·원문 파일은 열지 못함)', 'https://highways.fhwa.dot.gov/federal-lands/specs/wfl-los/fp-14-library/255fp14.docx'),
]
C = ' style="text-align:center"'

def tr(cells, th=False):
    t = 'th' if th else 'td'
    return '<tr>' + ''.join(f'<{t}{C}>{x}</{t}>' for x in cells) + '</tr>'

def table(rows):
    return ('<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">\n'
            + tr(rows[0], True) + '\n' + '\n'.join(tr(r) for r in rows[1:]) + '\n</table>')

def body(img_html, f1_html, f2_html, gif_html, pdf_html, banner_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    t_form = table([('구분', '붕괴 형태', '주요 징후'),
                    ('외적안정', '활동·전도·지지력 부족', '전면 밀림, 벽체 기울어짐'),
                    ('내적안정', '보강재 파단·인발', '전면 배부름, 블록 균열'),
                    ('전체안정', '보강토체를 포함한 사면활동', '상부 땅꺼짐·침하'),
                    ('국부', '전면벽체 탈락', '블록 이탈, 틈으로 흙 유출')])
    t_cause = table([('측면', '원인', '붕괴로 이어지는 과정'),
                     ('다짐', '다짐 부족, 층두께 과다, 이물질 혼입', '보강토체 침하 → 보강재 마찰 저하·배수관 변형'),
                     ('다짐', '전면 가까이 대형장비 다짐', '전면벽체 밀림·배부름'),
                     ('배면 수압', '세립분 많은 뒤채움, 배수층 누락', '포화·수압 → 수평력 증가, 전단강도 저하'),
                     ('배면 수압', '상부 배수로·포장 균열', '빗물 지속 유입 → 뒤채움 약화'),
                     ('상재토압', '상부 성토·L형 옹벽·차량하중 미반영', '수평토압·보강재 인장력 증가'),
                     ('상재토압', '2단·복합구조 전체 안정 검토 누락', '보강토체를 지나는 사면활동')])
    t_calc = table([('항목', '배수 정상(수위 없음)', '배면 만수(수위 = H)'),
                    ('흙의 단위중량', 'γ<sub>t</sub> = 19 kN/m³', "γ' = 20 − 9.81 = 10.19 kN/m³"),
                    ('흙 토압 ½K<sub>a</sub>γH²', f'{P_DRY:.1f} kN/m', f'{P_SUB:.1f} kN/m'),
                    ('수압 ½γ<sub>w</sub>H²', '—', f'{P_W:.1f} kN/m'),
                    ('상재 K<sub>a</sub>qH', f'{P_Q:.1f} kN/m', f'{P_Q:.1f} kN/m'),
                    ('수평력 합계', f'{TOT_DRY:.1f} kN/m', f'{TOT_WET:.1f} kN/m (약 {TOT_WET / TOT_DRY:.1f}배)')])
    t_sym = table([('기호', '뜻', '단위', '출처'),
                   ('K<sub>a</sub>', 'Rankine 주동토압계수 tan²(45° − φ/2)', '무차원', 'Rankine 토압 일반식'),
                   ('φ', '뒤채움 흙의 내부마찰각', '°', '가정값'),
                   ('γ<sub>t</sub>, γ<sub>sat</sub>, γ\'', '습윤·포화·수중 단위중량', 'kN/m³', '가정값, γ\' = γ<sub>sat</sub> − γ<sub>w</sub>'),
                   ('γ<sub>w</sub>', '물의 단위중량', 'kN/m³', '9.81 사용'),
                   ('H', '벽 높이', 'm', '가정값'),
                   ('q', '등분포 상재하중', 'kPa', '가정값'),
                   ('P', '벽 1 m 폭당 수평력', 'kN/m', '계산값')])
    return f'''{banner_html}<p>보강토옹벽은 2025년 제137회부터 2026년 제140회까지 네 회 연속 논술형으로 나왔어요. 가장 최근 문제인 제140회 4교시 3번은 다짐, 보강토체 배면 수압, 상재토압이라는 세 측면을 직접 정해 줬어요. 답안도 이에 맞춰 세 갈래로 나눠 원인과 대책을 짝지어 쓰면 돼요. 설계 기준은 KDS 11 80 10:2021을 제3자 요약으로 확인했고, 국가건설기준센터 원문과 뒤채움재 수치 기준(KCS 11 80 10)은 직접 대조하지 못했습니다.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.web.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>
<h2 data-ke-size="size26">오늘의 문제</h2>
<p><strong>시험 종목: 토목시공기술사 / 과목(학습 분류): 옹벽·지반(보강토) / 유형: 논술형 / 관련 기출: 2026년 제140회 4교시 3번</strong></p>
<blockquote>보강토옹벽(Reinforced Earth Wall)의 붕괴에 영향을 미치는 원인을 다짐, 보강토체 배면수압 및 상재토압 측면에서 분석하고 그 대책방안에 대하여 설명하시오.</blockquote>
<p>위 문제는 2026년 제140회 4교시 3번 기출 원문이에요. 답안예시는 학습용으로 쓴 것이라 공식 정답이나 채점기준이 아닙니다. 연습은 목차 3분, 작성 22분, 답안지 3쪽 정도를 권해요. 학습 분류와 시간·분량은 연습용 안내일 뿐 공식 시험 과목명이나 기준이 아닙니다.</p>
<h3 data-ke-size="size23">출제 흐름과 이번 주제</h3>
<p>2022~2026년 제126~140회 465문항 가운데 보강토옹벽을 직접 물은 문항은 다음 네 개예요.</p>
<ul><li>2025년 제137회 3교시 1번: <a href="{Q137}">보강토 옹벽의 배부름 현상의 발생원인과 시공대책 및 시공 시 유의사항</a></li>
<li>2026년 제138회 4교시 2번: <a href="{Q138}">보강토 옹벽의 안정 검토 방법과 시공 시 유의사항</a></li>
<li>2026년 제139회 4교시 2번: <a href="{Q139}">보강토옹벽 시공 시 뒤채움재료 선정기준 및 다짐관리 기준</a></li>
<li>2026년 제140회 4교시 3번: <a href="{Q140}">보강토옹벽의 붕괴에 영향을 미치는 원인(다짐·배면수압·상재토압)과 대책방안</a></li></ul>
<p>문항 제목은 일부 줄여 적었으니 정확한 표현은 Q-net 문제지에서 확인해 주세요. '네 회 연속'은 문제 제목을 하나씩 대조해 센 결과이고, 공식 출제 비중을 뜻하지는 않습니다. 같은 기간 '옹벽'이 들어간 문항은 9개였어요. 앞선 세 문제(배부름, 안정 검토, 뒤채움·다짐)의 내용이 이번 답안의 원인·대책에 고루 들어가므로, 이 글 하나로 네 문제를 함께 대비하도록 짰습니다. 10일차 하천제방, 11일차 연약지반 계측과는 대상 구조물이 달라 겹치지 않아요.</p>
<blockquote><p><strong>답안 작성 요령</strong> — 문제가 분석 측면을 지정하면 그 낱말을 그대로 소제목으로 세운다. 이번 문제는 '다짐 / 보강토체 배면수압 / 상재토압'을 원인 장의 소제목으로 두고, 대책 장도 같은 순서로 맞춘다. 원인과 대책의 순서가 같으면 채점자가 짝을 쉽게 찾는다. 붕괴 형태(외적·내적·전체 안정)를 먼저 한 표로 정리하면 각 원인이 어느 파괴로 이어지는지 화살표 하나로 연결할 수 있다.</p></blockquote>
<hr>
<h2 data-ke-size="size26">답안 목차</h2>
<p>1. 개요 → 2. 붕괴 형태 → 3. 원인 분석(다짐·배면수압·상재토압) → 4. 계산 예 → 5. 대책 → 6. 결론</p>
<h2 data-ke-size="size26">답안예시</h2>
<h3 data-ke-size="size23">1. 개요</h3>
<ul><li>보강토옹벽: 전면벽체, 보강재(띠형·그리드형·토목섬유), 뒤채움 보강토체, 배수시설로 구성됨</li>
<li>흙과 보강재 사이의 마찰·인발저항으로 배면 토압에 저항하는 구조임</li>
<li>외적안정(활동·전도·지지력·전체안정) 또는 내적안정(보강재 파단·인발)을 잃으면 붕괴함</li>
<li>다짐 불량, 배면 수압, 상재하중 증가가 서로 겹쳐 작용하는 경우가 많음</li></ul>
<h3 data-ke-size="size23">2. 붕괴 형태</h3>
{t_form}
<h3 data-ke-size="size23">3. 원인 분석</h3>
{img_html}
<p><strong>(1) 다짐 측면</strong></p>
<ul><li>다짐 부족: 보강토체 침하, 흙과 보강재 사이 마찰 저하로 인발저항 감소</li>
<li>보강토체 침하로 내부 배수관이 휘어 기능 상실 → 빗물이 다짐 불량 토체로 유입</li>
<li>전면 가까이 대형장비 다짐: 다짐 응력이 전면벽체를 밀어 배부름·블록 어긋남 발생</li>
<li>층두께 과다, 함수비 관리 미흡, 콘크리트 조각 등 이물질 혼입</li></ul>
<p><strong>(2) 보강토체 배면 수압 측면</strong></p>
<ul><li>세립분이 많은 흙을 뒤채움에 사용: 투수성 저하로 물이 빠지지 않아 수압 발생</li>
<li>상부 배수로·포장면 균열로 빗물이 지속적으로 유입되어 뒤채움 약화</li>
<li>포화 시 수평력 증가, 유효응력 감소로 전단강도·보강재 마찰저항 저하</li>
<li>전면벽체 배면 자갈 배수층 누락 시 블록 틈으로 흙 유출, 배부름 진행</li></ul>
<p><strong>(3) 상재토압 측면</strong></p>
<ul><li>상부 성토사면, 옹벽 위 L형 옹벽, 차량하중 등 상재하중을 설계에 미반영</li>
<li>상재하중 증가 → 수평토압과 보강재 인장력 증가 → 파단·인발 위험</li>
<li>2단·복합구조에서 보강토체를 지나는 전체 사면활동 검토 누락</li></ul>
{t_cause}
<h3 data-ke-size="size23">4. 계산 예 (가상 예시) — 배면 수압의 영향</h3>
<ul><li>가정: 벽 높이 H = 6 m, 뒤채움 φ = 30°, c = 0, γ<sub>t</sub> = 19 kN/m³, γ<sub>sat</sub> = 20 kN/m³, γ<sub>w</sub> = 9.81 kN/m³, 상재하중 q = 10 kPa</li>
<li>보강토체 배면에 작용하는 수평력(외적안정용)을 Rankine 주동토압으로 산정, 벽마찰 무시</li>
<li>비교: 배수 정상(수위 없음)과 배면 수위가 벽 높이까지 찬 극단 경우</li></ul>
{f1_html}
{t_calc}
{f2_html}
<ul><li>배수가 막혀 배면이 만수가 되면 흙 토압은 줄지만 수압이 더해져 수평력이 약 1.9배로 증가함</li>
<li>보강토체 밑면의 유효응력도 줄어 활동저항이 함께 감소함</li></ul>
{gif_html}
<h3 data-ke-size="size23">5. 대책</h3>
<p><strong>(1) 다짐</strong></p>
<ul><li>층별 다짐두께 관리, 들밀도시험으로 다짐도 확인(재시공 사례: 층당 0.2~0.3 m 이하, 상대다짐도 95% 이상)</li>
<li>전면벽체 가까이는 소형 다짐장비 사용, 전면 다짐 응력에 대한 안정성 확보</li>
<li>이물질 제거, 최적함수비 부근 관리, 보강재를 평탄하게 펴서 포설</li></ul>
<p><strong>(2) 배수·수압</strong></p>
<ul><li>투수성이 양호한 뒤채움재 사용(KCS 11 80 10 2.1.3 기준 준수), 세립분 많은 현장 유용토 사용 제한</li>
<li>전면벽체 배면에 자갈필터층 0.3 m 이상 설치</li>
<li>보강토체 밑면·배면 배수층과 유공관을 두고 외부 배수로에 연결</li>
<li>상부 배수로·포장면 균열 보수로 빗물 유입 차단, 수중 구간은 내외수면이 같아지도록 투수성 재료 사용</li></ul>
<p><strong>(3) 상재토압</strong></p>
<ul><li>상부 성토·L형 옹벽·차량하중 등 상재하중을 설계하중에 반영</li>
<li>보강재 길이·간격 재검토, 2단·복합구조는 전체 사면안정 검토</li>
<li>준공 뒤 상부 성토나 구조물을 더할 때 안정성 재검토</li></ul>
<p><strong>(4) 유지관리</strong></p>
<ul><li>배부름·균열·배수구 막힘을 정기 점검하고 결함을 즉시 보수</li>
<li>전면 수평변위·상부 침하 계측으로 변화 추적</li></ul>
<h3 data-ke-size="size23">6. 결론</h3>
<ul><li>보강토옹벽 붕괴는 다짐 불량, 배수 불량에 따른 배면 수압, 설계에 반영하지 않은 상재하중이 겹쳐 발생함</li>
<li>재료·다짐·배수를 시공 단계에서 시험으로 확인하고, 하중 조건이 바뀌면 다시 검토하는 관리가 핵심임</li></ul>
<hr>
<h2 data-ke-size="size26">해설 — 근거와 해석</h2>
<p>답안의 원인 항목은 실제 붕괴 조사 결과와 겹쳐요. 2013년 한국산학기술학회논문지의 블록식 보강토옹벽 붕괴사례 연구는 철거한 단면에서 빈 공간을 눈으로 확인했고, 다짐불량에 따른 침하를 가장 큰 원인으로 판단했습니다. 같은 연구는 보강토체가 가라앉으면서 내부 배수관이 휘어 기능을 잃었고, 전면판 뒤 배수층과 외부 배수시설이 없었으며, 기초지반 지지력 검토와 2단 옹벽의 전체 사면활동 검토가 빠졌다고 적었어요. 대책의 '층당 0.2~0.3 m, 상대다짐도 95% 이상'은 이 논문이 해당 현장의 재시공안으로 제시한 값이라, 모든 현장의 공식 기준으로 옮겨 쓰지는 마세요. 사례 하나에서 나온 값이라는 한계도 있습니다.</p>
<p>최근 사례로는 2025년 7월 경기 오산 보강토옹벽 붕괴가 있어요. 2026년 2월 26일 보도에 따르면 국토교통부 중앙시설물사고조사위원회는 상부 배수로와 포장면 균열로 빗물이 계속 들어가 뒤채움재가 약해졌고, 사고 직전 시간당 39.5 mm의 집중호우 때 배수가 되지 않아 수압이 가중되어 무너진 것으로 판단했습니다. 시공 단계에서는 세립분이 많은 흙을 뒤채움재로 썼고, 설계 단계에서는 옹벽 위 L형 옹벽 복합구조의 위험도 분석과 배수 설계가 미흡했다고 보았어요. 이 내용은 보도로 확인한 것이고 국토부 보도자료 원문은 열어 보지 못했습니다. 보도로 보면 직접 원인은 배수 불량에 따른 수압이었고, 뒤채움재 품질과 상부 L형 옹벽 복합구조 문제가 함께 지적됐어요. 이번 문제의 세 측면과 겹치는 부분이 있지만, 출제 의도는 공개되지 않았으니 필자의 해석으로 읽어 주세요.</p>
<p>기준 쪽에서는 KDS 11 80 10:2021이 다량의 배면 유입수로 뒤채움 흙이 포화되면 전단강도가 급격히 떨어질 수 있다고 경고하고, 전면벽체 배면에 두께 0.3 m 이상 자갈필터층을 두도록 하며, 벽체 시공 중 전면벽체 주변의 다짐 응력에도 안정성을 확보하라고 해요(제3자 요약 페이지로 확인). 전면 가까이 소형 장비를 쓰는 관행은 미국 연방도로청(FHWA) 연방토지 시방서 FP-14 255절이 벽면 900 mm 이내에서 경량 다짐기를 쓰도록 한 예가 있지만, 국내 시방서의 거리 기준은 확인하지 못했습니다. 뒤채움재의 입도·세립분·소성지수 수치는 KCS 11 80 10(2.1.3)에 있는데 원문을 대조하지 못해 이 글에는 적지 않았어요. 답안에 수치를 쓰려면 현행 KCS 원문을 먼저 확인해 주세요.</p>
<p>계산 예는 설명을 위해 만든 가상 조건이에요. 배면 수위가 벽 높이까지 찬 경우는 일부러 극단으로 잡은 것이고, 실제 설계는 보강토체 자체의 무게와 밑면 마찰, 보강재 인발저항까지 함께 따집니다. 그래도 같은 벽에서 배수 하나로 수평력이 두 배 가까이 달라진다는 점은 답안에서 배수를 강조하는 근거로 쓸 만합니다.</p>
<h2 data-ke-size="size26">핵심 암기어</h2>
<p>외적·내적·전체 안정 · 다짐 부족과 전면 대형장비 · 세립분·배수층 누락·빗물 유입 · 상재하중·복합구조 · 자갈필터 0.3 m · 만수 시 수평력 약 1.9배(가상 예시)</p>
<h2 data-ke-size="size26">답안 자가점검</h2>
<ul><li>원인 장의 소제목을 문제의 세 측면(다짐·배면수압·상재토압)으로 그대로 세웠나요?</li>
<li>원인과 대책을 같은 순서로 짝지어 썼나요?</li>
<li>붕괴 형태(외적·내적·전체 안정)와 원인을 연결했나요?</li>
<li>배수 대책에 재료(투수성), 시설(자갈필터·유공관), 상부 유입 차단을 모두 넣었나요?</li>
<li>제139회형(뒤채움·다짐 기준) 문제라면 KCS 원문 수치를 확인해 표로 쓸 준비가 되어 있나요?</li></ul>
<h2 data-ke-size="size26">기호·단위 정리</h2>
{t_sym}
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 형식의 3쪽 따라쓰기 PDF예요. 붕괴 형태 표, 원인 분석, 계산 예, 원인 위치 모식도, 대책이 옅은 회색 글씨로 들어 있어 출력해서 그대로 따라 쓸 수 있습니다.</p>
<h2 data-ke-size="size26">참고자료</h2>
<ul>{src}</ul>
<p>관련 기출 링크는 Q-net 회차별 문제지 게시글이에요. 자료 확인일은 2026년 10월 28일입니다. KDS 11 80 10은 2021년판을 기준으로 옮겼고, 이후 개정 여부는 국가건설기준센터 원문에서 확인하지 못했어요. 국토부는 사고 뒤 배수시설 설계기준 강화와 복합구조 기준 마련을 추진한다고 밝혔으니(2026년 2월 보도), 시험 전에 개정 여부를 다시 확인해 주세요.</p>
<p>#토목시공기술사 #보강토옹벽 #배면수압 #상재토압 #뒤채움다짐 #배수대책 #하루한문제</p>'''

if __name__ == '__main__':
    figure(); make_pdf()
    cap_img = '직접 작성한 개념도. 보강토옹벽 단면에 다짐·배면 수압·상재하중 세 원인의 위치와 대책을 짝지어 정리했다.'
    alt_img = '전면벽체·보강재·보강토체·배면 흙 단면 위에 ① 다짐, ② 배면 수위와 수압, ③ 상부 성토와 차량하중을 표시하고 원인별 대책을 정리한 개념도'
    alt_f1 = "K_a = tan^2(45° − φ/2), P_a = ½ K_a γ H², P_q = K_a q H, P_w = ½ γ_w H²"
    alt_f2 = (f"K_a = 1/3, 배수 정상: ½(1/3)(19)(6²) = {P_DRY:.1f}, (1/3)(10)(6) = {P_Q:.1f}, 합계 {TOT_DRY:.1f} kN/m; "
              f"배면 만수: γ' = 10.19, ½(1/3)(10.19)(6²) = {P_SUB:.1f}, ½(9.81)(6²) = {P_W:.1f}, 합계 {TOT_WET:.1f} kN/m, 약 {TOT_WET / TOT_DRY:.2f}배")
    alt_gif = f'가상 예시 벽 높이 6 m에서 배수 정상일 때 수평력 {TOT_DRY:.1f} kN/m인 토압 분포가 배면 수위가 차오르며 흙 토압·수압·상재압으로 나뉘어 {TOT_WET:.1f} kN/m로 커지는 도식'
    cap_f1 = '수식 1. Rankine 주동토압과 수압'
    cap_f2 = '수식 2. 계산 예(가상 예시)'
    cap_gif = '도식. 배면 수위에 따른 수평력 변화 — 학습용 가정값'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(banner_html=f'<p data-ax-attach="{BANNER}"></p>\n', img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'water-pressure.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(banner_html=f'<p><img src="{CDN}banner.png" alt="{TITLE}" style="max-width:100%;height:auto"></p>\n',
                   img_html=b_fig(CDN + 'causes.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'water-pressure.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (3쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(banner_html=f'<p><img src="{BANNER}" alt="배너"></p>', img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1),
                   f2_html=b_fig(F2_NAME, alt_f2, cap_f2), gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    print(json.dumps(CALC, ensure_ascii=False))
