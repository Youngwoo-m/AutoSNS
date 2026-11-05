"""14일차 비탈면의 붕괴원인과 방지대책 — 티스토리/Blogger 본문·미리보기·제목을 만든다(그림은 fig.py, PDF 는 make_pdf.py,
수식 PNG·GIF 는 dept/naver-blog-auto/math_gif/civil_day14.py)."""
from pathlib import Path
import json
import math

OUT = Path(__file__).parent
TITLE = '[토목시공기술사] 비탈면·산사태 붕괴 원인과 방지대책 | 하루 한 문제 14일차'
PDF_NAME = '14일차_비탈면붕괴_답안예시_따라쓰기.pdf'
FIG_NAME = '비탈면_붕괴형태_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_무한사면안전율.png', '수식2_계산예.png', '도식_지하수위안전율.gif'
BANNER = 'banner.png'
CDN = 'https://geoai-na.netlify.app/civil-questions/materials/day14/'
QNET = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq={}&brdId=Q006&gSite=Q'

SOURCES = []          # (제목, 주소) — sources.py
exec((OUT / 'sources.py').read_text())

# 가상 예시(무한사면) — 본문·수식·GIF·PDF 가 모두 이 값을 쓴다
Z, BETA, C, PHI, GT, GS, GW = 2.0, 30.0, 5.0, 35.0, 18.0, 19.0, 9.81


def fs(m):
    b, p = math.radians(BETA), math.radians(PHI)
    g = (1 - m) * GT + m * GS
    u = m * GW * Z * math.cos(b) ** 2
    res = C + (g * Z * math.cos(b) ** 2 - u) * math.tan(p)
    drv = g * Z * math.sin(b) * math.cos(b)
    return dict(m=m, gamma=g, u=round(u, 2), resist=round(res, 2), drive=round(drv, 2), fs=round(res / drv, 2))


CALC = [fs(0), fs(0.5), fs(1)]
F0, F5, F1 = (x['fs'] for x in CALC)

C_ = ' style="text-align:center"'


def tr(cells, th=False):
    t = 'th' if th else 'td'
    return '<tr>' + ''.join(f'<{t}{C_}>{x}</{t}>' for x in cells) + '</tr>'


def table(rows):
    return ('<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">\n'
            + tr(rows[0], True) + '\n' + '\n'.join(tr(r) for r in rows[1:]) + '\n</table>')


