"""19일차 터널 콘크리트 라이닝 균열의 종류·원인·억제 대책 — Q-net 답안지 위 따라쓰기 PDF(3쪽)."""
from pathlib import Path
from io import BytesIO
from copy import deepcopy
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

OUT = Path(__file__).parent
TEMPLATE = Path('/Volumes/USB256/기술사/2026기술사 답안지-1교시(안내용)_Qnet원본.pdf')
TITLE = '[토목시공기술사] 터널 라이닝 균열 종류와 원인, 균열억제 대책 | 하루 한 문제 19일차'
PDF_NAME = '19일차_라이닝균열_답안예시_따라쓰기.pdf'

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
        0: ('콘크리트 라이닝 균열의 종류·원인과 균열억제 대책', 12),
        1: ('1. 개요', 14),
        2: ('· 라이닝: 1차 지보(숏크리트·록볼트) 안쪽에', 12),
        3: ('  타설하는 내부 콘크리트', 12),
        4: ('· 작용하중보다 건조수축·온도 등 2차 원인이 많고', 12),
        5: ('  여러 원인이 복합적으로 작용함', 12),
        6: ('· 누수·백태·박락 경로 → 형태·위치로 원인 판단', 12),
        7: ('2. 균열의 종류', 14),
        14: ('· 종방향: 폭·길이가 커서 내구성 저해', 12),
        15: ('· 복합: 천단 종방향 균열이 전단 형태로 진전', 12),
        16: ('(전개도: 천단 종방향·이음부 횡방향·어깨 경사 병기)', 11),
    }
    for r, (s, z) in p1.items(): line(c, r, s, z)
    ys = [764 - 7.55 * 32.35 - i * 33 for i in range(5)]
    rule_table(c, [202, 282, 372, 605], ys, [
        ('구분', '방향', '주 발생 위치'),
        ('종방향', '축과 평행', '천단부 20° 범위, 어깨부, 갱구 쪽'),
        ('횡방향', '축에 직교', '시공이음 주변, 어깨·천단부'),
        ('전단', '대각선', '어깨부'),
    ])
    text(c, 132, 731, '1', 14)
    c.showPage()
    p2 = {
        0: ('3. 균열 원인', 14),
        1: ('(1) 재료', 12.5),
        2: ('· 두꺼운 인버트 수화열 → 내부 구속 온도균열', 12),
        3: ('· 건조수축, 슬럼프가 큰 콘크리트', 12),
        4: ('(2) 시공', 12.5),
        5: ('· 이른 탈형·양생 부족', 12),
        6: ('· 투입구 사이 타설 계면(콜드조인트)', 12),
        7: ('· S.L 부근 침강 차이, 두께 부족, 천단 배면 공동', 12),
        8: ('(3) 설계: 주철근 겹침이음 위치 집중(어깨·S.L)', 12),
        9: ('(4) 환경·하중', 12.5),
        10: ('· 대기 온도 변화 반복, 지반 팽창·편압', 12),
        11: ('· 측벽 기초 침하, 지하수압', 12),
        12: ('(5) 절리가 많은 암반', 12.5),
        13: ('· 이완하중·쐐기 하중, 편압', 12),
        14: ('· 배면 공동 → 휨모멘트 증가', 12),
        16: ('※ 원인은 형태·위치·진행성 조사로 판정', 11),
        17: ('  (균열 폭·깊이, 피복 두께, 강도, 시공 기록)', 11),
    }
    for r, (s, z) in p2.items(): line(c, r, s, z)
    text(c, 132, 731, '1', 14)
    c.showPage()
    p3 = {
        0: ('4. 균열억제 대책', 14),
        1: ('(1) 설계: 겹침이음 위치 분산, 갱구·단층대 보강,', 12),
        2: ('    배면 배수로 수압 저감', 12),
        3: ('(2) 재료: 혼화재로 수화열 저감·응결 지연,', 12),
        4: ('    단위수량·슬럼프 관리로 건조수축 저감', 12),
        5: ('(3) 타설: 숏크리트면 습윤, 좌우 대칭 타설', 12),
        6: ('· 초결 전 재다짐으로 투입구 계면 방지', 12),
        7: ('· S.L 부근 타설 일시 중지 → 침강 처리', 12),
        8: ('(4) 천단 충전: 검측공 확인, 공동 시 배면 그라우팅', 12),
        9: ('(5) 탈형·양생: 현장 양생 공시체 강도로 탈형 결정', 12),
        10: ('· 방풍막·살수 양생, 급격한 온도·건조 변화 방지', 12),
        11: ('(6) 유지관리: 폭·깊이·피복 조사, 진행성 감시,', 12),
        12: ('    교통량 고려 보수 우선순위 결정', 12),
        13: ('5. 결론', 14),
        14: ('· 비구조적 원인이 많으나 누수·박락 경로가', 12),
        15: ('  되므로 타설·양생 단계 관리가 핵심임', 12),
        16: ('· 진행하는 종방향·전단 균열은 배면 공동·편압', 12),
        17: ('  조사와 구조 검토가 필요함', 12),
        19: ('학습용 답안 예시 / 공식 정답·채점기준 아님', 11),
    }
    for r, (s, z) in p3.items(): line(c, r, s, z)
    text(c, 132, 731, '1', 14)
    c.save(); buf.seek(0)
    ov = PdfReader(buf); w = PdfWriter()
    for i in range(3):
        p = deepcopy(PdfReader(TEMPLATE).pages[4]); p.merge_page(ov.pages[i])
        if i:
            b = BytesIO(); cc = canvas.Canvas(b, pagesize=(W, H_PG)); cc.setFillColorRGB(1, 1, 1)
            cc.rect(574, 791, 45, 45, stroke=0, fill=1); text(cc, 587, 803, f'{i+1}쪽', 13, False)
            cc.save(); b.seek(0); p.merge_page(PdfReader(b).pages[0])
        w.add_page(p)
    w.add_metadata({'/Title': TITLE + ' - 따라쓰기', '/Subject': '기출 원문(2024 제132회 3교시 1번) 학습용 답안 예시. 공식 채점기준 아님. 작성 글씨 RGB 184/184/184.'})
    with (OUT / PDF_NAME).open('wb') as f: w.write(f)


if __name__ == '__main__':
    make_pdf()
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(OUT / PDF_NAME))
    for i in range(len(doc)):
        doc[i].render(scale=1.6).to_pil().save(OUT / f'_pdf_p{i+1}.png')
    print('pages', len(doc))
