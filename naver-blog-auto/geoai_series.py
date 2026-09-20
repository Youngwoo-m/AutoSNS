"""GeoAI·생성형AI 개념 시리즈 — 기획된 주제 목록을 하루 1편씩 글로 써서 발행한다.

career_series.py 는 본문까지 손으로 써 두었지만, 여기는 주제 수가 많고 설명 글이라
**주제·관점만 목록으로 두고 본문은 Claude 가 쓴다**. 주제 목록이 있으므로 매번
'무슨 글을 쓸지' 흔들리지 않고, 순서대로 빠짐없이 나간다.

사용:
    python geoai_series.py --dry     # 오늘 나갈 1편을 생성만 하고 보여준다(발행 안 함)
    python geoai_series.py --plan    # 무엇이 남았는지만 출력(API 호출 없음)
    python geoai_series.py --go      # 실제 발행(보통은 geoai_daily.py 가 호출)
"""
import json
import os
import random
import re
import sys
from datetime import datetime

from anthropic import Anthropic

from common import BASE_DIR, load_config, log
from geoai_blogger import channel_links_html, publish, service, blog_id, posted_titles
from post_blogger import _esc

STATE_PATH = os.path.join(BASE_DIR, "geoai_state.json")

# (slug, 제목, 글의 관점/꼭 다룰 것, 태그) — 순서대로 하루 1편씩 나간다.
# 앞쪽은 GeoAI 개념, 뒤쪽(genai-*)은 생성형 AI 사용법이다(블로그 이름의 나머지 절반).
# 제목은 사람들이 실제로 검색할 말로 짓는다(개념어 + '무엇/어떻게').
GEO_TOPICS = [
    ("what-is-geoai", "GeoAI란 무엇인가? 공간정보와 인공지능이 만나면",
     "GeoAI 의 정의, 기존 GIS 분석과 무엇이 다른지, 어디에 쓰이는지(재난·도시·농업·환경). 첫 편이므로 시리즈 전체 지도를 간단히 보여준다.",
     ["GeoAI", "공간정보", "GIS", "인공지능"]),
    ("gis-vs-geoai", "GIS와 GeoAI는 어떻게 다른가 | 규칙 기반과 학습 기반",
     "전통 GIS 의 규칙·수식 기반 분석과 학습 기반 모델의 차이, 각각 잘하는 일과 한계, 둘을 섞어 쓰는 실제 흐름.",
     ["GIS", "GeoAI", "공간분석"]),
    ("satellite-basics", "위성영상 기초 | 해상도·밴드·광학과 SAR의 차이",
     "공간/시간/분광 해상도, 광학과 SAR 의 차이와 장단점(구름·야간), 재난 상황에서 어느 쪽을 쓰는지.",
     ["위성영상", "원격탐사", "SAR"]),
    ("spectral-index", "NDVI·NDWI는 무엇을 보는 지표인가",
     "분광 지수의 원리(반사 특성), NDVI·NDWI·NBR 이 각각 무엇을 드러내는지, 산불 피해·가뭄·침수 판독에 쓰는 방법.",
     ["NDVI", "원격탐사", "분광지수"]),
    ("qgis-start", "QGIS 입문 | 처음 열고 무엇부터 해보면 되나",
     "무료 오픈소스 GIS 로 시작하는 법, 좌표계·레이어·속성테이블이라는 세 가지 기본 개념, 첫 실습 과제 제안.",
     ["QGIS", "GIS입문", "오픈소스GIS"]),
    ("crs-basics", "좌표계(CRS)가 헷갈릴 때 | EPSG:4326과 5186",
     "지리좌표계와 투영좌표계의 차이, 한국에서 자주 쓰는 EPSG 코드, 좌표계가 어긋났을 때 생기는 증상과 해결 순서.",
     ["좌표계", "EPSG", "GIS"]),
    ("geopandas", "파이썬으로 공간분석 시작하기 | GeoPandas 기초",
     "GeoDataFrame 개념, 파일 읽기·좌표변환·공간조인 흐름을 짧은 코드로. 엑셀·QGIS 로 하던 일을 코드로 옮길 때의 이점.",
     ["GeoPandas", "파이썬", "공간분석"]),
    ("earth-engine", "Google Earth Engine이란? 클라우드에서 위성영상 분석",
     "내 컴퓨터에 영상을 내려받지 않고 분석하는 방식, 컬렉션·필터·리듀서라는 사고 틀, 어떤 작업에 특히 유리한지.",
     ["EarthEngine", "위성영상", "클라우드"]),
    ("label-data", "공간 AI의 학습 데이터는 어떻게 만드나 | 라벨링과 품질",
     "위성·드론 영상 라벨링 방식(점·폴리곤·마스크), 클래스 불균형과 지역 편향 문제, 좋은 데이터셋의 조건.",
     ["학습데이터", "라벨링", "GeoAI"]),
    ("cnn-remote-sensing", "위성영상에 딥러닝을 쓰면 | 분류·탐지·분할의 차이",
     "영상 분류, 객체 탐지, 의미론적 분할이 각각 답하는 질문과 산출물, 재난 판독에서 어느 것을 골라야 하는지.",
     ["딥러닝", "객체탐지", "영상분할"]),
    ("landcover", "토지피복 분류 | 위성으로 땅의 쓰임을 읽는 법",
     "토지피복 분류의 개념과 쓰임(도시화·불투수면·유출계수), 정확도 평가(혼동행렬·카파)를 쉬운 말로.",
     ["토지피복", "원격탐사", "정확도평가"]),
    ("sar-flood", "SAR 위성으로 침수 지역을 찾는 원리",
     "물이 SAR 영상에서 어둡게 보이는 이유, 변화탐지로 침수 범위를 잡는 절차, 오탐(그림자·매끈한 지면) 주의점.",
     ["SAR", "침수", "재난탐지"]),
    ("landslide-susceptibility", "산사태 위험지도는 어떻게 만드나 | 취약성 모델링",
     "경사·지질·강우 등 입력 인자, 통계·머신러닝 취약성 모델의 흐름, 지도 해석 시 주의할 점(확률이지 예언이 아니다).",
     ["산사태", "위험지도", "머신러닝"]),
    ("wildfire", "산불을 위성으로 감시하고 피해를 추정하는 법",
     "열적외 밴드 기반 화점 탐지, dNBR 로 피해 심도 산정, 조기 감지와 사후 평가의 역할 차이.",
     ["산불", "원격탐사", "dNBR"]),
    ("drone-mapping", "드론 사진측량 | 사진 몇 장이 지도가 되기까지",
     "중복도·GCP·SfM 처리 흐름, 산출물(정사영상·DSM·점군)과 재난 현장에서의 활용, 비행 전 확인할 제도적 사항.",
     ["드론", "사진측량", "정사영상"]),
    ("lidar-dem", "LiDAR와 DEM | 지형 데이터가 방재에 쓰이는 방식",
     "DSM 과 DEM 의 차이, LiDAR 로 수목 아래 지형을 얻는 원리, 침수·산사태 모의에 지형 정확도가 중요한 이유.",
     ["LiDAR", "DEM", "지형분석"]),
    ("interpolation", "관측점 사이는 어떻게 채우나 | 공간 보간과 크리깅",
     "IDW·크리깅 등 보간의 기본 아이디어, 강우·미세먼지 지도에서의 사용, 보간 결과를 과신하면 안 되는 이유.",
     ["공간보간", "크리깅", "공간통계"]),
    ("spatial-autocorrelation", "가까운 것은 닮는다 | 공간 자기상관과 핫스팟 분석",
     "토블러의 제1법칙, Moran's I 와 핫스팟(Getis-Ord) 의 의미, 사고·재난 발생 지점 분석에 쓰는 방법.",
     ["공간통계", "핫스팟분석", "공간자기상관"]),
    ("change-detection", "시계열 변화탐지 | 같은 곳을 다른 시점으로 비교하기",
     "전후 비교와 시계열 분해의 차이, 계절·촬영조건이 만드는 가짜 변화, 개발·침수·붕괴 판독 사례.",
     ["변화탐지", "시계열", "위성영상"]),
    ("digital-twin", "디지털트윈은 지도와 무엇이 다른가",
     "정적 지도 → 3차원 모델 → 실시간 연동 모델로 이어지는 단계, 도시 침수·대피 시뮬레이션에서의 쓰임과 한계.",
     ["디지털트윈", "스마트시티", "시뮬레이션"]),
    ("foundation-model", "지구관측 파운데이션 모델이란 | 범용 모델이 지도에 오다",
     "대규모 사전학습 모델이 원격탐사에 들어오며 달라진 점(적은 라벨로 적응), 분할 기반 모델의 활용 방식과 검증 필요성.",
     ["파운데이션모델", "GeoAI", "원격탐사"]),
    ("llm-for-gis", "생성형 AI로 공간분석 코드를 짜는 법",
     "LLM 에게 공간분석을 시킬 때의 요령(데이터 스키마·좌표계·검증 요구), 자주 나오는 오류와 결과를 반드시 눈으로 확인해야 하는 이유.",
     ["생성형AI", "LLM", "공간분석"]),
    ("gis-agent", "자연어로 지도를 묻는다 | LLM 에이전트와 GIS 연동",
     "도구 호출(function calling)로 GIS 기능을 붙이는 구조, 자연어 질의가 공간 질의로 번역되는 과정, 신뢰성 확보 장치.",
     ["LLM", "AI에이전트", "GIS"]),
    ("rag-manual", "재난 매뉴얼 챗봇 만들기 | RAG의 기본 구조",
     "검색증강생성(RAG)의 구성요소, 매뉴얼·조례처럼 근거가 중요한 문서에 왜 적합한지, 출처 표기와 최신성 관리.",
     ["RAG", "생성형AI", "재난매뉴얼"]),
    ("geoai-ethics", "GeoAI의 그늘 | 프라이버시·편향·오탐의 대가",
     "위치정보의 민감성, 학습 데이터 지역 편향, 오탐/미탐이 재난 대응에서 갖는 비대칭적 비용, 공개 시 지켜야 할 원칙.",
     ["AI윤리", "프라이버시", "GeoAI"]),
    ("geoai-career", "GeoAI로 진로를 잡으려면 | 배울 것과 포트폴리오",
     "필요한 역량 묶음(GIS·프로그래밍·도메인), 단계별 학습 순서, 포트폴리오로 쓸 만한 프로젝트 예시와 공개 데이터.",
     ["GeoAI진로", "포트폴리오", "공간정보"]),
    ("flood-hazard-map", "홍수위험지도·침수예상도는 어떻게 만들고 어디서 보나",
     "침수예상도가 무엇을 가정한 지도인지(강우 빈도·제방 붕괴 시나리오), 만드는 과정(지형·수리모형·토지이용), "
     "국민재난안전포털·홍수위험지도정보시스템에서 내 동네 지도를 찾아보는 법, 이 지도를 읽을 때의 한계.",
     ["홍수위험지도", "침수예상도", "재난안전"]),
    ("shelter-siting", "대피소는 어디에 둬야 하나 | 입지 분석과 접근성",
     "대피소 입지의 조건(위험지 회피·도보 접근성·수용력), 접근성을 거리 대신 '도달 시간'으로 보는 이유, "
     "GIS 로 취약지(도달 못 하는 구역)를 찾아내는 절차, 고령자·이동약자를 고려할 때 달라지는 결과.",
     ["대피소", "입지분석", "공간분석"]),
    ("population-grid", "격자 인구 데이터 | 밤낮으로 달라지는 위험 인구 읽기",
     "행정구역 단위 인구의 한계, 격자(100m·1km) 인구와 생활인구의 차이, 주간·야간 인구가 뒤바뀌는 지역의 의미, "
     "재난 피해 규모를 추정할 때 어떤 인구를 써야 하는지.",
     ["격자인구", "생활인구", "재난피해추정"]),
    ("urban-heat", "폭염은 도시 안에서도 다르다 | 열섬 지도 만들기",
     "도시열섬이 생기는 원리(피복·건물·녹지), 위성 열적외 밴드로 지표온도를 보는 법, "
     "그늘막·쿨링포그 같은 대책의 위치를 정할 때 지도가 하는 역할.",
     ["폭염", "도시열섬", "지표온도"]),
    ("openstreetmap", "무료 지도 데이터 OpenStreetMap, 재난 대응에 쓰는 법",
     "OSM 이 무엇이고 누가 만드는지, 도로·건물 데이터를 내려받아 쓰는 방법, "
     "재난 발생 시 전 세계가 함께 지도를 그리는 인도적 매핑(HOT), 품질이 지역마다 다르다는 점과 확인 방법.",
     ["OpenStreetMap", "오픈데이터", "재난지도"]),
    ("public-geodata", "공공데이터로 시작하는 공간분석 | 어디서 무엇을 받나",
     "국가공간정보포털·브이월드·공공데이터포털·통계지리정보의 역할 구분, 자주 쓰는 자료(행정경계·건물·도로·지적), "
     "받은 파일이 열리지 않을 때 점검할 것(좌표계·인코딩·용량), 이용 조건과 출처 표기.",
     ["공공데이터", "국가공간정보", "브이월드"]),
    ("sentinel-download", "위성영상 직접 받아보기 | Copernicus에서 Sentinel 내려받기",
     "무료로 받을 수 있는 위성영상의 종류, Copernicus Browser 에서 지역·기간·구름량으로 찾는 순서, "
     "받은 영상을 QGIS 에서 여는 법, 밴드 조합을 바꿔 보는 첫 실습.",
     ["Sentinel", "위성영상", "Copernicus"]),
    ("accuracy-assessment", "내 분석은 얼마나 맞았나 | 정확도 평가와 혼동행렬",
     "검증 표본을 따로 두어야 하는 이유, 혼동행렬 읽는 법, 전체 정확도만 보면 속는 경우(드문 사건), "
     "재난 탐지에서 놓침(미탐)과 헛경보(오탐) 중 무엇을 더 줄여야 하는지.",
     ["정확도평가", "혼동행렬", "모델검증"]),
    ("web-map", "웹지도 만들기 | 분석 결과를 남에게 보여주는 법",
     "결과를 이미지가 아니라 지도로 공유하는 이점, QGIS 에서 웹지도로 내보내는 방법, "
     "간단한 웹지도 도구들, 공개할 때 지우거나 가려야 할 정보(위치 프라이버시).",
     ["웹지도", "지도공유", "QGIS"]),
    ("gps-accuracy", "GPS는 왜 흔들리나 | 위치 오차와 보정(RTK)의 기본",
     "위성측위 오차의 원인(전리층·다중경로·건물), 스마트폰 위치가 수 미터 튀는 이유, "
     "RTK·네트워크 보정으로 센티미터급을 얻는 원리, 현장 조사에서 어느 정도 정확도가 필요한지.",
     ["GPS", "위치정확도", "RTK"]),
    ("network-analysis", "소방차는 몇 분에 닿나 | 도로망 분석과 골든타임",
     "도로망 위의 최단경로와 직선거리의 차이, 도달권(서비스 영역) 분석으로 사각지대를 찾는 법, "
     "시간대별 속도를 넣으면 결과가 달라지는 이유, 소방·구급 배치 검토에 쓰이는 방식.",
     ["도로망분석", "골든타임", "소방"]),
    ("earthquake-geoai", "지진 피해를 위성과 AI로 빠르게 파악하기",
     "지진 직후 필요한 정보와 현장 조사의 한계, 전후 영상 비교로 붕괴 건물을 찾는 방법, "
     "InSAR 로 지표 변위를 보는 원리, 빠른 추정이 구조 자원 배분에 쓰이는 흐름.",
     ["지진", "InSAR", "피해추정"]),
    ("debris-flow", "토석류와 급경사지 | 위험지 판정에 쓰는 공간 데이터",
     "토석류가 발생하는 조건(경사·토심·강우), 급경사지 붕괴위험지역 지정에 쓰이는 자료, "
     "산사태 위험지도와 무엇이 다른지, 주택 뒤 경사면을 스스로 살펴볼 때의 관점.",
     ["토석류", "급경사지", "산사태"]),
    ("air-dispersion", "미세먼지·유해가스 확산을 지도로 보는 법",
     "확산 모델이 무엇을 계산하는지(배출·바람·지형), 측정소 값과 모델 값의 차이, "
     "화학사고 때 대피 범위를 정하는 데 쓰이는 방식, 지도를 볼 때 오해하기 쉬운 점.",
     ["대기확산", "화학사고", "미세먼지"]),
    ("damage-survey", "재난 피해조사, 드론과 AI로 줄이는 시간",
     "피해조사가 오래 걸리는 이유, 드론 촬영으로 현장을 통째로 기록하는 절차, "
     "AI 로 피해 건물·농경지를 세는 방법과 한계, 조사 결과가 복구 지원으로 이어지는 흐름.",
     ["피해조사", "드론", "재난복구"]),
    ("geoai-toolmap", "GeoAI 도구 지도 | 무엇을 언제 쓰나",
     "QGIS·파이썬·Earth Engine·클라우드 서비스의 쓰임을 한 장으로 정리, 자료 크기와 목적에 따른 선택 기준, "
     "처음 배우는 사람이 밟으면 좋은 순서, 도구보다 먼저 정해야 하는 '무엇을 알고 싶은가'.",
     ["GeoAI", "QGIS", "도구선택"]),
    ("geo-physical-ai", "Geo-Physical AI란? 물리 법칙을 아는 공간 AI",
     "데이터만 보고 배운 모델이 물리적으로 말이 안 되는 답을 내놓는 경우(물이 위로 흐르거나 "
     "질량이 사라지는 식), 물리 법칙을 학습에 함께 넣는다는 발상, 물리정보 신경망(PINN)이 "
     "무엇을 어떻게 제약하는지 쉬운 말로, 수치 시뮬레이션(침수·확산 모델)과 AI 를 "
     "대체가 아니라 짝으로 쓰는 방식(시뮬레이션 결과로 학습시켜 빠른 근사 모델을 만들기), "
     "재난 분야에서 기대되는 지점(실시간 침수 예측·산불 확산·대기 확산처럼 몇 시간 걸리던 "
     "계산을 몇 초로), 관측이 드문 곳에서도 덜 틀리는 이유(법칙이 빈칸을 잡아 준다), "
     "그래도 남는 한계(경계 조건·지형 자료의 품질, 검증 없이는 못 쓴다), "
     "디지털트윈·지구관측 파운데이션 모델과 어떻게 이어지는지. "
     "특정 제품이나 벤치마크 수치는 말하지 않는다.",
     ["GeoPhysicalAI", "물리정보신경망", "PINN", "재난예측"]),
]

