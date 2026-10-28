# naver_hub (geopanda-seller에서 복사)
- 원본: geopanda-seller `app/naver_hub.py`, `tests/test_naver_hub.py` (브랜치 feat/naver-apihub-search, 커밋 b587a6b, main에 병합됨)
- 기능: NAVER API HUB 공용 클라이언트(검색·성인판별·오타변환·검색어 트렌드·쇼핑 인사이트)
- 키: AutoSNS/.env 의 NAVER_SEARCH_CLIENT_ID / NAVER_SEARCH_CLIENT_SECRET / NAVER_SEARCH_PROVIDER
- 의존: httpx

## AutoSNS 에서 쓰는 법 (2026-10-28)
- 위치: `common/naver_hub/` (옛 경로 `naver_hub/` 도 심볼릭 링크 규칙에 따라 필요하면 추가).
- 가져오기: `from naver_hub import naver_hub as hub` (`common/` 이 sys.path 에 있을 때). 키는 `hub.search(env, …)` 의 `env` 딕셔너리로 넘긴다 — `.env` 의 NAVER_SEARCH_CLIENT_ID/SECRET/PROVIDER 를 `shared/secret_env.py` 로 읽어 만든다.
- 테스트: `cd common && python -m pytest naver_hub` (httpx·pytest 필요).
- 기존 `shared/naver_search.py`(블로그 검색, urllib)는 그대로 둔다. 바꿀지는 사장님과 상의.
