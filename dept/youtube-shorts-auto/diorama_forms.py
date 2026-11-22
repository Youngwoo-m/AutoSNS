"""디오라마 형식 두 가지 — 장면형·소품형(2026-11-19 사용자 지정: "소품형과 장면형을 적절하게 선택해서 제작", "사실감 있게 제작").

장면형(scene): 사람의 행동·장소·지형·피해 범위·대피 동선을 보여 줄 때. 모형이 화면을 끝까지 채우고 받침대·작업대가 안 보이며,
    하늘·지평선과 자연광으로 실제 장소처럼 찍되, 사람은 자세와 행동이 읽힐 만큼 크게 둔다.
소품형(prop): 장비·도구·구호 물품·구조물 하나나 원리(단면)를 보여 줄 때. 작업대 위 작은 받침대에 놓인 실물 모형을
    매크로 렌즈로 크게 찍는다.
두 형식 모두 실제 재료·자연광·접지 그림자로 사실감 있게 만들되, 실제 현장 사진으로 오인되지 않게 모형임은 드러낸다
(장면형은 위아래 가장자리만 살짝 틸트시프트, 소품형은 받침대와 얕은 심도). 장난감·점토·만화·게임 CG 느낌은 피한다.

pick(text) 는 장면 설명(영어)에서 형식을 고른다. 확실하지 않으면 장면형(사람·장소가 보여야 이해되는 장면이 대부분이다).
"""
import re

COMMON_AVOID = ("No text, no letters, no numbers, no logos anywhere; every sign, screen and label is blank. "
                "Avoid: cartoon, clay or plastic toy look, video-game CGI, injured people, distressing scenes.")

SCENE = ("Style: photorealistic large-scale diorama, a highly detailed handcrafted scale model of a Korean scene that fills "
         "the entire frame edge to edge with no visible base, table or studio. Real materials: actual soil, gravel, moss, "
         "weathered paint, water resin, finely detailed trees, buildings and vehicles. Physically accurate natural daylight "
         "with open sky and horizon visible, realistic soft shadows and ambient occlusion. Figures are large enough that "
         "their posture and actions are clearly readable. Very subtle tilt-shift blur only at the top and bottom edges, so "
         "it looks like a real place yet still reads as a scale model and not a real photograph. Calm, orderly mood. ")

PROP = ("Style: photorealistic macro photograph of a real handcrafted miniature diorama on a small square base standing on "
        "a wooden workbench; one subject sits large in the center of the frame. Real materials: metal, painted resin, "
        "fabric, soil and moss with fine wear and texture. Soft natural window light, realistic contact shadows, macro "
        "lens with shallow depth of field. Clearly a physical scale model, calm and orderly mood. ")

FORMS = {"scene": SCENE, "prop": PROP}
LABEL = {"scene": "장면형", "prop": "소품형"}

_PROP_WORDS = re.compile(r"\b(close-?up|insert|single|kit|bag|device|instrument|equipment|tool|extinguisher|antenna|"
                         r"receiver|tripod|sensor|gauge|valve|helmet|harness|cross-?section|cutaway|model of|"
                         r"on a (?:small )?(?:base|table|desk|workbench))\b", re.I)
_SCENE_WORDS = re.compile(r"\b(people|person|residents|workers|crew|team|family|students|village|town|city|street|"
                          r"alley|road|neighborhood|mountain|hill|river|valley|coast|shelter|evacuat\w*|crowd|site|"
                          r"field|landscape|aerial|campus|apartment)\b", re.I)


def pick(text, form="auto"):
    """'scene'·'prop' 은 그대로, 'auto' 면 장면 설명으로 고른다."""
    if form in FORMS:
        return form
    t = text or ""
    return "prop" if _PROP_WORDS.search(t) and not _SCENE_WORDS.search(t) else "scene"


def style(form, aspect="vertical 9:16"):
    return FORMS[form] + f"{aspect} composition. " + COMMON_AVOID


# 재난 숏츠(dept/disaster-shorts) 영상·그림 스타일 문구 — write_script 가 script.json 에 넣고, image_scene·veo_scene 은
# 예전 미니어처 문구가 든 대본도 이 문구로 바꿔 쓴다(OLD_DISASTER_PREFIX 로 알아봄).
OLD_DISASTER_PREFIX = "Style: an isometric miniature diorama of a Korean scene"
DISASTER_SCENE = ("Style: photorealistic large-scale diorama, a highly detailed handcrafted scale model of a Korean scene that fills "
                "the entire frame edge to edge with no visible base, table or studio. Real materials: actual soil, gravel, moss, "
                "weathered paint, water resin, finely detailed trees, buildings and vehicles. Physically accurate natural daylight "
                "with open sky visible, realistic soft shadows, warm highlights and cool shadows. Figures are large enough that "
                "their posture and actions are clearly readable. Very subtle tilt-shift blur only at the top and bottom edges so it "
                "still reads as a scale model and not a real photograph, anamorphic lens feel, subtle film grain. All walls, signboards, "
                "banners, screens and vehicles are plain and unmarked; single continuous shot, no captions or on-screen graphics. "
                "Avoid: passing as real news footage of a real place, cartoon, clay or plastic toy look, video-game CGI, injured "
                "people, text, letters, numbers, logos.")
DISASTER_PROP = ("Style: photorealistic macro footage of a real handcrafted miniature diorama on a small square base standing on "
                     "a wooden workbench; one subject sits large in the center of the frame. Real materials: metal, painted resin, "
                     "fabric, soil and moss with fine wear and texture. Soft natural window light, realistic contact shadows, macro "
                     "lens with shallow depth of field, slow steady camera. Clearly a physical scale model, calm mood, single continuous "
                     "shot. Every label, screen and sign is blank. Avoid: cartoon, clay or plastic toy look, video-game CGI, text, "
                     "letters, numbers, logos.")
