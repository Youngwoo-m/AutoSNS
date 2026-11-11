"""TTS 에 넘기기 전 읽는 법 고치기(2026-11-10 사용자 지정: 119 는 '백십구'가 아니라 '일일구').

edge-tts 등은 숫자 '119' 를 '백십구'로 읽는다. 전화번호처럼 한 자리씩 읽어야 하는 번호를
합성 직전에 한글 읽기로 바꾸고, 단어 경계(자막용)는 다시 화면 표기로 되돌린다.

    from shared.tts_read import spoken, shown
    audio_text = spoken("불이 나면 119에 신고하세요")   # → "불이 나면 일일구에 신고하세요"
    word = shown("일일구에")                              # → "119에" (자막은 숫자로)
"""
import re

# 화면 표기 → 읽는 법. 앞뒤가 숫자인 경우(1190, 2119 등)는 건드리지 않는다.
READINGS = {
    "119": "일일구",
    "112": "일일이",
}

_PAT = re.compile(r"(?<!\d)(" + "|".join(map(re.escape, READINGS)) + r")(?!\d)")
_BACK = {v: k for k, v in READINGS.items()}
_BACK_PAT = re.compile("|".join(map(re.escape, _BACK)))


def spoken(text):
    """TTS 에 넘길 글: 119·112 같은 번호를 한 자리씩 읽는 한글로."""
    return _PAT.sub(lambda m: READINGS[m.group(1)], text or "")


def shown(text):
    """TTS 단어 경계 글자를 화면 표기로 되돌린다(자막이 '일일구'로 나오지 않게)."""
    return _BACK_PAT.sub(lambda m: _BACK[m.group(0)], text or "")