# 생성형 AI 사용법 계열 — 위 GeoAI 계열과 번갈아 나간다.
GENAI_TOPICS = [
    ("genai-prompt", "생성형 AI 사용법 1 | 프롬프트는 이렇게 쓴다",
     "좋은 프롬프트의 구성(역할·맥락·형식·제약), 막연한 질문과 구체적 요청의 결과 차이, 되묻게 만드는 요령. 공간정보·재난안전 업무 예시로 설명한다.",
     ["생성형AI", "프롬프트", "AI활용"]),
    ("genai-doc", "생성형 AI 사용법 2 | 보고서와 자료 정리에 쓰는 법",
     "긴 문서 요약·표 정리·초안 작성에 쓰는 절차, 원문을 함께 주는 것이 중요한 이유, 결과를 검증하는 순서. 공문·계획서처럼 근거가 필요한 문서에서의 주의점.",
     ["생성형AI", "AI활용", "문서작성"]),
    ("genai-hallucination", "생성형 AI 사용법 3 | 틀린 답(환각)을 걸러내는 법",
     "환각이 생기는 이유를 쉬운 말로, 숫자·법령·출처가 걸린 답을 확인하는 습관, 출처를 요구하는 프롬프트, 확인 없이 쓰면 안 되는 항목들.",
     ["생성형AI", "AI윤리", "팩트체크"]),
    ("genai-image", "생성형 AI 사용법 4 | 이미지 생성과 저작권 주의점",
     "이미지 생성 도구의 기본 사용 흐름, 자료용 이미지에 쓸 때의 한계(지도·통계는 생성하면 안 된다), 표기와 저작권·초상권에서 조심할 점.",
     ["생성형AI", "이미지생성", "저작권"]),
    ("genai-code", "생성형 AI 사용법 5 | 코드를 모르는 사람의 데이터 처리",
     "엑셀·CSV 정리, 간단한 파이썬 코드 요청, 결과를 눈으로 검증하는 방법. 공간데이터를 다룰 때 좌표계·단위를 반드시 확인해야 하는 이유.",
     ["생성형AI", "데이터분석", "파이썬"]),
    ("genai-safety-drill", "생성형 AI 사용법 6 | 안전 훈련 시나리오 만들기",
     "재난 대응 훈련 시나리오·체크리스트 초안을 AI로 만드는 절차, 지역 특성과 실제 매뉴얼을 함께 넣어야 하는 이유, 전문가 검토가 반드시 필요한 지점.",
     ["생성형AI", "안전훈련", "재난대응훈련"]),
    ("genai-meeting", "생성형 AI 사용법 7 | 회의록과 업무 메일 빠르게 정리하기",
     "녹취·메모를 회의록 형태로 다듬는 절차, 결정사항과 할 일을 따로 뽑아내는 프롬프트, "
     "메일 초안을 쓸 때 어조와 분량을 지정하는 법, 사람 이름·소속처럼 틀리면 안 되는 항목을 확인하는 습관.",
     ["생성형AI", "회의록", "업무효율"]),
    ("genai-excel", "생성형 AI 사용법 8 | 표와 숫자를 다룰 때의 요령",
     "엑셀 수식·피벗을 말로 요청하는 방법, 표를 붙여 넣을 때 형식을 지키는 요령, "
     "합계·평균을 AI 가 직접 계산하게 두면 위험한 이유(계산은 도구에 맡긴다), 결과를 눈으로 검산하는 순서.",
     ["생성형AI", "엑셀", "데이터정리"]),
    ("genai-slides", "생성형 AI 사용법 9 | 발표자료 초안 만들기",
     "목차부터 잡는 순서, 슬라이드 한 장에 한 메시지를 넣게 하는 프롬프트, "
     "발표 시간에 맞춰 분량을 조절하는 법, 도표·이미지는 어디까지 AI 에 맡기고 어디부터 직접 만들어야 하는지.",
     ["생성형AI", "발표자료", "문서작성"]),
    ("genai-translate", "생성형 AI 사용법 10 | 번역과 외국 자료 읽기",
     "기계번역과 생성형 AI 번역의 차이, 전문용어를 고정하는 방법(용어집을 함께 주기), "
     "논문·기술문서를 읽을 때 요약에 기대지 않고 확인하는 지점, 번역문을 공식 문서로 쓸 때의 책임.",
     ["생성형AI", "번역", "논문읽기"]),
    ("genai-security", "생성형 AI 사용법 11 | 업무에 쓸 때의 정보 보안 선",
     "입력한 내용이 어디까지 가는지, 개인정보·내부자료·미공개 문서를 넣으면 안 되는 이유, "
     "지워야 할 항목을 먼저 걸러내는 습관, 기관에서 쓸 때 확인할 것(이용약관·학습 사용 여부·승인된 도구).",
     ["생성형AI", "정보보안", "개인정보"]),
    ("genai-compare", "생성형 AI 사용법 12 | 어떤 도구를 쓸까",
     "도구를 고르는 기준(글쓰기·검색·코드·이미지), 무료와 유료가 실제로 갈리는 지점, "
     "같은 질문을 여러 도구에 던져 비교해 보는 방법, 하나에만 의존하지 않는 편이 나은 이유.",
     ["생성형AI", "AI도구", "AI활용"]),
    ("genai-study", "생성형 AI 사용법 13 | 공부와 자료조사에 쓰는 법",
     "모르는 분야를 빠르게 훑는 순서, 요약에 속지 않기 위해 원문으로 되돌아가는 습관, "
     "스스로 이해했는지 확인하는 '설명하게 하기' 활용, 과제·보고서에 쓸 때의 인용과 표기.",
     ["생성형AI", "공부법", "자료조사"]),
    ("genai-workflow", "생성형 AI 사용법 14 | 반복 업무를 줄이는 나만의 프롬프트 모음",
     "매번 새로 쓰지 않고 형식을 재사용하는 방법, 자주 쓰는 프롬프트를 정리해 두는 방식, "
     "맥락(기관·업무·말투)을 미리 넣어 두면 달라지는 결과, 한 달 써 보고 다듬는 요령.",
     ["생성형AI", "업무자동화", "프롬프트"]),
    ("genai-refine", "생성형 AI 사용법 15 | 답이 시원찮을 때 프롬프트를 고치는 법",
     "한 번에 완벽한 프롬프트를 쓰려 하지 말고 첫 답을 보고 고쳐 가는 것이 실제 방식이라는 점. "
     "받은 답의 증상으로 원인을 짚는 법 — 너무 뻔하고 일반적이면 맥락이 없는 것, 형식이 안 맞으면 "
     "형식을 안 준 것, 엉뚱한 곳을 길게 늘어놓으면 범위를 안 좁힌 것, 사실이 틀리면 근거를 "
     "안 준 것. 증상별 처방 네 가지를 짝지어 보여 준다(맥락 넣기, 원하는 형식 보여 주기, "
     "'무엇은 빼라'로 범위 좁히기, 원문을 붙여 주고 그 안에서만 쓰게 하기). "
     "예시를 한두 개 직접 보여 주면 설명보다 빠르게 잡힌다는 점(few-shot)도 다룬다. "
     "한 번에 한 가지만 바꿔야 무엇이 효과가 있었는지 알 수 있다는 것, "
     "대화를 이어서 고칠 때와 새 대화로 다시 시작하는 편이 나을 때의 구분(앞의 틀린 답이 "
     "계속 끌려오는 경우), 마음에 드는 답이 나왔으면 그 프롬프트를 바로 저장해 두라는 마무리. "
     "1편이 프롬프트의 구성 요소를 다룬다면 이 편은 '고쳐 쓰는 과정'을 다룬다.",
     ["프롬프트", "생성형AI", "프롬프트수정", "AI활용"]),
]

