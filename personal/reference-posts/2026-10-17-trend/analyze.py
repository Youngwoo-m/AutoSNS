from pathlib import Path
import json,re,csv,collections
P=Path(__file__).resolve().parent;Q=json.loads((P/'questions.json').read_text())
THEMES=[
('측지학·좌표계','지오이드·높이기준','지오이드|정표고|타원체고|수직위치기준|기본수준면|해안선의높이기준'),
('측지학·좌표계','좌표계·지구형상·지도투영','좌표계|기준타원체|지구타원체|지구의형상|지도투영|자오선수차|위도의종류'),
('측지학·좌표계','국가기준점·우주측지','기준점|VLBI|SLR|위성궤도력|안테나고'),
('GNSS','GNSS·RTK·보정정보','GNSS|RTK|위성측위|VRS|FKP|DOP|PPP|OSR|SSR|위성항법|의사위성|RINEX'),
('오차론·망조정','오차·정확도·조정','오차|정확도|정밀도(?!로)|최소제곱|조정|정규분포|칼만'),
('지상측량','노선·곡선측량','노선|클로소이드|완화곡선|캔트|확폭|유토곡선'),
('지상측량','수준측량','수준측량|교호수준'),
('지상측량','지하공간·매설물·탐사','지하공간|지하시설|지하터널|지하차도|하저터널|매설|GPR|지표투과'),
('지상측량','수로·수심·해양측량','수로|수심|음향측심|해저|해양|조석|소나|해안선|영해기점'),
('사진측량·UAV','드론·UAV·무인비행장치','드론|UAV|무인비행장치'),
('사진측량·UAV','표정·항공삼각·기준점·검정','표정|항공삼각|공선조건|교회법|카메라검정|카메라의검정|카메라의검정장|항공사진측량용카메라|지상기준점'),
('사진측량·UAV','정사영상·편위수정·기복변위','정사영상|편위수정|기복변위'),
('LiDAR·원격탐사','LiDAR·레이저·점군','LiDAR|라이다|레이저|점군'),
('LiDAR·원격탐사','SAR·레이더·InSAR','(?<![A-Z])SAR(?![A-Z])|InSAR|레이더|Radar'),
('LiDAR·원격탐사','영상해상도·분광·영상처리','해상도|분광|식생|NDVI|영상처리|영상분류|재배열|Resampling|공간필터링|히스토그램|변화탐지|변화를탐지|변화정보|SIFT|SfM|영상정합'),
('GIS·공간정보','DEM·DSM·지형모델','DEM|DSM|수치표고|수치표면|등고선|지성선'),
('GIS·공간정보','디지털트윈·BIM','디지털트윈|BIM|DTS'),
('GIS·공간정보','실내공간·LoD·SLAM','실내공간|LOD|SLAM'),
('GIS·공간정보','정밀도로지도·MMS','정밀도로지도|MMS'),
('GIS·공간정보','공간정보 품질·표준·구조','품질|위상|메타데이터|Metadata|GML|DBMS|구조화편집|주소참조'),
('GIS·공간정보','AI·온톨로지','GeoAI|인공지능|딥러닝|온톨로지|Ontology'),
('관련 제도·실무','법·정책·기본계획·안전','법률|법령|기본법|기본계획|기본전략|안전관리|안전대책|안전운항|국외반출|중대재해'),
('관련 제도·실무','재난·재해·긴급정보','재난|재해|침수|홍수|긴급공간정보|땅꺼짐'),
]
T=[]
for field,name,rule in THEMES:
 hits=[q for q in Q if re.search(rule,re.sub(r'\s+','',q['question']),re.I)]
 T.append(dict(field=field,theme=name,rule=rule,count=len(hits),round_count=len({q['round'] for q in hits}),by_year={str(y):sum(q['year']==y for q in hits) for y in range(2022,2027)},ids=[q['id'] for q in hits]))
requests=[('비교·차이·장단점','비교|차이|장.?단점'),('작업과정·방법·절차','방법|절차|과정|작업순서|작업공정'),('활용·적용','활용|적용'),('오차·정확도·정밀도·품질','오차|정확도|정밀도(?!로)|품질'),('개선·발전·대응·관리','개선|발전|대책|대응|관리|갱신')]
E=[q for q in Q if q['period']>1];R=[]
for name,rule in requests:
 hits=[q for q in E if re.search(rule,re.sub(r'\s+','',q['question']))];R.append(dict(type=name,count=len(hits),denominator=180,ids=[q['id'] for q in hits]))
A=dict(scope='2022~2026년 시행, 10회차 310문항',checked_at='2026-10-17',method='공식 PDF 텍스트의 공백을 제거하여 공개된 정규식으로 검색. 그룹 내 문항별 1회, 그룹 간 중복 허용. 학습 분야 배타분류 또는 공식 배점 비중이 아님. 문항은 1교시13개와 2~4교시각6개, 소문항은 분리하지 않음.',total=len(Q),short=130,essay=180,themes=T,answer_requests=R)
(P/'analysis.json').write_text(json.dumps(A,ensure_ascii=False,indent=2))
with (P/'topic-evidence.csv').open('w',encoding='utf-8-sig',newline='') as f:
 w=csv.writer(f);w.writerow(['학습분야','주제그룹','문항수','출제회차수','2022','2023','2024','2025','2026','집계규칙','문항ID'])
 for t in T:w.writerow([t['field'],t['theme'],t['count'],t['round_count'],*t['by_year'].values(),t['rule'],';'.join(t['ids'])])
print('\n'.join(f"{t['field']} | {t['theme']}: {t['count']}문항/{t['round_count']}회차, {list(t['by_year'].values())}" for t in T));print(R)
