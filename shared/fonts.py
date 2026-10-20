"""공용 폰트(FONTS/KoPubWorld) 존재 확인.

FONTS/ 는 용량·라이선스 때문에 git 에서 제외되어 있다(.gitignore 참고).
새 환경에 클론하면 폰트가 없는데, 그때의 실패 방식이 두 갈래로 갈린다.

  · ffmpeg drawtext(heygen_anchor·overlays) → FileNotFoundError 로 즉시 중단
  · HTML @font-face(render_frames·render_cards_local) → 크롬이 예외 없이
    '다른 글꼴로' 렌더해 버린다. 영상·카드가 멀쩡히 만들어지고 자동 발행까지
    그대로 진행되므로 아무도 모르는 사이 결과물만 깨진다.

후자를 막는 게 이 모듈의 목적이다. 렌더 직전에 require_fonts() 를 불러
없으면 '무엇을 어디에 두어야 하는지' 알려주며 멈춘다.
"""
import os

# 실제로 쓰이는 것은 Dotum 3종뿐이다(Batang 은 어디서도 참조하지 않는다).
DOTUM_LIGHT = "KoPubWorld Dotum_Pro Light.otf"
DOTUM_MEDIUM = "KoPubWorld Dotum_Pro Medium.otf"
DOTUM_BOLD = "KoPubWorld Dotum_Pro Bold.otf"
REQUIRED = (DOTUM_LIGHT, DOTUM_MEDIUM, DOTUM_BOLD)


ROOT_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "FONTS")


def kopub_bold_css(font_dir=None, doubled=False):
    """HTML 이미지에 넣을 @font-face — 글꼴 이름 'KoPub' 의 모든 굵기를 Dotum_Pro Bold 로.

    사용자 지정(2026-10-06): 이미지 속 글자는 전부 KoPubWorld 돋움 Bold. 시스템 글꼴
    (Apple SD Gothic Neo 등)에 맡기면 렌더 환경에 따라 한글이 깨지거나 글꼴이 바뀐다.
    doubled=True 면 .format() 템플릿에 그대로 넣을 수 있게 중괄호를 두 겹으로 쓴다."""
    path = os.path.join(font_dir or ROOT_FONT_DIR, DOTUM_BOLD)
    if not os.path.exists(path):
        require_fonts(font_dir or ROOT_FONT_DIR, (DOTUM_BOLD,))
    css = ("@font-face{font-family:'KoPub';font-weight:100 900;font-style:normal;"
           f"src:url('file://{path}') format('opentype');}}")
    return css.replace("{", "{{").replace("}", "}}") if doubled else css


def default_font_dir(base_dir):
    """프로젝트 폴더 한 단계 위의 공용 FONTS/."""
    return ROOT_FONT_DIR


def require_fonts(font_dir, needed=REQUIRED):
    """폰트가 모두 있으면 font_dir 을 돌려주고, 없으면 안내와 함께 중단한다."""
    missing = [n for n in needed
               if not os.path.exists(os.path.join(font_dir, n))]
    if missing:
        raise RuntimeError(
            "폰트를 찾을 수 없어 렌더링을 중단합니다.\n"
            f"  찾은 위치 : {font_dir}\n"
            f"  없는 파일 : {', '.join(missing)}\n"
            "  해결      : KoPubWorld OTF 폰트를 내려받아 위 FONTS/ 에 넣으세요.\n"
            "              (FONTS/ 는 용량·라이선스 때문에 git 에서 제외됩니다)\n"
            "              다른 경로를 쓰려면 config 의 local_render.font_dir 지정."
        )
    return font_dir

# ── 제목용 굵은 글꼴(2026-10-14) ────────────────────────────────────────────
# KoPubWorld 돋움 Bold 는 본문용이라 썸네일·배너 제목에서는 획이 가늘어 보인다.
# 제목은 '검은고딕'(제목 전용, OFL), 보조 글자는 Pretendard 로 쓴다. 둘 다 상업용 무료다.
# 영상 프레임·인스타 카드는 글자 수에 맞춰 칸을 짜 두어 더 두꺼운 글꼴로 바꾸면
# 넘칠 수 있으므로 손대지 않았다(바꾸려면 렌더 결과를 먼저 확인할 것).
# 2026-10-14 2차: 검은고딕은 획이 너무 굵고 속공간이 좁아 "읽기 어렵다"는 지적을 받았다.
# 제목 글꼴을 Pretendard 로 내린다 — KoPub 보다 확실히 굵으면서 글자 속이
# 트여 있어 길게 읽어도 피로하지 않다. 검은고딕은 필요할 때만 골라 쓴다(PUNCH).
DISPLAY = "Pretendard-Bold.otf"           # 제목(2026-10-14 3차: Black 도 두껍다는 지적)
BODY_BOLD = "Pretendard-Bold.otf"         # 보조·설명
BODY_BLACK = "Pretendard-Black.otf"       # 강조·라벨
PUNCH = "BlackHanSans-Regular.ttf"        # 검은고딕 — 아주 짧은 문구에만
HEAVY_ALT = "SCDream9Black.otf"           # 에스코어드림 9 Black — 대체 제목용


def font_path(name, font_dir=None):
    """FONTS/ 안의 글꼴 경로. 없으면 KoPub Bold 로 떨어뜨린다(렌더는 계속된다)."""
    d = font_dir or ROOT_FONT_DIR
    p = os.path.join(d, name)
    if os.path.exists(p):
        return p
    return os.path.join(d, DOTUM_BOLD)


def display_css(font_dir=None, doubled=False):
    """HTML 이미지용 @font-face — 'Display'(검은고딕)와 'Body'(Pretendard).

    kopub_bold_css() 와 함께 넣으면 제목만 굵은 글꼴로 바꿀 수 있다."""
    disp = font_path(DISPLAY, font_dir)
    body = font_path(BODY_BOLD, font_dir)
    black = font_path(BODY_BLACK, font_dir)
    fmt = "truetype" if disp.lower().endswith(".ttf") else "opentype"
    css = (f"@font-face{{font-family:'Display';font-weight:100 900;"
           f"src:url('file://{disp}') format('{fmt}');}}"
           f"@font-face{{font-family:'Body';font-weight:100 700;"
           f"src:url('file://{body}') format('opentype');}}"
           f"@font-face{{font-family:'Body';font-weight:800 900;"
           f"src:url('file://{black}') format('opentype');}}")
    return css.replace("{", "{{").replace("}", "}}") if doubled else css
