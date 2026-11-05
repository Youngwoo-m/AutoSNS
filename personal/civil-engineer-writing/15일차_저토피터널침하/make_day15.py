"""15일차 미고결 저토피 터널 지표침하 원인과 저감대책 — 티스토리/Blogger 본문·미리보기·제목을 만든다(그림은 fig.py, PDF 는 make_pdf.py,
수식 PNG·GIF 는 dept/naver-blog-auto/math_gif/civil_day15.py)."""
from pathlib import Path
import json
import math

OUT = Path(__file__).parent
TITLE = '[토목시공기술사] 싱크홀·지표침하, 저토피 터널 원인과 저감대책 | 하루 한 문제 15일차'
PDF_NAME = '15일차_저토피터널침하_답안예시_따라쓰기.pdf'
FIG_NAME = '저토피터널_지표침하_개념도.jpg'
F1_NAME, F2_NAME, GIF_NAME = '수식1_침하곡선.png', '수식2_계산예.png', '도식_토피별침하곡선.gif'
BANNER = 'banner.png'
CDN = 'https://geoai-na.netlify.app/civil-questions/materials/day15/'
QNET = 'https://www.q-net.or.kr/cst006.do?id=cst00602&artlSeq={}&brdId=Q006&gSite=Q'

SOURCES = []          # (제목, 주소) — sources.py
exec((OUT / 'sources.py').read_text())

# 가상 예시(Peck 정규분포 침하곡선) — 본문·수식·GIF·PDF 가 모두 이 값을 쓴다
D, VL, K = 10.0, 0.01, 0.5
VS = VL * math.pi * D * D / 4


def trough(z0):
    i = K * z0
    s = VS / (math.sqrt(2 * math.pi) * i)
    return dict(z0=z0, i=i, smax_mm=round(s * 1000, 1), at_i_mm=round(s * 1000 * math.exp(-0.5), 1))


CALC = [trough(15.0), trough(10.0)]
S15, S10 = CALC[0]['smax_mm'], CALC[1]['smax_mm']

C_ = ' style="text-align:center"'


def tr(cells, th=False):
    t = 'th' if th else 'td'
    return '<tr>' + ''.join(f'<{t}{C_}>{x}</{t}>' for x in cells) + '</tr>'


def table(rows):
    return ('<table style="border-collapse: collapse; width: 100%;" border="1" data-ke-align="alignLeft">\n'
            + tr(rows[0], True) + '\n' + '\n'.join(tr(r) for r in rows[1:]) + '\n</table>')


