"""빠진 API 키를 암호화 저장소(secrets.env.enc)에 하나씩 넣는다 — 사용자가 터미널에서 직접 실행 (2026-11-06, Windows).

    python common\\tools\\secrets_setup.py            개인 계정 작업에 필요한 키
    python common\\tools\\secrets_setup.py --all      학과 계정 키까지

입력한 값은 화면에 보이지 않고(getpass) 바로 암호화 저장소에 들어간다. 이미 있는 키는 묻지 않는다.
모르는 키는 그냥 Enter 로 건너뛴다(나중에 다시 실행하면 빠진 것만 다시 묻는다).
"""
import getpass
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
sys.path.insert(0, ROOT)
from shared import secret_env  # noqa: E402

PERSONAL = [
    ("ANTHROPIC_API_KEY", "Anthropic API 키 — Max 구독(claude CLI)이 안 될 때만 쓰는 예비 글 작성", "console.anthropic.com → API Keys"),
    ("LLM_GATEWAY_API_KEY", "세명대 AI 게이트웨이 — 영상 클립·숏츠 디오라마 그림 전용", "학교 게이트웨이 발급 키"),
    ("PEXELS_API_KEY", "자료사진(Pexels)", "pexels.com/api"),
    ("PIXABAY_API_KEY", "자료사진(Pixabay)", "pixabay.com/api/docs"),
    ("COLLECTOR_KEY", "기술사 친구 요청 접수함(Firebase 함수) 읽기 키", "Firebase 함수 설정값(geoai-na)"),
    ("NAVER_SEARCH_CLIENT_ID", "네이버 검색 API(검색량·뉴스 비교) Client ID", "developers.naver.com → 내 애플리케이션"),
    ("NAVER_SEARCH_CLIENT_SECRET", "네이버 검색 API Client Secret", "developers.naver.com → 내 애플리케이션"),
    ("DATA_GO_KR_KEY", "공공데이터포털 일반 인증키(Decoding)", "data.go.kr → 마이페이지"),
    ("DATA_GO_KR_KEY_ENCODED", "공공데이터포털 일반 인증키(Encoding)", "data.go.kr → 마이페이지"),
    ("GAMMA_API_KEY", "Gamma 이미지(선택)", "gamma.app 설정"),
    ("HEYGEN_API_KEY", "HeyGen AI 아나운서 영상(선택)", "heygen.com 설정"),
    ("GH_TOKEN", "GitHub 토큰 — 글 그림 CDN(geoai-assets) 올리기", "github.com → Settings → Developer settings → Tokens"),
    ("MAIL_APP_PASSWORD", "주간·월간 보고서 메일 발송용 앱 비밀번호", "Google 계정 → 보안 → 앱 비밀번호"),
]
DEPT = [
    ("NAVER_ID", "학과 네이버 아이디", ""), ("NAVER_PW", "학과 네이버 비밀번호", ""),
    ("INSTAGRAM_ID", "학과 인스타그램 아이디", ""), ("INSTAGRAM_PW", "학과 인스타그램 비밀번호", ""),
    ("X_OAUTH2_CLIENT_ID", "X(트위터) OAuth2 Client ID", ""), ("X_OAUTH2_CLIENT_SECRET", "X OAuth2 Client Secret", ""),
    ("TIKTOK_CLIENT_KEY", "학과 틱톡 API Client key", ""), ("TIKTOK_CLIENT_SECRET", "학과 틱톡 API Client secret", ""),
]


def main(argv):
    have = secret_env.read()
    # 카카오 REST 키는 알림 토큰을 만들 때 이미 입력했다 — 토큰 안의 client_id 를 그대로 옮긴다(화면에 띄우지 않음)
    if "KAKAO_REST_KEY" not in have and have.get("KAKAO_TOKEN"):
        try:
            cid = json.loads(have["KAKAO_TOKEN"]).get("client_id")
            if cid:
                secret_env.update({"KAKAO_REST_KEY": cid})
                print("KAKAO_REST_KEY: 카카오 알림 토큰에 있던 값으로 채웠습니다.")
                have = secret_env.read()
        except Exception:  # noqa: BLE001
            pass
    items = PERSONAL + (DEPT if "--all" in argv else [])
    missing = [x for x in items if not have.get(x[0])]
    print(f"\n이미 있는 키 {len(items) - len(missing)}개, 빠진 키 {len(missing)}개. 값은 화면에 보이지 않습니다. 모르면 Enter.\n")
    added = []
    for name, what, where in missing:
        print(f"■ {name} — {what}" + (f"\n  (어디서: {where})" if where else ""))
        v = getpass.getpass("  값: ").strip()
        if v:
            secret_env.update({name: v})
            added.append(name)
            print("  저장했습니다.\n")
        else:
            print("  건너뜀.\n")
    left = [n for n, _, _ in items if not secret_env.read().get(n)]
    print("저장:", ", ".join(added) or "없음")
    print("아직 빠진 키:", ", ".join(left) or "없음")


if __name__ == "__main__":
    main(sys.argv[1:])