# 안전한국훈련 문서 실무 계열 — 생성형 AI 로 초안을 잡고 hwpx 스킬로 한글 문서를 만든다.
SAFETYDOC_TOPICS = [
    ("safetydoc-basic", "안전한국훈련 기본계획서, 생성형 AI로 쓰는 법",
     "기본계획서가 무엇을 담는 문서인지(훈련 목적·대상 재난·참여기관·일정·훈련 유형·평가 방향), "
     "AI 에게 반드시 함께 줘야 할 맥락(기관 성격·규모·지역 위험요소·전년도 훈련 결과), "
     "막연한 요청과 맥락을 준 요청의 결과 차이, 프롬프트 예시 한 개, "
     "AI 가 지어내기 쉬운 항목(근거 법령·지침 번호·기관명·연도)은 원문으로 확인해야 한다는 점, "
     "마지막에 hwpx 스킬로 한글 문서(.hwpx) 형태로 내려받아 결재선에 올리는 흐름.",
     ["안전한국훈련", "생성형AI", "기본계획서", "HWPX"]),
    ("safetydoc-plan", "안전한국훈련 실시계획서, AI로 초안 잡고 검토하기",
     "실시계획서가 기본계획서와 무엇이 다른지(누가·언제·어디서·무엇을 하는지까지 구체화), "
     "시간대별 진행표·역할분담·안전관리·평가항목을 AI 에게 표 형태로 받는 요령, "
     "기본계획서 내용을 그대로 물려주는 방법(문서를 통째로 붙여 넣고 '이 범위 안에서' 라고 제한), "
     "현장에서 지켜지지 않을 계획을 걸러내는 검토 질문들, hwpx 로 표까지 살려 한글 문서로 만드는 순서.",
     ["안전한국훈련", "생성형AI", "실시계획서", "HWPX"]),
    ("safetydoc-scenario", "훈련 시나리오 쓰기 | 생성형 AI로 상황 부여와 진행표 만들기",
     "시나리오가 계획서와 다른 점(상황 부여와 대응 흐름), 상황 부여 카드의 구성(시각·상황·전달 대상·기대 조치), "
     "지역 위험요소와 실제 매뉴얼을 넣어야 현실적인 시나리오가 나오는 이유, "
     "돌발 상황(통신 두절·부상자 발생)을 추가해 난이도를 올리는 프롬프트, "
     "AI 시나리오를 그대로 쓰면 안 되는 이유와 전문가 검토 지점, hwpx 로 진행표를 한글 문서로 만드는 마무리.",
     ["안전한국훈련", "생성형AI", "훈련시나리오", "재난대응훈련"]),
    ("safetydoc-evaluation", "훈련 평가보고서, 생성형 AI로 정리하는 법",
     "평가보고서가 담아야 할 것(훈련 개요·평가 항목별 결과·미흡 사항·개선 과제), "
     "현장 기록과 평가표를 통째로 주고 '이 자료 안에서만' 쓰게 제한하는 요령, "
     "잘된 점만 나열되지 않게 개선 과제를 끌어내는 프롬프트, 수치와 기관명은 반드시 원문 확인, "
     "hwpx 로 표까지 살려 한글 문서를 만드는 마무리.",
     ["안전한국훈련", "생성형AI", "평가보고서", "HWPX"]),
    ("safetydoc-checklist", "현장 점검표와 체크리스트, AI로 만들기",
     "점검표가 쓸모 있으려면 갖춰야 할 것(대상·주기·판정 기준·조치), 법정 점검 항목을 빠뜨리지 않는 방법, "
     "'예/아니오'로 끝나지 않고 조치까지 적게 만드는 구성, 현장에서 실제로 쓰이는지 확인하는 검토 질문, "
     "hwpx 로 인쇄용 점검표를 만드는 순서.",
     ["안전점검", "생성형AI", "체크리스트", "HWPX"]),
    ("safetydoc-manual", "부서 재난 대응 매뉴얼 손보기 | AI로 최신화하는 절차",
     "매뉴얼이 낡는 이유(조직 개편·연락망·법령 개정), 기존 매뉴얼을 통째로 주고 바뀐 부분만 찾게 하는 방법, "
     "연락망·역할분담처럼 지어내면 위험한 항목을 표시해 두는 요령, 개정 이력을 남기는 방식, "
     "hwpx 로 개정판을 만드는 마무리.",
     ["재난대응매뉴얼", "생성형AI", "문서최신화", "HWPX"]),
    ("safetydoc-sitrep", "상황보고서 쓰기 | 재난 상황에서 빠르고 정확하게",
     "상황보고서의 기본 골격(발생 개요·피해·조치·향후 계획), 시간이 없을 때 먼저 채워야 할 칸, "
     "확인된 사실과 추정을 구분해 적는 습관, 보고 차수가 올라갈 때 달라지는 내용, "
     "AI 에 맡길 부분(문장 다듬기)과 맡기면 안 되는 부분(피해 숫자)의 경계.",
     ["상황보고서", "생성형AI", "재난대응", "HWPX"]),
    ("safetydoc-official", "공문과 협조요청, AI로 초안 잡기",
     "공문의 형식(제목·근거·요청 사항·기한)과 말투, 근거 법령·지침을 AI 가 지어내기 쉬우므로 직접 넣어 주는 방법, "
     "협조요청이 실제로 움직이게 하는 요소(무엇을·언제까지·누구에게), 발송 전 점검표, "
     "hwpx 로 기안 문서를 만드는 흐름.",
     ["공문작성", "생성형AI", "기안문", "HWPX"]),
    ("safetydoc-debrief", "사후강평 자료, 생성형 AI로 만드는 법",
     "사후강평이 평가보고서와 다른 점(개선을 위한 토론 자료), 시간 순 진행 기록에서 쟁점을 뽑아내는 방법, "
     "책임 추궁이 아니라 원인과 구조를 보게 만드는 질문 구성, 다음 훈련 과제로 잇는 정리, "
     "hwpx 로 발표용 자료를 만드는 마무리.",
     ["사후강평", "생성형AI", "훈련개선", "HWPX"]),
]