def body(banner_html, img_html, f1_html, f2_html, gif_html, pdf_html):
    src = ''.join(f'<li><a href="{u}">{t}</a></li>' for t, u in SOURCES)
    t_stage = table([('단계', '언제', '주된 원인'),
                     ('선행 침하', '막장이 도달하기 전', '막장 앞 지반 이완, 지하수위 저하'),
                     ('막장 침하', '막장이 지나가는 순간', '막장 자립 부족, 여굴·붕락'),
                     ('후행 침하', '지보 설치 뒤', '지보 변형, 폐합 지연, 배면 공극'),
                     ('장기 침하', '굴착 뒤 오랫동안', '배수에 따른 점성토 압밀')])
    t_calc = table([('터널 중심 깊이 z₀', '침하곡선 폭 i', '최대 침하 S max', 'x = i 지점 침하')]
                   + [(f"{x['z0']:g} m", f"{x['i']:.1f} m", f"{x['smax_mm']:.1f} mm", f"{x['at_i_mm']:.1f} mm") for x in CALC])
    return f'''{banner_html}<p>안녕하세요, 오늘은 토피가 얕은 미고결 지반에서 생기는 저토피 터널 지표침하의 원인과 저감대책을 묻는 기출을 풀어요. 지난 10월 22일 강릉 동해북부선 철도 공사의 지하 터널 구간에서 지름 2 m 안팎의 땅 꺼짐이 생겼고, 시공사는 지하 15 m 깊이에서 굴착하던 중 연약지반이 침하한 것으로 보고 보강 공사를 하기로 했다고 해요(KBS, 2026년 10월 22일, 기사에 토피 두께는 나오지 않아요). 같은 날 장종태 의원실이 받은 국토안전관리원 자료에서는 2022년부터 올해 7월까지 굴착공사 인접 지반침하 56건 가운데 30건이 지하안전평가를 마친 현장이었는데, 평가 뒤 굴착 중 관리가 그만큼 중요하다는 지적으로 읽을 수 있어요(뉴스티앤티, 2026년 10월 22일).</p>
<h2 data-ke-size="size26">문제</h2>
<p>기출문제: 2022년 제126회 토목시공기술사 제4교시 5번 (<a href="{QNET.format(5209527)}">Q-net 공식 문제지</a>)</p>
<blockquote><p>미고결(未固結) 저토피(低土皮) 터널 시공 시 지표 침하원인 및 저감대책을 설명하시오. (25점)</p></blockquote>
<p>논술형 · 25점 · 권장 작성시간 25분, 분량 3쪽 안팎</p>
<h2 data-ke-size="size26">출제 의도와 답안 방향</h2>
<p>저토피 터널은 2022~2026년 기출 15회 가운데 다섯 회차에서 논술형으로 나왔어요. 2022년 제127회 2교시 5번은 토피가 얕은 도심지 터널의 지표면 침하방지 대책, 2023년 제130회 2교시 5번은 저토피 구간 굴착 시 보강대책, 같은 해 제131회 2교시 4번은 미고결 지반의 공학적 특징과 저토피 터널의 문제점·대책, 2025년 제136회 2교시 3번은 지하수위가 높은 저토피 터널의 지반함몰 예방대책과 응급복구방안을 물었어요. 다섯 문제 모두 침하가 왜 생기고 무엇으로 막는지를 물어요. 원인을 지반·시공·지하수로 나누고 대책을 천단·막장·굴착방법·지하수·계측으로 짝지어 두면 어느 문제가 나와도 쓸 수 있어요.</p>
<p>점수는 침하가 언제, 어떤 모양으로 생기는지 보여 주느냐에서 갈려요. 정규분포 침하곡선 하나와 침하 단계 표 하나만 넣어도 대책에 근거가 생겨요. 흔한 실수는 숏크리트·록볼트·강지보 같은 산악 터널 지보 일반론만 적고, 저토피에서 핵심인 천단·막장 보강과 조기 폐합을 빠뜨리는 거예요.</p>
<h2 data-ke-size="size26">저토피 터널에서 지표침하가 생기는 이유</h2>
<p>터널을 파면 주변 흙이 굴착면 쪽으로 움직여요. 토피가 두꺼우면 위쪽 흙이 서로 기대어 하중을 옆으로 돌리는 아칭(arching)이 생겨 움직임이 지표까지 잘 올라오지 않지만, 토피가 얕으면 아칭이 충분히 생기지 못해 굴착면에서 생긴 손실이 거의 그대로 지표침하로 나타나요. 여기에 미고결 지반, 곧 아직 단단히 굳지 않은 토사·풍화토는 점착력이 작고 지보 없이 버틸 수 있는 시간(자립시간)이 짧아요. 지하수가 있으면 흙 알갱이가 물과 함께 터널 안으로 쓸려 들어오기 쉬워서, 땅속에 빈 공간이 생기고 그것이 위로 올라가면 지표 함몰, 흔히 말하는 싱크홀이 돼요.</p>
{img_html}
<h3 data-ke-size="size23">침하는 막장 앞에서부터 시작돼요</h3>
{t_stage}
<p>지표침하는 막장이 오기 전부터 생기고, 지나간 뒤에도 이어져요. 그래서 대책도 막장 앞을 미리 보강하고, 막장을 빨리 지나가고, 지나간 뒤 빨리 닫고, 계속 지켜보는 순서로 짜면 빠지는 게 없어요.</p>
<h3 data-ke-size="size23">침하곡선을 숫자로 보면</h3>
<p>터널 위 지표침하의 가로 단면은 정규분포 곡선 모양을 따른다고 보는 경우가 많아요(Peck, 1969). 최대 침하 S max는 터널 중심 위에서 생기고, 곡선의 변곡점까지 거리 i가 침하 범위의 폭을 나타내요. O'Reilly & New(1982)는 i를 터널 중심 깊이 z₀에 비례하는 i = K·z₀로 두었고, 점토에서는 K를 0.5 정도로 많이 써요. 지반에 따라 값이 달라지니 실제로는 현장 계측이나 설계 자료로 정해요. 침하곡선 아래 넓이(침하 체적 V s)를 터널 단면적으로 나눈 값이 체적손실(volume loss) V L이에요.</p>
{f1_html}
<p>지름 D 10 m 터널에서 체적손실 1.0 %, K 0.5인 점성토를 가정하고, 터널 중심 깊이만 15 m에서 10 m로 바꿔 계산해 봤어요. 학습용 가상 예시라 실제 설계 값과는 달라요.</p>
{f2_html}
{t_calc}
<p>같은 체적손실이어도 토피가 얕아지면 곡선 폭이 좁아지면서 최대 침하가 {S15:.1f} mm에서 {S10:.1f} mm로 커져요. 실제로는 토피가 얕을수록 체적손실 자체도 커지기 쉬우니 차이는 더 벌어질 수 있어요. 다만 이 식은 길게 뻗은 단일 터널을 전제로 하고, 천단 위에 조립토층이 있으면 지중 손실 체적과 지표 침하 체적이 같지 않을 수 있다는 한계도 함께 알아 두세요.</p>
{gif_html}
<h3 data-ke-size="size23">대책은 막장 앞에서 시작해 계측으로 끝나요</h3>
<p>먼저 천단을 미리 보강해요. 강관다단 그라우팅은 막장 앞 천장 위로 강관을 우산처럼 박고 그라우트를 넣어 지반을 붙잡고, 훠폴링은 더 짧은 철근·강관으로 같은 일을 해요. 막장면이 무너질 우려가 있으면 막장면에 숏크리트를 뿌리고 막장 볼트를 박거나, 가운데 흙을 남겨 두는 링컷으로 막장을 버티게 해요. 굴착은 단면을 나눠 파고(분할굴착), 한 번에 파는 길이를 줄이고, 숏크리트를 바로 뿌리고, 바닥까지 빨리 닫아요(가인버트·조기 폐합). 지하수가 많으면 차수 그라우팅이나 지반개량으로 물과 토사가 함께 들어오지 않게 막아요. 쉴드 TBM이라면 막장압 관리와 세그먼트 뒤 공극을 채우는 뒤채움 주입이 같은 역할을 해요. 마지막으로 지표침하·천단침하·내공변위를 계측하고, 관리기준을 단계별로 정해 두고, 기준을 넘으면 굴진을 멈추고 보강하도록 미리 정해 둬요.</p>
<p>제도 쪽에서는 「지하안전관리에 관한 특별법」 시행령 제13조가 굴착깊이 20 m 이상이거나 터널공사(산악·수저터널 제외)를 수반하는 사업을 지하안전평가 대상으로, 제23조가 굴착깊이 10 m 이상 20 m 미만이면서 별표 1에서 정한 사업을 소규모 지하안전평가 대상으로 정하고 있어요(법령 해설 사이트 정리본으로 확인). 도심지 저토피 터널이라면 착공 전에 이 평가를 거치게 되고, 굴착 중 계측과 대응이 그 협의 내용을 실제로 지키는 단계예요.</p>
<blockquote><p><strong>답안 작성 요령</strong> — 개요에서 미고결 지반과 저토피의 특징을 정의하고 아칭 부족이라는 핵심 문제를 먼저 제시한다. 침하 발생 단계를 표로 정리한 뒤 원인을 지반·시공·지하수로 나누어 쓴다. 정규분포 침하곡선 그림과 간단한 계산을 넣으면 토피가 얕을수록 침하가 커지는 이유가 근거를 갖는다. 대책은 천단 보강·막장 보강·굴착방법·지하수 대책·계측관리로 나누고 원인과 짝지어 표로 정리한다. 끝은 이상 징후 시 조치로 마무리해 응급복구를 묻는 변형 문제에도 대응한다.</p></blockquote>
<hr>
<h2 data-ke-size="size26">답안 예시</h2>
<h3 data-ke-size="size23">Ⅰ. 개요</h3>
<ul>
<li>미고결 지반: 고결되지 않은 토사·풍화토로 점착력이 작고 자립시간이 짧으며 지하수에 민감함</li>
<li>저토피 터널: 토피가 얕아 지반 아칭이 충분히 형성되지 않으므로 굴착 손실이 지표침하로 직접 전달됨</li>
<li>도심지에서는 지반함몰·매설관 파손·인접 건물 손상으로 이어질 수 있어 침하 억제가 시공관리의 핵심임</li>
</ul>
<h3 data-ke-size="size23">Ⅱ. 지표침하 발생 단계와 형태</h3>
{table([('단계', '시기', '주된 원인'),
        ('선행 침하', '막장 도달 전', '전방 이완, 지하수위 저하'),
        ('막장 침하', '막장 통과 시', '막장 자립 부족, 여굴'),
        ('후행 침하', '지보 설치 후', '지보 변형, 폐합 지연'),
        ('장기 침하', '굴착 완료 후', '배수에 따른 압밀')])}
<ul>
<li>횡단 침하곡선: 정규분포형 S(x) = S max·exp(−x²/2i²), i = K·z₀(Peck 1969, O'Reilly & New 1982), 점토 K 약 0.5</li>
<li>가상 예시(D 10 m, 체적손실 1.0 %, K 0.5): z₀ 15 m → S max 약 {S15:.0f} mm, z₀ 10 m → 약 {S10:.0f} mm</li>
<li>토피가 얕을수록 침하 폭은 좁아지고 최대 침하는 커짐</li>
</ul>
<h3 data-ke-size="size23">Ⅲ. 지표침하 원인</h3>
<ul>
<li>지반 요인: 아칭 효과 부족, 낮은 점착력·짧은 자립시간, 이완영역의 지표 도달</li>
<li>시공 요인: 막장 붕락·여굴, 1회 굴진장 과다, 지보 설치·인버트 폐합 지연, 숏크리트 두께·품질 부족, 배면 공극</li>
<li>지하수 요인: 용수와 함께 세립분 유출 → 지중 공동 형성, 지하수위 저하에 따른 압밀침하</li>
<li>외부 요인: 상재하중·교통하중, 노후 상하수관 누수</li>
</ul>
<h3 data-ke-size="size23">Ⅳ. 저감대책</h3>
{table([('구분', '대책', '대응 원인'),
        ('천단 보강', '강관다단 그라우팅, 훠폴링', '아칭 부족, 이완'),
        ('막장 보강', '막장 숏크리트·볼트, 링컷', '막장 붕락, 여굴'),
        ('굴착 방법', '분할굴착, 굴진장 축소, 조기 폐합', '지보·폐합 지연'),
        ('지하수', '차수 그라우팅, 지반개량', '세립분 유출, 압밀'),
        ('계측', '지표·천단침하, 내공변위', '이상 징후 조기 파악')])}
<ul>
<li>쉴드 TBM 적용 시 막장압 관리와 뒤채움 주입으로 테일 공극을 즉시 충전함</li>
<li>도심지는 착공 전 지하안전평가(굴착 20 m 이상 또는 터널공사 수반)와 지장물·매설관 조사를 시행함</li>
</ul>
<h3 data-ke-size="size23">Ⅴ. 이상 징후 시 조치</h3>
<ul>
<li>관리기준 초과 시 굴진 중지, 막장면 숏크리트 폐합·되메움으로 막장 안정 확보</li>
<li>지중 공동은 그라우팅으로 충전하고 지표 함몰부는 출입 통제 후 복구</li>
<li>인접 매설관(상하수도·가스) 점검, 계측 빈도 상향 후 보강 효과 확인 뒤 굴진 재개</li>
</ul>
<hr>
<h2 data-ke-size="size26">놓치기 쉬운 점</h2>
<ul>
<li>"지보를 튼튼하게"로만 쓰면 저토피 문제의 핵심을 놓쳐요. 침하는 막장 앞에서 시작하니까, 천단·막장을 미리 보강하는 선행 대책과 빨리 닫는 조기 폐합이 답안의 중심이 돼야 해요.</li>
<li>i = K·z₀에서 z₀는 토피가 아니라 터널 중심까지의 깊이예요. 토피 10 m, 지름 10 m 터널이면 z₀는 15 m예요.</li>
<li>침하와 함몰은 달라요. 침하는 넓게 완만히 내려앉는 것이고, 함몰(싱크홀)은 세립분 유출로 생긴 공동이 위로 올라와 갑자기 꺼지는 거예요. 지하수가 많은 지반이라는 조건이 붙으면 차수와 공동 충전을 꼭 쓰세요.</li>
</ul>
<h2 data-ke-size="size26">참고자료와 확인일</h2>
<ul>{src}</ul>
<p>자료 확인일은 2026년 11월 1일이에요. 위 답안은 학습용 예시이고, 공식 정답이나 채점기준이 아니에요. 문제 원문과 관련 기출 네 문제는 Q-net 문제지로 확인했어요. 침하곡선 식과 점토 K 0.5는 Peck(1969), O'Reilly & New(1982)를 인용한 공개 논문(Divall et al. 2023)으로 확인했고 원 논문은 열지 못했어요. 아칭·이완영역 설명과 보조공법, 침하 단계 구분은 일반 터널 시공 교과 내용이에요. '다섯 회차'는 2022~2026년 제126~140회 문제지에서 '토피'가 든 문제를 낱말로 찾아 센 것이라, 다른 표현으로 나온 터널 문제는 세지 않았어요. 지하안전법 시행령 조문은 국가법령정보센터 원문을 열지 못해 법령 해설 사이트 정리본(2022년 1월 25일 개정 반영)으로 확인했으니, 적용할 때는 현행 원문을 다시 보세요. 침하 계산의 터널 지름·체적손실·K·깊이는 이해를 돕기 위해 정한 가상 값이에요.</p>
<h2 data-ke-size="size26">따라쓰기 PDF</h2>
{pdf_html}
<p>Q-net 답안지 양식 위에 위 답안 예시를 옅은 회색 글씨로 얹은 3쪽짜리 PDF예요. 출력해서 그대로 따라 써 보세요.</p>
<h2 data-ke-size="size26"><a href="https://geoai-na.netlify.app/civil-questions/">함께 푸는 [토목시공기술사] 답안지 요청</a></h2>
<p>문제를 요청하시면 접수 순서에 따라 매일 밤 11시에 요청을 확인하고, 정답예시와 따라쓰기 PDF를 작성해 블로그에 올립니다.</p>'''


