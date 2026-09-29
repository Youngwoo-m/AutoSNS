"""Claude 호출 공용 창구 — 세명대 AI 게이트웨이를 먼저 쓰고, 안 되면 Anthropic 키로.

세명대 BAZE(Mindlogic) API Gateway 가 Anthropic Messages 형식을 그대로 받는다
(https://factchat-cloud.mindlogic.ai/v1/gateway/claude). 학교가 매달 크레딧을 지급해
개인 Anthropic 키 비용을 줄일 수 있다(2026-09-29 확인: 월 12,000).

게이트웨이가 실패하면(키 오류·크레딧 소진·서버 오류·모델 없음) 기존 Anthropic 키로 같은
요청을 다시 보낸다 — 발행이 멈추지 않게. 어느 쪽으로 나갔는지 로그에 남긴다.

설정(config.json):
  "llm_gateway": {"enabled": true, "api_key": "...",
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


class _Messages:
    def __init__(self, gw, direct, model_map):
        self._gw, self._direct, self._map = gw, direct, model_map

    def create(self, **kw):
        if self._gw is not None:
            gkw = dict(kw)
            gkw["model"] = self._map.get(kw.get("model"), kw.get("model"))
            try:
                r = self._gw.messages.create(**gkw)
                _log(f"LLM: 학교 게이트웨이({gkw['model']})")
                return r
            except Exception as e:
                if self._direct is None:
                    raise
                _log(f"LLM: 게이트웨이 실패 → Anthropic 키로 전환 ({type(e).__name__}: {str(e)[:120]})")
        if self._direct is None:
            raise RuntimeError("LLM 키가 없습니다(llm_gateway.api_key / anthropic_api_key).")
        return self._direct.messages.create(**kw)


class _Client:
    def __init__(self, gw, direct, model_map):
        self.messages = _Messages(gw, direct, model_map)


def client(cfg):
    from anthropic import Anthropic
    g = cfg.get("llm_gateway") or {}
    gw = None
    if g.get("enabled", True) and g.get("api_key"):
        gw = Anthropic(api_key=g["api_key"], base_url=g.get("base_url") or DEFAULT_BASE,
                       max_retries=1, timeout=180)
    direct = Anthropic(api_key=cfg["anthropic_api_key"]) if cfg.get("anthropic_api_key") else None
    return _Client(gw, direct, {**DEFAULT_MAP, **(g.get("model_map") or {})})