# 순서를 섞되 매 실행 같은 결과가 나오게 하는 씨앗. 씨앗을 바꾸면 배치가 통째로
# 달라진다. 계열에 주제를 더 넣어도 마찬가지다(슬롯 수가 달라져 섞임이 바뀐다) —
# 이미 발행된 편은 slug 로 걸러지므로 다시 나가지는 않고, 아직 안 나간 편들의
# 차례만 바뀐다. 주제를 추가할 때는 반드시 계열 '끝에' 덧붙인다 — 중간에 끼워
# 넣으면 SERIES_NO(계열 안 회차 번호)가 밀려 이미 발행된 편의 번호가 어긋난다.
SHUFFLE_SEED = 57


def _publish_order(head=2, seed=SHUFFLE_SEED):
    """발행 순서를 만든다 — 계열이 섞이되 계열 안 순서는 지킨다.

    섞는 것은 '어느 계열을 낼 차례인가' 뿐이다. 계열 안에서는 정의한 순서대로 나간다
    — 기본계획서 → 실시계획서 → 시나리오처럼 순서가 곧 내용인 편들이 뒤집히면 안 된다.
    head: 이미 발행된 앞쪽 편은 자리를 그대로 둔다.
    씨앗을 고정했으므로 목록은 매번 같다(실행마다 순서가 바뀌면 '다음 편' 예고와
    중복 판단이 어긋난다). 다르게 섞고 싶으면 씨앗만 바꾸면 된다."""
    queues = [list(GEO_TOPICS[head:]), list(GENAI_TOPICS), list(SAFETYDOC_TOPICS)]
    slots = [i for i, q in enumerate(queues) for _ in q]
    random.Random(seed).shuffle(slots)
    return list(GEO_TOPICS[:head]) + [queues[i].pop(0) for i in slots]


