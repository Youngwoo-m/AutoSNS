# 베오(Veo) B롤 프롬프트 — 재난안전 숏폼용

우리 숏폼은 한 편이 **5장면, 장면당 7초 안팎**이고, 화면 위쪽 40%에 소제목과
자막이 얹힌다. 그래서 B롤은 아래 조건을 항상 지켜야 쓸 수 있다.

## 공통 규칙 (모든 프롬프트 끝에 붙인다)

```
Vertical 9:16 aspect ratio. 8 seconds. Flat vector illustration style,
clean editorial infographic look, NOT photorealistic. Muted palette:
deep navy #334A8E, slate #272C3C, warm amber #FFA500, off-white.
Slow steady camera, minimal motion, no camera shake. Upper 40% of the
frame kept visually simple and uncluttered for text overlay. No text,
no letters, no numbers, no logos, no watermarks anywhere in the image.
No people's faces in close-up. No audio, no speech, no music.
```

**왜 이 조건인가**
- `9:16 / 8초` — 숏폼 한 장면 길이와 같다.
- `일러스트·도해풍, NOT photorealistic` — 실제 재난 영상으로 오해받지 않게. 우리는
  뉴스 브리핑 옆에 이 화면을 쓰므로, 실사처럼 보이면 가짜 현장 영상이 된다.
- `상단 40% 비워두기` — render_frames 가 그 자리에 소제목·자막을 얹는다.
- `텍스트·로고 금지` — 생성 모델이 만드는 글자는 거의 항상 깨진 한글/영문이다.
- `얼굴 클로즈업 금지` — 특정 인물처럼 보이는 얼굴을 피한다.
- `무음` — 내레이션은 TTS 로 따로 입힌다.

---

## 1. 화재 계열

**주택·아파트 화재 예방**
```
A cutaway illustration of a quiet apartment interior at night, one
electrical outlet with an overloaded power strip glowing faintly amber,
thin wisps of smoke rising slowly. Calm, instructional mood, not alarming.
```

**전통시장 화재 점검**
```
An overhead isometric illustration of a traditional Korean market alley,
fabric awnings and stalls, a fire extinguisher and a hydrant highlighted
in amber while everything else stays muted navy. Gentle top-down drift.
```

**산불 감시**
```
A wide illustrated mountain ridge in autumn, dry brown slopes, a thin
line of amber smoke on a distant peak, a watchtower silhouette in the
foreground. Slow push-in. Calm documentary tone.
```

**소화기 사용**
```
An illustrated close shot of hands (no face) lifting a red fire
extinguisher, pulling the safety pin, hose aimed low. Simple flat shapes,
step-by-step instructional feel. Neutral background.
```

## 2. 침수·호우 계열

**집중호우 도시 침수**
```
An illustrated city street in heavy rain seen from a raised angle, water
rising over a curb, a storm drain swirling, amber streetlights reflecting
on the surface. Steady rain, no people. Slow lateral drift.
```

**지하주차장·반지하 침수 위험**
```
A cross-section illustration of a building showing a basement parking
ramp with water beginning to flow down it, amber warning marking on the
ramp edge. Diagrammatic, calm explanatory style.
```

**차량 침수 대처**
```
An illustrated side view of a sedan stopped in shallow floodwater on a
road, water at wheel height, hazard lights glowing amber. Empty car
interior. Instructional, non-dramatic.
```

## 3. 지진·산사태 계열

**지진 행동요령**
```
An illustrated cutaway of a plain room, a sturdy table in the centre, a
pendant lamp swaying slightly, thin crack lines spreading across one wall.
Static camera, subtle shaking of loose objects only.
```

**산사태 전조**
```
An illustrated steep hillside after rain, soil darkened, a small slump
of earth and a tilted utility pole, thin water seeping from the slope.
Wide shot, slow push-in. Muted earth tones with amber warning accent.
```

## 4. 계절 재난

**폭염**
```
An illustrated empty city crosswalk under a high summer sun, heat
shimmer rising from asphalt, a shaded bus-stop canopy in amber. Slow
heat-haze motion. No people.
```

**대설·한파**
```
An illustrated road in falling snow, tyre tracks, a snow-covered guard
rail and a salt-spreading truck outline in the distance. Gentle snowfall,
static camera.
```

**태풍·강풍**
```
An illustrated coastal town street under strong wind, bending street
trees, a loose sign swinging, taped windows on a shopfront. Wide shot,
steady camera, wind motion only.
```

## 5. 생활안전

**승강기 안전**
```
An illustrated elevator hall, doors half open, an amber warning triangle
on the floor beside the gap. Clean diagrammatic style, static camera.
```

**어린이 놀이터 안전**
```
An illustrated empty playground at golden hour, slide and climbing frame,
soft rubber safety flooring shown in a different tone. Slow orbit.
No children visible.
```

**심폐소생술**
```
An illustrated top-down view of hands (no face) performing chest
compressions on a CPR training mannequin on a floor mat, rhythmic
vertical motion. Clean medical-instruction style.
```

## 6. GeoAI·드론 계열 (토요일 GeoAI 판)

**위성 재난 관측**
```
An illustrated view of Earth's surface from orbit, a satellite outline
in the foreground, a river basin below with one area highlighted in
amber as if flagged by analysis. Slow orbital drift.
```

**드론 현장 조사**
```
An illustrated quadcopter drone flying over a flooded farmland grid,
camera gimbal visible, thin scan lines sweeping the ground below.
Side-follow shot, steady.
```

**디지털 트윈 관제센터**
```
An illustrated control room with a large wall display showing an abstract
3D city model in navy and amber wireframe, empty operator desks in
silhouette. Slow push-in. No readable text on the screens.
```

**분광 지수 분석 (NDVI 등)**
```
An illustrated split view of the same forest area, one side natural
colour, the other side an abstract false-colour index map in amber and
navy gradients. Slow horizontal wipe between them.
```

## 7. 마무리 장면 (5번째 장면 / CTA 배경)

```
An illustrated wide shot of a calm city skyline at dawn in deep navy,
soft amber light on the horizon, a single thin amber line running along
the bottom third. Very slow push-in. Peaceful, reassuring tone.
```

---

## 쓰는 법

1. 위 장면 프롬프트 + **공통 규칙**을 이어 붙여 베오에 넣는다.
2. 받은 mp4 를 `posts/broll/` 에 두고 `render_frames.py` 배경으로 쓴다.
3. 8초보다 장면이 길면 마지막 프레임을 정지로 늘리거나 같은 프롬프트로 한 편 더 만든다.

## 꼭 지킬 것

- **뉴스 브리핑 편에 쓸 때는 특히 주의한다.** 실제 사건을 다루는 글·영상에 생성
  영상을 붙이면, 그 장면이 해당 사건의 실제 모습으로 읽힐 수 있다. 일러스트풍을
  쓰는 이유가 이것이다. 실사풍으로 바꾸지 않는다.
- **실존 지명·기관·인물을 프롬프트에 넣지 않는다.** "제천 전통시장" 대신
  "a traditional Korean market" 처럼 일반 명사로 쓴다.
- **플랫폼의 AI 생성 표시를 켠다.** 틱톡은 업로드 화면에 AI 생성 콘텐츠 토글이
  있고, 유튜브는 '변형된 콘텐츠' 공개 항목이 있다. 일러스트풍이라도 켜 두는 편이
  안전하다.
- 생성된 화면에 글자가 섞여 나오면 버린다. 한글이 깨져 나오는 경우가 많다.