if __name__ == '__main__':
    cap_img = '직접 작성한 개념도. 저토피 터널 지표침하 원인과 저감대책을 한 단면에 정리했다(축척 없음).'
    alt_img = '미고결 지반 저토피 터널 위로 정규분포 모양 지표침하 곡선과 이완영역, 강관다단 그라우팅 천단 보강, 지하수 유입을 표시하고 침하 원인과 저감대책을 정리한 개념도'
    alt_f1 = "S(x) = S_max exp(−x²/2i²), V_s = √(2π) i S_max = V_L πD²/4, i = K z₀"
    alt_f2 = f"V_s = 0.01 × π × 10²/4 = 0.785 m³/m; z₀ 15 m: i 7.5 m, S_max {S15:.1f} mm; z₀ 10 m: i 5.0 m, S_max {S10:.1f} mm"
    alt_gif = f'가상 예시 지름 10 m 터널, 체적손실 1 %, K 0.5에서 터널 중심 깊이가 15 m에서 10 m로 얕아지며 지표 침하곡선이 좁고 깊어져 최대 침하가 {S15:.1f} mm에서 {S10:.1f} mm로 커지는 도식'
    cap_f1 = '수식 1. 정규분포 침하곡선과 체적손실(Peck 1969, O\'Reilly & New 1982)'
    cap_f2 = '수식 2. 토피 15 m와 10 m 계산 예'
    cap_gif = '도식. 토피에 따른 침하곡선 변화'
    def t_fig(name, cap): return f'<p data-ax-attach="{name}"></p><p>{cap}</p>'
    def b_fig(url, alt, cap): return f'<figure><img src="{url}" alt="{alt}" style="max-width:100%;height:auto"><figcaption>{cap}</figcaption></figure>'
    t_parts = dict(banner_html=f'<p data-ax-attach="{BANNER}"></p>\n', img_html=t_fig(FIG_NAME, cap_img), f1_html=t_fig(F1_NAME, cap_f1), f2_html=t_fig(F2_NAME, cap_f2),
                   gif_html=b_fig(CDN + 'trough-cover.gif', alt_gif, cap_gif), pdf_html=f'<p data-ax-attach="{PDF_NAME}"></p>')
    b_parts = dict(banner_html=f'<p><img src="{CDN}banner.png" alt="{TITLE}" style="max-width:100%;height:auto"></p>\n',
                   img_html=b_fig(CDN + 'tunnel-settlement.jpg', alt_img, cap_img), f1_html=b_fig(CDN + 'formula1.png', alt_f1, cap_f1),
                   f2_html=b_fig(CDN + 'formula2.png', alt_f2, cap_f2), gif_html=b_fig(CDN + 'trough-cover.gif', alt_gif, cap_gif),
                   pdf_html=f'<p><a href="{CDN}answer-tracing.pdf">{PDF_NAME} 내려받기 (3쪽)</a></p>')
    (OUT / '티스토리게시본문.html').write_text(body(**t_parts))
    (OUT / 'Blogger게시본문.html').write_text(body(**b_parts))
    p_parts = dict(banner_html=f'<p><img src="{BANNER}" alt="배너"></p>', img_html=b_fig(FIG_NAME, alt_img, cap_img), f1_html=b_fig(F1_NAME, alt_f1, cap_f1),
                   f2_html=b_fig(F2_NAME, alt_f2, cap_f2), gif_html=b_fig(GIF_NAME, alt_gif, cap_gif), pdf_html=f'<p><a href="{PDF_NAME}">{PDF_NAME}</a></p>')
    prev = f'<!doctype html><html lang="ko"><meta charset="utf-8"><title>{TITLE}</title><style>body{{max-width:860px;margin:40px auto;padding:0 20px;font:17px/1.85 sans-serif}}td,th{{padding:8px}}img{{max-width:100%}}</style><h1>{TITLE}</h1>' + body(**p_parts) + '</html>'
    (OUT / '블로그미리보기.html').write_text(prev)
    (OUT / '제목.txt').write_text(TITLE + '\n')
    (OUT / '태그.txt').write_text('토목시공기술사,싱크홀,지반침하,저토피터널,지표침하,터널,NATM,보조공법,토목시공,토목시공기술사기출\n')
    print(json.dumps(CALC, ensure_ascii=False))