TOPICS = _publish_order()

# 계열 안에서의 회차 번호. 배치 순서를 바꿔도 번호가 흔들리지 않게 계열별로 센다
# (GeoAI 기초 1·2편은 이미 발행돼 있어 번호가 바뀌면 안 된다).
SERIES_NO = {}
for _fam in (GEO_TOPICS, GENAI_TOPICS, SAFETYDOC_TOPICS):
    SERIES_NO.update({t[0]: i for i, t in enumerate(_fam, start=1)})

FAMILIES = {                       # slug 접두사 → (표시 이름, 그 계열 목록)
    "genai-": ("생성형AI 사용법", GENAI_TOPICS),
    "safetydoc-": ("안전한국훈련 실무", SAFETYDOC_TOPICS),
}


def family_of(slug):
    for pre, (label, topics) in FAMILIES.items():
        if slug.startswith(pre):
            return label, topics
    return "GeoAI 기초", GEO_TOPICS



# 계열별 추가 지침 — 글 성격이 달라 본문 요구사항을 조금 다르게 준다.

# ─── 카테고리 ────────────────────────────────────────────────────────────────
# Blogger 에는 카테고리가 따로 없고 라벨이 그 역할을 한다. 주제 태그는 글마다 달라서
# (글 5편에 라벨 45종이던 때가 있다) 라벨 목록이 카테고리 구실을 못 했다. 그래서
# 글마다 반드시 하나씩 붙는 '카테고리 라벨'을 따로 둔다 — 이것만 레이아웃의 라벨
# 가젯에 띄우면 카테고리 메뉴가 된다.
# 계열(FAMILIES)과 따로 두는 이유: GeoAI 계열 42편을 한 칸에 넣으면 카테고리 하나에
# 글이 몰린다. 그래서 GeoAI 계열만 개념 / 도구 / 현장 셋으로 나눈다.
CATEGORIES = ("GeoAI 개념", "GIS 도구", "재난 현장 활용",
              "생성형AI 사용법", "안전한국훈련 실무")

_CAT_CONCEPT = {
    "what-is-geoai", "gis-vs-geoai", "satellite-basics", "spectral-index",
    "label-data", "cnn-remote-sensing", "landcover", "digital-twin",
    "foundation-model", "geoai-ethics", "geoai-career", "population-grid",
    "geo-physical-ai",
}
_CAT_TOOLS = {
    "qgis-start", "crs-basics", "geopandas", "earth-engine", "interpolation",
    "spatial-autocorrelation", "change-detection", "llm-for-gis", "gis-agent",
    "rag-manual", "openstreetmap", "public-geodata", "sentinel-download",
    "accuracy-assessment", "web-map", "gps-accuracy", "geoai-toolmap",
}
_CAT_FIELD = {
    "sar-flood", "landslide-susceptibility", "wildfire", "drone-mapping",
    "lidar-dem", "flood-hazard-map", "shelter-siting", "urban-heat",
    "network-analysis", "earthquake-geoai", "debris-flow", "air-dispersion",
    "damage-survey",
}