def body(banner_html, img_html, f1_html, f2_html, gif_html, pdf_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    t_type = table([('붕괴 형태', '주로 생기는 곳', '움직임'),
                    ('원호 활동', '흙·풍화토 비탈면', '휘어진 활동면을 따라 한 덩어리로 미끄러짐'),
                    ('평면 파괴', '암반 비탈면', '비탈면 쪽으로 기운 절리 하나를 따라 미끄러짐'),
                    ('쐐기 파괴', '암반 비탈면', '교차하는 절리 두 개 사이의 쐐기가 빠짐'),
                    ('전도 파괴', '암반 비탈면', '비탈 안쪽으로 급하게 기운 절리로 갈라진 기둥 암괴가 넘어짐'),
                    ('표층 유실', '얕은 토층', '집중호우 때 표면 흙이 쓸려 내려감')])
    t_fs = table([('구분', '깎기 비탈면', '일반 쌓기 비탈면', '해석 조건'),
                  ('건기', '1.5', '1.5', '지하수 없음'),
                  ('우기', '1.2 / 1.3', '1.3', '깎기: 지하수위 결정 해석 1.2, 강우침투 해석 1.3'),
                  ('지진 시', '1.1', '1.1', ''),
                  ('단기', '1.1', '1.1', '1년 미만·시공 중')])
    t_calc = table([('지하수 비율 m', '단위중량 γ (kN/m³)', '간극수압 u (kPa)', '저항 (kPa)', '활동 (kPa)', '안전율 Fs')]
                   + [(f"{x['m']:g}", f"{x['gamma']:g}", f"{x['u']:.2f}", f"{x['resist']:.2f}", f"{x['drive']:.2f}", f"{x['fs']:.2f}")
                      for x in CALC])
    return f'''{banner_html}<p>안녕하세요, 오늘은 비탈면이 왜 무너지는지(붕괴원인)와 어떻게 막는지(방지대책)를 묻는 기출이에요. 마침 경북매일은 2017년부터 올해 7월까지 전국 일반국도 비탈면 붕괴 위험 점검·조사 요청이 2,653건이었고, 그중 경북이 803건(30.3%)으로 가장 많았다고 보도했어요(경북매일, 2026년 9월 9일). 실제 사고 건수가 아니라 점검·조사를 요청한 건수이고, 유형별로는 표층유실이 915건(34.5%)으로 가장 많았어요. 우기마다 산사태와 함께 되풀이되는 일이라 시험에도 자주 나와요.</p>
<h2 data-ke-size="size26">문제</h2>
<p>기출문제: 2024년 제133회 토목시공기술사 제2교시 5번 (<a href="{QNET.format(5213322)}">Q-net 공식 문제지</a>)</p>
<blockquote><p>비탈면의 붕괴원인과 방지대책에 대하여 설명하시오. (25점)</p></blockquote>
<p>논술형 · 25점 · 권장 작성시간 25분, 분량 3쪽 안팎</p>
<h2 data-ke-size="size26">출제 의도와 답안 방향</h2>
<p>비탈면은 거의 해마다 이름을 바꿔 가며 나와요. 2022년 제126회 2교시 4번은 절토사면 시공관리와 붕괴원인, 2023년 제129회 1교시 3번은 사면붕괴의 내적·외적 원인(단답형), 2025년 제135회 4교시 3번은 붕괴형태와 안정공법, 같은 해 제137회 2교시 6번은 극한호우 때 산사태 원인과 비탈면 안정공법을 물었어요. 붕괴 형태, 원인, 대책을 한 흐름으로 묶어 두면 비슷한 문제 대부분에 그대로 쓸 수 있어요. 원인은 내적(저항력이 줄어듦)과 외적(작용력이 커짐)으로 나누고, 대책은 억제공과 억지공으로 나눈 뒤 형태별로 어떤 공법이 먼저인지 짝지어 주면 답안의 뼈대가 서요.</p>
<h2 data-ke-size="size26">비탈면은 왜 무너질까</h2>
<p>비탈면에는 흙이나 암괴를 아래로 끌어내리는 힘(활동력)과 버티는 힘(전단저항력)이 함께 작용해요. 안전율은 버티는 힘을 끌어내리는 힘으로 나눈 값이고, 1보다 작아지면 무너져요. 그래서 붕괴 원인은 결국 두 가지예요. 버티는 힘이 줄어들거나(내적 원인), 끌어내리는 힘이 커지거나(외적 원인)요.</p>
{img_html}
<h3 data-ke-size="size23">붕괴 형태 다섯 가지</h3>
{t_type}
<p>흙 비탈면은 대개 원호 모양으로 미끄러지고, 암반 비탈면은 절리·층리 같은 불연속면의 방향이 형태를 정해요. 비탈면과 같은 쪽으로 기운 절리가 하나면 평면 파괴, 두 절리가 V자로 만나면 쐐기 파괴, 비탈 안쪽으로 급하게 기운 절리가 있으면 전도 파괴가 생겨요. 앞의 기사에서 위험도 점수가 가장 높았던 유형이 원호파괴, 피해도 점수가 가장 높았던 유형은 전도파괴였어요.</p>
<h3 data-ke-size="size23">물이 들어오면 안전율이 얼마나 떨어질까</h3>
<p>원인 가운데 가장 흔한 것이 비예요. 빗물이 스며들어 지하수위가 오르면 흙이 무거워지고, 간극수압이 생겨 흙 입자끼리 누르는 힘(유효응력)이 줄어들어 마찰 저항이 약해져요. 얕은 토층이 비탈면과 나란히 미끄러지는 무한사면으로 단순화하면 이 효과를 숫자로 볼 수 있어요.</p>
{f1_html}
<p>여기서 m은 토층 두께 z 가운데 지하수에 잠긴 비율이고, 지하수는 비탈면과 나란히 흐른다고 봐요. 단위중량 γ는 물에 잠긴 부분만 포화단위중량으로 바꿔 γ = (1 − m)γt + m·γsat로 섞었어요. 토층 두께 2 m, 경사 30°, 점착력 c′ 5 kPa, 내부마찰각 φ′ 35°, 습윤단위중량 γt 18 kN/m³, 포화단위중량 γsat 19 kN/m³, 물의 단위중량 γw 9.81 kN/m³으로 가정해 계산했어요.</p>
{f2_html}
{t_calc}
<p>같은 비탈면인데도 물이 없을 때 {F0:.2f}이던 안전율이 토층의 절반까지 물이 차면 {F5:.2f}, 지표까지 차면 {F1:.2f}로 떨어져요. 이 값을 「건설공사 비탈면 설계기준」(2016) 깎기 비탈면 기준안전율(건기 1.5, 우기 1.2~1.3)과 나란히 놓으면, 배수가 왜 대책의 첫 순서인지 감이 와요. 다만 이 수치는 학습용으로 만든 가상 예시라 실제 설계 검토와는 달라요.</p>
{gif_html}
<h3 data-ke-size="size23">기준안전율</h3>
{t_fs}
<p>위 표는 국토교통부 「건설공사 비탈면 설계기준」(2016) 표 4.2·표 5.2를 정리한 것이에요. 현재는 KDS 11 70 05로 옮겨졌고, 정리본으로 보면 깎기 건기 1.5, 우기 1.2 또는 1.3은 같아요. 다만 표의 지진 시 1.1은 2016년 판 값이고, 현행 KDS에서는 깎기·쌓기 모두 지진 시 기준을 KDS 11 90 00에 따르도록 되어 있어요(정리본 기준). 연약지반 위 쌓기 비탈면은 따로 기준이 있어요(2016년 판 장기 기준 건기 1.3, 우기 1.2). 시험 전에 국가건설기준센터 원문으로 한 번 더 확인하세요.</p>
<h3 data-ke-size="size23">대책은 억제공과 억지공으로</h3>
<p>억제공은 붕괴를 일으키는 원인 자체를 줄이는 공법이에요. 산마루측구·소단 배수구·수평배수공으로 물을 빼고, 식생이나 숏크리트·블록으로 표면을 보호하고, 경사를 완만하게 하거나 머리 부분 흙을 걷어 내고 아래쪽에 압성토를 쌓아 무게 균형을 맞춰요. 억지공은 구조물로 직접 버티는 공법이에요. 앵커·쏘일네일링·록볼트, 억지말뚝, 옹벽, 낙석방지망·울타리가 여기에 들어가요. 형태마다 먼저 쓸 공법이 달라서, 아래 답안 예시에서는 표로 짝지어 두었어요.</p>
<blockquote><p><strong>답안 작성 요령</strong> — 개요에서 안전율 정의와 기준안전율을 먼저 제시한다. 붕괴 형태는 표로 정리하고, 원인은 내적·외적으로 나누어 각 3~4항목으로 쓴다. 강우에 따른 안전율 저하를 간단한 식이나 그래프로 보이면 배수 대책의 우선순위가 근거를 갖는다. 대책은 억제공·억지공으로 나누되 형태별 우선 대책을 표로 짝지어 일반론 나열을 피한다. 끝은 시공·유지관리 유의사항으로 마무리한다.</p></blockquote>
<hr>
<h2 data-ke-size="size26">답안 예시</h2>
<h3 data-ke-size="size23">Ⅰ. 개요</h3>
<ul>
<li>비탈면 붕괴: 활동력이 전단저항력을 넘어 토체·암괴가 비탈 아래로 이동하는 현상임</li>
<li>안전율 Fs = 전단저항력 / 활동력</li>
<li>기준안전율(깎기): 건기 1.5, 우기 1.2~1.3(「건설공사 비탈면 설계기준」, 2016)</li>
</ul>
<h3 data-ke-size="size23">Ⅱ. 붕괴 형태</h3>
{table([('형태', '대상', '특징'),
        ('원호 활동', '흙·풍화토', '휘어진 활동면, 한 덩어리 이동'),
        ('평면 파괴', '암반', '비탈면 쪽으로 기운 절리 1개'),
        ('쐐기 파괴', '암반', '교차하는 절리 2개 사이 쐐기'),
        ('전도 파괴', '암반', '안쪽으로 급경사인 기둥 암괴'),
        ('표층 유실', '얕은 토층', '호우 시 표면 흙 쓸림')])}
<ul>
<li>흙은 원호, 암반은 불연속면 방향이 형태를 지배함</li>
</ul>
<h3 data-ke-size="size23">Ⅲ. 붕괴 원인</h3>
<ul>
<li>내적 원인(전단강도 감소): 풍화·이완, 불연속면 발달, 다짐 부족·점토 연화, 흡수·팽창, 간극수압 증가로 유효응력 감소</li>
<li>외적 원인(전단응력 증가): 강우 침투·지하수위 상승, 배수시설 막힘, 비탈 끝 굴착·침식, 비탈 어깨 성토·상재하중, 지진·발파 진동, 동결융해</li>
</ul>
<h3 data-ke-size="size23">Ⅳ. 강우 시 안전율 저하(무한사면, 가상 예시)</h3>
<ul>
<li>Fs = [c′ + (γz·cos²β − u)tanφ′] / (γz·sinβ·cosβ), u = m·γw·z·cos²β(사면과 평행한 지하수 흐름)</li>
<li>z = 2 m, β = 30°, c′ = 5 kPa, φ′ = 35°, γt = 18, γsat = 19, γw = 9.81 kN/m³ 가정 시 m = 0 → {F0:.2f}, m = 0.5 → {F5:.2f}, m = 1 → {F1:.2f}</li>
<li>이 가정에서는 지하수위가 토층 두께의 약 82%를 넘으면 안전율이 1.0 아래로 떨어지므로 배수 확보가 대책의 첫 순위임</li>
</ul>
<h3 data-ke-size="size23">Ⅴ. 방지대책</h3>
<ul>
<li>억제공(활동력 감소·강도 저하 방지): 산마루측구·소단 배수구·수평배수공, 식생·숏크리트·블록 표면보호, 경사 완화, 두부 제거·압성토</li>
<li>억지공(저항력 증가): 앵커·쏘일네일링·록볼트, 억지말뚝, 옹벽·돌망태옹벽, 낙석방지망·울타리</li>
</ul>
{table([('형태', '우선 대책'),
        ('원호 활동', '배수, 경사 완화·압성토, 억지말뚝'),
        ('평면·쐐기', '앵커·록볼트, 절리면 배수'),
        ('전도', '록볼트·앵커, 낙석방지시설'),
        ('표층 유실', '식생·표면보호, 산마루측구')])}
<h3 data-ke-size="size23">Ⅵ. 시공·유지관리 시 유의사항</h3>
<ul>
<li>깎기 중 노출되는 암질·절리를 조사해 설계를 보완함</li>
<li>높이 10 m 이상 깎기 비탈면은 5~20 m마다 소단을 둠</li>
<li>우기 전 배수시설 점검·준설, 지표변위·지하수위 계측</li>
<li>위험도와 피해도를 함께 보고 관리 우선순위를 정함</li>
</ul>
<hr>
<h2 data-ke-size="size26">놓치기 쉬운 점</h2>
<ul>
<li>원인을 "비가 와서"로만 쓰면 점수가 깎여요. 비가 흙을 무겁게 하는 것(작용력 증가)과 간극수압으로 마찰 저항을 줄이는 것(저항력 감소)을 나눠 쓰면 내적·외적 원인 구분이 저절로 정리돼요.</li>
<li>암반 비탈면에 원호 활동 해석과 억지말뚝만 적어 두면 틀린 답이 돼요. 암반은 절리 방향으로 평면·쐐기·전도를 먼저 가리고, 앵커·록볼트처럼 그 형태에 맞는 공법을 골라야 해요.</li>
<li>억제공과 억지공의 한자를 헷갈리기 쉬워요. 억제(抑制)는 원인을 누르는 것, 억지(抑止)는 움직임을 붙잡아 멈추는 것이라고 기억해 두세요.</li>
</ul>
<h2 data-ke-size="size26">참고자료와 확인일</h2>
<ul>{src}</ul>
<p>자료 확인일은 2026년 10월 31일이에요. 위 답안은 학습용 예시이며 공식 정답이나 채점기준이 아닙니다. 문제 원문과 관련 기출 네 문제는 Q-net 문제지로 확인했어요. 기준안전율은 「건설공사 비탈면 설계기준」(2016) 공개 사본으로 확인했고, 현행 KDS 11 70 05 원문은 열지 못해 정리본으로만 대조했어요. 무한사면 계산의 토층 두께·강도정수·단위중량은 이해를 돕기 위해 정한 가상 값이에요.</p>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 양식 위에 위 답안 예시를 옅은 회색 글씨로 얹은 3쪽짜리 PDF예요. 출력해서 그대로 따라 써 보세요.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>'''


if __name__ == '__main__':
    cap_img = '직접 작성한 개념도. 비탈면 붕괴 다섯 형태와 내적·외적 원인을 정리했다(축척 없음).'
    alt_img = '원호 활동, 평면 파괴, 쐐기 파괴, 전도 파괴, 표층 유실 다섯 가지 비탈면 붕괴 형태 단면과 내적·외적 원인을 정리한 개념도'
    alt_f1 = "F_s = [c' + (γ z cos²β − u) tan φ'] / (γ z sinβ cosβ), u = m γ_w z cos²β (0 ≤ m ≤ 1)"
    alt_f2 = '; '.join(f"m = {x['m']:g}: 저항 {x['resist']:.2f} / 활동 {x['drive']:.2f} = Fs {x['fs']:.2f}" for x in CALC)
    alt_gif = f'가상 예시 토층 2 m, 경사 30° 무한사면에서 지하수가 차오르며 안전율 막대가 {F0:.2f}에서 {F5:.2f}, {F1:.2f}로 낮아지고 건기 1.5, 우기 1.2, 1.0 기준선과 비교되는 도식'
    cap_f1 = '수식 1. 무한사면 안전율과 간극수압'
    cap_f2 = '수식 2. 계산 예(가상 예시)'
    cap_gif = '도식. 지하수위 상승에 따른 안전율 변화 — 학습용 가정값'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(banner_html=f'<p data-ax-attach="{BANNER}"></p>\n', img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'groundwater-fs.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(banner_html=f'<p><img src="{CDN}banner.png" alt="{TITLE}" style="max-width:100%;height:auto"></p>\n',
                   img_html=b_fig(CDN + 'slope-failure-types.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'groundwater-fs.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (3쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(banner_html=f'<p><img src="{BANNER}" alt="배너"></p>', img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1),
                   f2_html=b_fig(F2_NAME, alt_f2, cap_f2), gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    (OUT / '태그.txt').write_text('토목시공기술사,비탈면,산사태,사면붕괴,사면안정,비탈면안정공법,안전율,토목시공,토목시공기술사기출\n')
    print(json.dumps(CALC, ensure_ascii=False))
