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


def default_font_dir(base_dir):
    """프로젝트 폴더 한 단계 위의 공용 FONTS/."""
    return os.path.join(os.path.dirname(base_dir), "FONTS")


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