def category_of(slug):
    """글 하나가 들어갈 카테고리(라벨) 하나. 모든 글이 반드시 하나를 갖는다."""
    if slug.startswith("genai-"):
        return "생성형AI 사용법"
    if slug.startswith("safetydoc-"):
        return "안전한국훈련 실무"
    if slug in _CAT_TOOLS:
        return "GIS 도구"
    if slug in _CAT_FIELD:
        return "재난 현장 활용"
    return "GeoAI 개념"          # 분류에서 빠진 GeoAI 편의 기본값

FAMILY_HINT = {
    "safetydoc-": (
        "\n[이 글의 추가 요구사항]\n"
        "- 실무자가 그대로 따라 할 수 있게 '순서'로 쓴다: 무엇을 준비하고, AI 에게 무엇을 주고,\n"
        "  받은 초안에서 무엇을 고치고, 어떤 형식으로 마무리하는지.\n"
        "- 프롬프트 예시를 최소 1개는 통째로 보여 준다(따옴표 없이 줄바꿈으로 구분).\n"
        "- 법령 이름·지침 번호·연도·기관명은 지어내지 말고, '소관 부처 공고와 최신 지침을\n"
        "  확인하라'는 식으로 쓴다. 훈련 일정·규모도 해마다 달라진다는 점을 밝힌다.\n"
        "- AI 초안을 그대로 결재에 올리면 안 되는 이유와, 사람이 반드시 확인할 항목을 넣는다.\n"
        "- 마지막에 초안을 한글 문서(.hwpx)로 만드는 방법을 한 단락 넣는다. 복사해 붙여 넣는\n"
        "  방법과, 문서 변환 기능(예: Claude 의 hwpx 스킬)으로 바로 받는 방법을 함께 적는다.\n"
    ),
    "genai-": (
        "\n[이 글의 추가 요구사항]\n"
        "- 도구 이름을 특정해 단정하지 말고(서비스·요금·기능은 자주 바뀐다) 방법 중심으로 쓴다.\n"
        "- 따라하기 칸은 'AI 도구 화면에서 무엇을 어떤 순서로 하는가'로 쓴다 — 새 대화를 열고,\n"
        "  맥락을 먼저 주고, 형식을 지정하고, 받은 답을 어떻게 고쳐 달라고 하는지까지.\n"
        "- 프롬프트 칸에는 막연한 요청과 맥락을 준 요청을 대비해 2개를 넣으면 좋다.\n"
        "- 파일을 올리거나 문서로 내려받는 기능(예: Claude 의 hwpx 스킬로 한글 문서 받기)을\n"
        "  쓰는 편이면, 어떤 말로 요청하면 되는지 한 줄 예시를 넣는다.\n"
    ),
}

# 계열을 가리지 않고 모든 글에 붙는 지침 — '따라하기'와 '프롬프트' 칸의 품질을 잡는다.
COMMON_HINT = (
    "\n[따라하기·프롬프트 칸 작성 규칙]\n"
    "- 따라하기는 독자가 화면을 보며 그대로 따라갈 수 있어야 한다. '분석을 수행한다' 처럼\n"
    "  두루뭉술하게 쓰지 말고, 누르는 메뉴·입력하는 값·확인할 화면을 적는다.\n"
    "- 도구가 없는 개념 위주의 주제라도, 개념을 확인해 볼 수 있는 무료 도구나 공개 사이트로\n"
    "  따라하기를 만든다(예: 공개 지도 서비스에서 해당 현상을 눈으로 확인하는 순서).\n"
    "- 설치 경로·메뉴 이름은 버전에 따라 다를 수 있으므로 단정하지 말고, 못 찾을 때\n"
    "  어디를 보면 되는지 한 줄 덧붙인다.\n"
    "- 프롬프트는 실제로 붙여 넣으면 쓸 만한 답이 나오는 수준으로 구체적으로 쓴다.\n"
    "  역할·맥락·원하는 형식·하지 말아야 할 것이 들어가야 한다.\n"
    "- 프롬프트가 만들어 준 결과를 사람이 반드시 확인해야 하는 항목을 함께 적는다.\n"
)


def family_hint(slug):
    """계열별 지침 + 모든 글에 붙는 공통 지침(따라하기·프롬프트 품질)."""
    for pre, text in FAMILY_HINT.items():
        if slug.startswith(pre):
            return text + COMMON_HINT
    return COMMON_HINT


SYSTEM = """너는 공간정보(GIS)와 인공지능을 처음 배우는 사람에게 쉽게 설명하는 한국어 기술 블로그 작가다.
지켜야 할 원칙:
- 개념과 원리를 정확하게 설명한다. 확인되지 않은 수치, 연도, 기관명, 제품 사양, 논문 제목,
  최신 버전·순위 같은 것은 지어내지 않는다. 필요하면 "도구에 따라 다르다" 처럼 일반론으로 쓴다.
- 특정 제품/서비스의 현재 상태를 단정하지 않는다("현재 무료다", "가장 정확하다" 금지).
- 전문용어는 처음 나올 때 한 줄로 풀어 준다. 비유를 한두 개 쓰되 과장하지 않는다.
- 과장·공포 조장·낚시성 표현을 쓰지 않는다.
- 마크다운 강조 기호(#, *, - 등)를 쓰지 않는다. 코드 예시가 꼭 필요할 때만 ``` 로 감싼다.
- 출력은 반드시 지정된 구분자(===) 형식만 반환한다."""

USER = """시리즈: '재난안전과 GeoAI' 블로그의 개념 시리즈 {n}편
글 제목: {title}
이번 글의 관점(반드시 반영): {angle}
오늘 날짜: {today}
말투: 친근하지만 군더더기 없는 설명체(존댓말)

요구사항
- 전체 본문 2,000자 이상. 같은 말을 되풀이해 늘리지 말고 원리·예시·주의점으로 채운다.
- 본문 소제목은 4~5개, 사람들이 검색창에 칠 법한 '질문형'으로 쓴다.
  (예: "SAR 영상에서 물은 왜 어둡게 보이나요?")
- 소제목마다 맨 앞에 어울리는 이모지 1개.
- 각 소제목 본문은 300~450자. 마지막 1~2문장은 재난안전(홍수·산사태·산불·대피 등)이나
  실제 업무에서 이 개념이 어떻게 쓰이는지로 연결한다.
- 최소 한 곳에는 '해봐야 아는 것'(직접 확인할 절차나 판단 기준)을 넣는다.
- 코드 예시는 필요한 글에서만 3~10줄, ``` 로 감싼다. 없어도 된다.
- 도구를 다루는 글이면 본문 안에서도 메뉴 이름·버튼 이름을 그대로 적어 준다
  ('속성 테이블을 연다' 가 아니라 '레이어에서 오른쪽 클릭 > 속성 테이블 열기').

이미 발행한 글(내용이 겹치지 않게 참고):
{recent}

반드시 아래 형식 그대로 응답해. 마커(===)는 글자 그대로. 그 외 설명 금지.

===요약===
이 글의 핵심 3줄. 각 줄은 '· '로 시작하고 40자 내외, 한 줄에 하나의 내용만.
===도입===
이 개념이 왜 필요한지 보여주는 짧은 장면이나 질문으로 시작하는 1~2단락(250자 이상).
===본문===
## 🛰️ 질문형 소제목
본문 단락
## 🌊 질문형 소제목
본문 단락
(이런 식으로 4~5개. 소제목 줄은 반드시 '## ' 로 시작)
===따라하기===
이 글의 도구·프로그램을 실제로 쓰는 순서 4~6단계. 한 줄에 한 단계씩, 아래 형식만 쓴다.
단계이름 | 화면에서 무엇을 누르고 무엇을 입력하는지 (60자 내외, 구체적으로)
단계이름은 12자 이내의 명사구로 짧게 쓴다(도식 그림에 그대로 들어간다).
메뉴 경로는 '레이어 > 레이어 추가 > 벡터 레이어' 처럼 실제 이름으로 쓴다.
버전에 따라 메뉴 이름이 다를 수 있다는 점은 본문에서 한 번 밝힌다.
===프롬프트===
독자가 복사해 그대로 쓸 수 있는 프롬프트 1~2개. 각 프롬프트는 아래 형식.
쓰임: 이 프롬프트로 무엇을 얻는지 한 줄
그 다음 줄부터 프롬프트 본문을 여러 줄로 쓴다(빈 줄 없이 이어서).
역할·맥락·형식·제약이 드러나게 쓰고, 사용자가 채워 넣을 자리는 대괄호로 표시한다
(예: [기관명], [대상 재난]). '쓰임:' 은 각 프롬프트의 첫 줄에만 쓴다.
프롬프트 본문에는 마커(===)를 쓰지 않는다.
프롬프트가 어울리지 않는 주제면 이 칸은 '(없음)' 한 줄만 쓴다.
===해보기===
독자가 오늘 바로 해볼 수 있는 확인·실습 2~3가지. 각 줄은 '· '로 시작, 한 줄 한 가지.
무료로 접근 가능한 방법 위주로 쓰되, 특정 서비스의 가격·정책은 단정하지 않는다.
===FAQ===
이 주제로 사람들이 실제로 검색할 법한 질문 3개.
'Q. 질문' 다음 줄에 'A. 답변(2~3문장)' 형식.
===마무리===
한 단락(150자 이상). 다음 편으로 이어질 궁금증을 한 문장 남긴다.
===태그===
검색에 걸릴 만한 태그 8~11개를 쉼표로."""


