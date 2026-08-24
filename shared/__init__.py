"""세 프로젝트(youtube-shorts-auto / naver-blog-auto / insta-cardnews)가 함께 쓰는 모듈.

각 프로젝트 루트에 같은 이름의 얇은 shim 파일이 있어 기존 import 경로
(`from esri_feed import ...`)가 그대로 동작한다. 실제 구현은 여기에만 있다.

주의: 이 안의 모듈이 `from common import log` 하면 각 프로젝트의 common.py 가
잡힌다(프로젝트별 BASE_DIR/로그 경로 유지). common.py 는 프로젝트마다 경로가
달라야 하므로 의도적으로 공용화하지 않는다.
"""
