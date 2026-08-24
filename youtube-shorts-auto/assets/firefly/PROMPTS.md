# Adobe Firefly 배경 이미지 프롬프트 — 틱톡 진로 시리즈 1편

## 공통 설정 (Firefly 화면에서)
- **종횡비(Aspect ratio):** `세로 9:16` (없으면 `세로 3:4` — 제가 9:16으로 자동 크롭)
- **콘텐츠 유형:** `사진(Photo)`  ← 실사 느낌. 일러스트를 원하면 `아트`
- **스타일 참조:** 없음(또는 시네마틱/드라마틱 라이트)
- **중요:** 프롬프트에 "no text, no letters, no words" 유지 → Firefly가 글자를 그려 넣지 않게
- **구도 팁:** 화면 **중앙은 비교적 단순/어둡게**(그 위에 자막이 올라감). 아래 프롬프트에 이미 반영됨.

## 저장 규칙
생성한 이미지를 아래 파일명으로 이 폴더(`assets/firefly/`)에 저장해 주세요.
이 이름으로 넣어두면 제가 자동으로 각 장면 배경에 매칭합니다.

| 파일명 | 장면 |
|--------|------|
| `01_hook.png` | 훅(표지) |
| `02_impact.png` | ① 재해영향평가 |
| `03_biz.png` | ② 기업 재난관리 |
| `04_geoai.png` | ③ GeoAI·공간정보 |
| `05_fire.png` | ④ 방재·소방직 |
| `06_safety.png` | ⑤ 산업안전 관리자 |
| `07_cta.png` | 팔로우(CTA) |

---

## 프롬프트 (영문 그대로 붙여넣기 — Firefly는 영문에서 품질이 좋습니다)

### 01_hook — 훅(표지)
```
Cinematic wide shot of an emergency operations center at night, glowing blue
monitors showing maps and weather radar, silhouettes of responders, dramatic
moody lighting, deep navy and cyan tones, dark uncluttered center for overlay,
9:16 vertical, no text, no letters, no words
```

### 02_impact — ① 재해영향평가
```
Aerial view of a river flooding near a construction development site, muddy water
rising toward buildings and roads, overcast dramatic sky, engineering survey mood,
desaturated blue-grey tones, dark calm center area, 9:16 vertical,
no text, no letters, no words
```

### 03_biz — ② 기업 재난관리
```
Modern corporate control room with a large data dashboard wall, business people
reviewing continuity plans, clean professional atmosphere, cool blue lighting,
sense of resilience and preparedness, dark uncluttered center, 9:16 vertical,
no text, no letters, no words
```

### 04_geoai — ③ GeoAI·공간정보
```
Futuristic 3D terrain map with glowing data overlays and contour lines, satellite
and drone perspective of a landscape, holographic GIS interface, deep blue and
teal glow, high-tech geospatial AI mood, dark center space, 9:16 vertical,
no text, no letters, no words
```

### 05_fire — ④ 방재·소방직 공무원
```
Firefighters and disaster response team in action at dusk, red and orange emergency
lights, smoke haze, heroic dramatic atmosphere, motion and urgency, dark cinematic
tone, uncluttered center, 9:16 vertical, no text, no letters, no words
```

### 06_safety — ⑤ 산업안전 관리자
```
Industrial safety manager wearing a hard hat and hi-vis vest inspecting a large
construction or plant site, blueprints and safety signage, professional confident
mood, cool daylight with strong shadows, calm dark center area, 9:16 vertical,
no text, no letters, no words
```

### 07_cta — 팔로우(CTA)
```
Hopeful university campus at golden hour, students walking together, bright warm
optimistic atmosphere, soft bokeh background, sense of future and opportunity,
gentle uncluttered center, 9:16 vertical, no text, no letters, no words
```

---

## 다 만든 뒤
이 7장을 `assets/firefly/`에 위 파일명으로 저장하고 "배경 넣어서 렌더해줘"라고 말씀해 주세요.
제가 진로 시리즈 1편 영상을 Firefly 배경으로 다시 렌더해 드립니다.
(일부만 만들어도 됩니다 — 없는 장면은 기존 흰 배경으로 자동 대체됩니다.)

---

# 추가분 — 7·8편 전용 배경 (관제센터 배경과 구분용)

> ⚠️ **이번엔 꼭 세로 9:16로!** (지난번 07_cta가 가로로 나왔어요)

| 파일명 | 장면 |
|--------|------|
| `08_mgr.png` | 7편 재난안전관리자 |
| `09_smart.png` | 8편 스마트 재난안전관리자 |

### 08_mgr — 7편 재난안전관리자 (밝은 주간 지휘·기획실)
```
A disaster safety manager leading a planning meeting in a bright modern emergency
management operations room, team reviewing city hazard maps and response manuals on
a large wall display, daytime professional government atmosphere, cool blue and teal
palette, sense of coordination and preparedness, simple uncluttered vertical center
for text, 9:16 vertical portrait, no text, no letters, no words
```

### 09_smart — 8편 스마트 재난안전관리자 (스마트시티 디지털트윈)
```
A futuristic smart city digital twin, glowing holographic 3D model of an urban
skyline with IoT sensor networks and connecting data lines, real-time monitoring
interface, deep blue and cyan neon glow with subtle purple accents, high-tech smart
disaster control atmosphere, dark simple vertical center for text overlay,
9:16 vertical portrait, no text, no letters, no words
```

이 2장을 `assets/firefly/`에 저장하고 "7·8편 전용 배경으로 재렌더"라고 하시면
제가 두 편을 새 배경으로 다시 렌더해 드립니다.