def state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"posted": {}}


def save_state(s):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def post_title(topic):
    """발행 제목. 생성형 AI 편은 제목에 이미 '사용법 N' 이 들어 있어 덧붙이지 않는다."""
    slug, title = topic[0], topic[1]
    if slug.startswith("genai-"):
        return title
    label, _ = family_of(slug)
    return f"{title} | {label} {SERIES_NO.get(slug, 0)}편"


def next_topic(done_titles=()):
    """아직 안 나간 첫 주제. (로컬 상태 + 블로그에 실제로 있는 제목) 둘 다 본다.

    상태 파일이 지워지거나 다른 기기에서 돌아도 같은 글이 두 번 나가지 않게 한다."""
    done = set(state().get("posted", {}))
    for i, t in enumerate(TOPICS, start=1):
        if t[0] in done:
            continue
        if post_title(t) in done_titles:
            continue
        return i, t
    return None, None


def _split(text):
    """===마커=== 로 나눈 구간 dict."""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^===\s*([^=]+?)\s*===$", line.strip())
        if m:
            cur = m.group(1).strip()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


def _lines(block):
    return [re.sub(r"^[·\-•*]\s*", "", l).strip()
            for l in (block or "").splitlines() if l.strip()]


def _prose_html(text):
    """빈 줄로 나뉜 덩어리를 <p> 로. ``` 로 감싼 부분은 <pre> 로."""
    parts = []
    for i, seg in enumerate(re.split(r"```", text or "")):
        if i % 2:                                   # 코드 블록
            body = seg.strip("\n")
            body = re.sub(r"^[a-zA-Z0-9_+-]{0,12}\n", "", body)   # 첫 줄 언어 표기 제거
            if body.strip():
                parts.append("<pre style=\"background:#f6f8fa;padding:12px;"
                             "overflow-x:auto\"><code>" + _esc(body) + "</code></pre>")
            continue
        for chunk in re.split(r"\n\s*\n", seg.strip()):
            if chunk.strip():
                parts.append("<p>" + _esc(chunk.strip()).replace("\n", "<br>") + "</p>")
    return "\n".join(parts)



def _steps(block):
    """'단계이름 | 설명' 줄들을 [(이름, 설명)] 로. 도식 그림과 본문이 같은 값을 쓴다."""
    out = []
    for line in _lines(block):
        name, sep, desc = line.partition("|")
        if not sep:                         # 구분자를 안 지켰으면 앞 12자를 이름으로
            name, desc = line[:12], line
        out.append((name.strip()[:16], desc.strip()))
    return [(n, d) for n, d in out if n]


def _prompts(block):
    """'[쓰임] 한 줄' + 프롬프트 본문 묶음을 [(쓰임, 본문)] 로."""
    text = (block or "").strip()
    if not text or text.startswith("(없음)"):
        return []
    out = []
    # '쓰임:' 으로 시작하는 줄에서만 나눈다 — 프롬프트 본문의 [기관명] 같은 채움
    # 자리와 겹치지 않게 대괄호를 구분자로 쓰지 않는다.
    for chunk in re.split(r"^\s*쓰임\s*[:：]", text, flags=re.M):
        chunk = chunk.strip()
        if not chunk:
            continue
        head, _, body = chunk.partition("\n")
        use, body = head.strip(), body.strip()
        if not body:                       # '쓰임:' 없이 본문만 온 경우
            use, body = "", head.strip()
        if body:
            out.append((use or "그대로 복사해 쓰세요", body))
    return out

def _sections(block):
    """'## 소제목' 단위로 (소제목, 본문) 목록."""
    out = []
    for part in re.split(r"^##\s+", block or "", flags=re.M):
        part = part.strip()
        if not part:
            continue
        head, _, rest = part.partition("\n")
        out.append((head.strip(), rest.strip()))
    return out


def generate(idx, topic, cfg=None, recent=()):
    """한 편을 생성한다. 형식·분량이 모자라면 최대 3번까지 다시 쓴다."""
    cfg = cfg or load_config()
    slug, title, angle, tags = topic
    client = Anthropic(api_key=cfg["anthropic_api_key"])
    user = USER.format(n=idx, title=title, angle=angle,
                       today=f"{datetime.now():%Y-%m-%d}",
                       recent="\n".join(f"- {t}" for t in list(recent)[-12:]) or "(없음)")
    user += family_hint(slug)
    min_chars = int((cfg.get("geoai") or {}).get("min_chars", 1800))
    best = None
    for attempt in range(1, 4):
        msg = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=8000, system=SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        S = _split(msg.content[0].text.strip())
        secs = _sections(S.get("본문", ""))
        data = {
            "slug": slug, "title": post_title(topic), "index": SERIES_NO.get(slug, idx),
            "family": family_of(slug)[0], "family_total": len(family_of(slug)[1]),
            "summary": _lines(S.get("요약", ""))[:3],
            "intro": S.get("도입", ""), "sections": secs,
            "howto": _steps(S.get("따라하기", "")),
            "prompts": _prompts(S.get("프롬프트", "")),
            "practice": _lines(S.get("해보기", "")),
            "faq": S.get("FAQ", "") or S.get("자주묻는질문", ""),
            "outro": S.get("마무리", ""),
            "tags": [t.strip() for t in re.split(r"[,\n]", S.get("태그", "")) if t.strip()] or list(tags),
        }
        length = len(data["intro"]) + len(data["outro"]) + sum(
            len(h) + len(p) for h, p in secs)
        ok = bool(data["intro"] and data["outro"]) and len(secs) >= 3
        if ok and (best is None or length > best[1]):
            best = (data, length)
        if ok and length >= min_chars and len(secs) >= 4:
            log(f"본문 {length}자 / 소제목 {len(secs)}개 — 생성 완료")
            return data
        log(f"분량·형식 미달(시도 {attempt}/3: 본문 {length}자, 소제목 {len(secs)}개) → 재시도")
    if best is None:
        raise RuntimeError("시리즈 글 생성 형식 파싱 실패(3회).")
    log("3회 시도 후 기준 미달 → 그중 가장 긴 결과로 진행합니다.")
    return best[0]


