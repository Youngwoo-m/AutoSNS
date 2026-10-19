"""Claude 호출 공용 창구 — 세명대 AI 게이트웨이를 먼저 쓰고, 안 되면 Anthropic 키로.

세명대 BAZE(Mindlogic) API Gateway 가 Anthropic Messages 형식을 그대로 받는다
(https://factchat-cloud.mindlogic.ai/v1/gateway/claude). 학교가 매달 크레딧을 지급해
개인 Anthropic 키 비용을 줄일 수 있다(2026-09-29 확인: 월 12,000).

게이트웨이가 실패하면(키 오류·크레딧 소진·서버 오류·모델 없음) 기존 Anthropic 키로 같은
요청을 다시 보낸다 — 발행이 멈추지 않게. 어느 쪽으로 나갔는지 로그에 남긴다.

설정(config.json):
  "llm_gateway": {"enabled": true, "api_key": "...", "extra_keys": ["..."],   # 추가 계정(차례로)
                  "base_url": "https://factchat-cloud.mindlogic.ai/v1/gateway/claude",
                  "model_map": {"claude-sonnet-4-6": "claude-sonnet-5"}}
  "anthropic_api_key": "..."      # 대비책

사용: from shared.llm import client;  client(cfg).messages.create(model=..., ...)
      — Anthropic(api_key=...) 자리에 그대로 바꿔 끼우면 된다.
"""
DEFAULT_BASE = "https://factchat-cloud.mindlogic.ai/v1/gateway/claude"
# 게이트웨이 목록에 없는 모델은 가까운 모델로(2026-09-29 목록 기준)
DEFAULT_MAP = {"claude-sonnet-4-6": "claude-sonnet-5", "claude-sonnet-4-5": "claude-sonnet-5",
               "claude-opus-4-6": "claude-opus-5"}


def _log(msg):
    try:
        from common import log
        log(msg)
    except Exception:
        print(msg)


def _text_first(r):
    """응답에서 사고(thinking) 블록을 뺀다. 호출하는 쪽이 모두 content[0].text 를 읽는데,
    게이트웨이의 Sonnet 5 는 어려운 요청에 사고 블록을 먼저 붙여 보낸다
    (2026-09-29 채용공고 선별에서 AttributeError: 'ThinkingBlock' … 'text')."""
    try:
        blocks = [b for b in r.content if getattr(b, "type", "") not in ("thinking", "redacted_thinking")]
        if blocks and blocks is not r.content:
            r.content = blocks
    except Exception:
        pass
    return r


class _Messages:
    def __init__(self, gws, direct, model_map):
        self._gws, self._direct, self._map = gws, direct, model_map

    def create(self, **kw):
        # 게이트웨이 키를 순서대로 쓴다(주 계정 → 추가 계정). 한 계정의 월 크레딧이 떨어지거나
        # 오류가 나면 다음 키, 모두 안 되면 Anthropic 키(2026-10-01 추가 키 연결).
        for n, (label, gw) in enumerate(self._gws):
            gkw = dict(kw)
            gkw["model"] = self._map.get(kw.get("model"), kw.get("model"))
            # 사고(thinking)를 끈다 — 우리 프롬프트는 모두 사고 없이 쓰도록 짜여 있고, 게이트웨이
            # 쪽은 어려운 요청에 사고를 붙이다가 max_tokens 를 다 써 글 블록 없이 끝난 적이 있다
            # (2026-10-01 GeoAI 영상 대본: 사고 블록만 와서 _text_first 로도 못 살렸다).
            gkw.setdefault("thinking", {"type": "disabled"})
            try:
                r = _text_first(gw.messages.create(**gkw))
                if not any(getattr(b, "type", "") == "text" for b in r.content):
                    raise RuntimeError(f"글 블록 없는 응답(stop={getattr(r, 'stop_reason', '')})")
                _log(f"LLM: 학교 게이트웨이{label}({gkw['model']})")
                return r
            except Exception as e:
                last = n == len(self._gws) - 1
                if last and self._direct is None:
                    raise
                nxt = "Anthropic 키" if last else "다음 게이트웨이 키"
                _log(f"LLM: 게이트웨이{label} 실패 → {nxt}로 전환 ({type(e).__name__}: {str(e)[:120]})")
        if self._direct is None:
            raise RuntimeError("LLM 키가 없습니다(llm_gateway.api_key / extra_keys / anthropic_api_key).")
        return self._direct.messages.create(**kw)


class _Client:
    def __init__(self, gws, direct, model_map):
        self.messages = _Messages(gws, direct, model_map)


def gateway_keys(cfg):
    """[주 키, 추가 키…] — 중복·빈 값 제외."""
    g = cfg.get("llm_gateway") or {}
    if not g.get("enabled", True):
        return []
    keys = [g.get("api_key")] + list(g.get("extra_keys") or [])
    return list(dict.fromkeys(k for k in keys if k))


# 키별 남은 '월 할당' 크레딧(10분 기억). 구매 크레딧은 쓰지 않는 것이 원칙이라, 월 할당이 바닥난 키는
# 건너뛴다 — 안 그러면 게이트웨이가 구매 크레딧부터 깎는다(2026-10 주 키 구매분 5,500 이 다 쓰였다).
_CREDITS = {}
CREDITS_URL = "https://factchat-cloud.mindlogic.ai/v1/gateway/credits/"


def monthly_left(key, ttl=600):
    """그 키의 남은 월 할당. 확인하지 못하면 None(그때는 쓸 수 있다고 본다)."""
    import json
    import time
    import urllib.request
    hit = _CREDITS.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    try:
        req = urllib.request.Request(CREDITS_URL, headers={"Authorization": f"Bearer {key}", "x-api-key": key,
                                                           "User-Agent": "smuds-autosns/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            left = float(json.load(r)["monthly_allocated"]["remaining"])
    except Exception:
        left = None
    _CREDITS[key] = (time.time(), left)
    return left


def usable_gateway_keys(cfg):
    """[(이름표, 키)] — 월 할당이 llm_gateway.monthly_reserve(기본 500) 아래로 떨어진 키는 뺀다.
    이름표는 설정 순서 그대로(주 키 '', 추가 키 '[추가N]')라 로그로 어느 계정인지 알 수 있다.
    모두 빠지면 빈 목록 — 부르는 쪽이 Anthropic 키로 넘어간다."""
    g = cfg.get("llm_gateway") or {}
    reserve = float(g.get("monthly_reserve", 500))
    out, skipped = [], []
    for i, k in enumerate(gateway_keys(cfg)):
        label = "" if i == 0 else f"[추가{i}]"
        left = monthly_left(k)
        if left is not None and left < reserve:
            skipped.append(f"게이트웨이{label} 월 할당 {left:.0f}")
            continue
        out.append((label, k))
    if skipped:
        _log(f"LLM: 월 할당이 {reserve:.0f} 아래라 건너뜀(구매 크레딧 안 씀) — {', '.join(skipped)}")
    return out


def client(cfg):
    from anthropic import Anthropic
    g = cfg.get("llm_gateway") or {}
    base = g.get("base_url") or DEFAULT_BASE
    gws = [(label, Anthropic(api_key=k, base_url=base, max_retries=1, timeout=180))
           for label, k in usable_gateway_keys(cfg)]
    direct = Anthropic(api_key=cfg["anthropic_api_key"]) if cfg.get("anthropic_api_key") else None
    return _Client(gws, direct, {**DEFAULT_MAP, **(g.get("model_map") or {})})