def _shot_html(url, caption=""):
    """단계 밑에 붙는 실제 화면 캡처 한 장."""
    cap = ('<br><span style="color:#667;font-size:0.9em">%s</span>' % _esc(caption)
           if caption else "")
    return ('<div style="margin:8px 0 4px"><img src="%s" alt="%s" '
            'style="max-width:100%%;height:auto;border:1px solid #dfe3e8;'
            'border-radius:6px">%s</div>'
            % (_esc(url), _esc(caption or "화면 캡처"), cap))


def _howto_html(steps, image_url="", shots=None):
    """따라하기 — 그림(실제 캡처가 있으면 그것, 없으면 도식) + 번호 매긴 단계.

    shots: {"cover": url, "steps": {번호: (설명, url)}} — 사람이 찍어 둔 화면 캡처.
    표지 캡처가 있으면 도식 대신 그것을 쓴다(진짜 화면이 늘 더 낫다)."""
    if not steps:
        return ""
    shots = shots or {"cover": "", "steps": {}}
    head_img = shots.get("cover") or image_url
    drawn = not shots.get("cover") and bool(image_url)
    P = ['<h3>🖥️ 화면에서 따라하기</h3>']
    if head_img:
        P.append('<p style="text-align:center"><img src="%s" alt="따라하기 단계" '
                 'style="max-width:100%%;height:auto;border-radius:8px"></p>'
                 % _esc(head_img))
    P.append('<ol style="line-height:1.8">')
    for i, (name, desc) in enumerate(steps, start=1):
        cap, url = shots.get("steps", {}).get(i, ("", ""))
        P.append("<li><strong>%s</strong><br>%s%s</li>"
                 % (_esc(name), _esc(desc), _shot_html(url, cap) if url else ""))
    P.append("</ol>")
    note = "※ 프로그램 버전에 따라 메뉴 이름이 조금씩 다를 수 있습니다."
    if drawn:
        note += " 위 그림은 순서를 정리한 도식입니다."
    P.append('<p style="color:#667;font-size:0.92em">%s</p>' % note)
    return "\n".join(P)


def _prompts_html(prompts):
    """복사해 쓰는 프롬프트 상자. 대괄호 자리는 사용자가 채운다."""
    if not prompts:
        return ""
    P = ['<h3>✍️ 그대로 복사해 쓰는 프롬프트</h3>']
    for use, body in prompts:
        P.append('<p style="margin-bottom:6px"><strong>%s</strong></p>' % _esc(use))
        P.append('<pre style="background:#f6f8fa;border:1px solid #dfe3e8;border-left:4px solid'
                 ' #0e5a6b;padding:14px;border-radius:6px;white-space:pre-wrap;word-break:'
                 'break-word;font-size:0.95em">%s</pre>' % _esc(body))
    P.append('<p style="color:#667;font-size:0.92em">※ 대괄호 부분을 상황에 맞게 바꿔서 '
             '쓰세요. 받은 답은 그대로 쓰지 말고 사실 확인을 거치세요.</p>')
    return "\n".join(P)


def build_html(data, cfg=None, with_links=True, step_image="", shots=None):
    """with_links=False 면 채널 안내를 빼고 본문만 만든다(미디어 합성에서 마지막에 붙인다).

    step_image: 따라하기 단계를 그린 도식 PNG 의 CDN 주소(없으면 글자 단계만).
    shots: 사람이 찍어 둔 실제 화면 캡처(geoai_shots.upload_for) — 있으면 도식보다 앞선다."""
    cfg = cfg or load_config()
    P = []
    if data.get("summary"):
        P.append("<h3>📌 3줄 요약</h3><ul>"
                 + "".join(f"<li>{_esc(s)}</li>" for s in data["summary"]) + "</ul>")
    P.append(_prose_html(data.get("intro", "")))
    for head, body in data.get("sections", []):
        P.append(f"<h3>{_esc(head)}</h3>")
        P.append(_prose_html(body))
    P.append(_howto_html(data.get("howto", []), step_image, shots))
    P.append(_prompts_html(data.get("prompts", [])))
    if data.get("practice"):
        P.append("<h3>🧪 직접 해보기</h3><ul>"
                 + "".join(f"<li>{_esc(s)}</li>" for s in data["practice"]) + "</ul>")
    if data.get("faq"):
        P.append("<h3>❓ 자주 묻는 질문</h3>" + _prose_html(data["faq"]))
    if data.get("outro"):
        P.append(_prose_html(data["outro"]))
    P.append(f'<p><em>{data.get("family", "GeoAI 기초")} 시리즈 '
             f'{data.get("index", "")}편 · 전체 {data.get("family_total", len(TOPICS))}편</em></p>')
    if with_links:
        P.append(channel_links_html(cfg))
    return "\n".join(p for p in P if p)


def prepare(cfg=None, check_blog=True):
    """오늘 나갈 1편을 생성한다(발행하지 않음). → (idx, topic, data) / 없으면 (None, None, None)."""
    cfg = cfg or load_config()
    have = set()
    if check_blog:
        try:
            have = posted_titles(service(), blog_id(cfg))
        except Exception as e:
            log(f"GeoAI: 기존 글 목록 확인 실패({type(e).__name__}) — 로컬 상태로만 판단합니다")
    idx, topic = next_topic(have)
    if topic is None:
        log("GeoAI 시리즈: 남은 주제가 없습니다(TOPICS 에 주제를 더 넣어주세요).")
        return None, None, None
    log(f"GeoAI 시리즈 {idx}/{len(TOPICS)}편 생성: {topic[1]}")
    recent = [v.get("title", "") for v in state().get("posted", {}).values()]
    return idx, topic, generate(idx, topic, cfg, recent)


def mark_posted(topic, data, url):
    """발행 결과를 상태 파일에 남긴다(다음 실행이 같은 편을 다시 쓰지 않게)."""
    s = state()
    s.setdefault("posted", {})[topic[0]] = {
        "title": data["title"], "url": url, "date": f"{datetime.now():%Y-%m-%d}"}
    save_state(s)


def run(dry_run=False, cfg=None):
    """오늘 나갈 1편을 생성해 발행한다(미디어 없이). 보통은 geoai_daily.py 가 호출한다."""
    cfg = cfg or load_config()
    idx, topic, data = prepare(cfg, check_blog=not dry_run)
    if data is None:
        return {"status": "exhausted"}
    html = build_html(data, cfg)
    r = publish(data["title"], html, data["tags"] + list(topic[3]),
                dry_run=dry_run, cfg=cfg)
    if r.get("status") == "published":
        mark_posted(topic, data, r.get("url", ""))
    r["title"] = data["title"]
    r["kind"] = "series"
    return r


if __name__ == "__main__":
    if "--plan" in sys.argv:
        done = set(state().get("posted", {}))
        for i, t in enumerate(TOPICS, start=1):
            print(("[완료] " if t[0] in done else "[대기] ") + f"{i:2d}. {t[1]}")
        idx, topic = next_topic()
        print("\n다음 발행 예정:", post_title(topic) if topic else "없음")
        raise SystemExit(0)
    go = "--go" in sys.argv
    print(json.dumps(run(dry_run=not go), ensure_ascii=False, indent=2))
