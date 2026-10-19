"""Claude 호출 공용 창구 — 글은 Max 구독(claude CLI)으로, 안 되면 Anthropic 키로.

2026-10-19 사용자 지정: 세명대 AI 게이트웨이 크레딧은 영상 제작(영상 클립·숏츠 디오라마 그림)에만 쓴다.
그래서 글 작성(블로그·대본·카드 문구 등)은 claude CLI(`claude -p`, Max 구독 — 호출당 추가 비용 없음)로 보내고,
CLI 가 실패하면(사용 한도·로그인·시간 초과) Anthropic 키로 같은 요청을 다시 보낸다. 어느 쪽으로 나갔는지 로그에 남긴다.
그림이 든 요청·도구(tools) 요청은 CLI 가 못 받으므로 바로 Anthropic 키로 간다.

게이트웨이로 글을 쓰던 예전 방식은 llm_gateway.text_enabled = true 일 때만 쓴다(그때는 게이트웨이 → CLI → 키).

설정(config.json):
  "llm_gateway": {"enabled": true, "api_key": "...", "extra_keys": ["..."], "text_enabled": false, ...}
  "llm_cli": {"enabled": true}        # 끄면 CLI 를 건너뛴다
  "anthropic_api_key": "..."          # 대비책

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
        # 앞에서부터 차례로 쓴다(CLI·게이트웨이 키). 실패하면 다음, 모두 안 되면 Anthropic 키.
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
                _log(f"LLM: {label}({gkw['model']})")
                return r
            except _Unsupported:
                continue
            except Exception as e:
                last = n == len(self._gws) - 1
                if last and self._direct is None:
                    raise
                nxt = "Anthropic 키" if last else self._gws[n + 1][0]
                _log(f"LLM: {label} 실패 → {nxt}로 전환 ({type(e).__name__}: {str(e)[:120]})")
        if self._direct is None:
            raise RuntimeError("쓸 수 있는 LLM 이 없습니다(claude CLI / anthropic_api_key).")
        _log(f"LLM: Anthropic 키({kw.get('model')})")
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


class _Unsupported(Exception):
    """이 창구가 받을 수 없는 요청(그림·도구) — 실패로 세지 않고 다음 창구로 넘긴다."""


def _text_of(content):
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        t = b.get("type") if isinstance(b, dict) else getattr(b, "type", "")
        if t != "text":
            raise _Unsupported(f"글이 아닌 블록({t})")
        out.append(b["text"] if isinstance(b, dict) else b.text)
    return "\n".join(out)


class _CliMessages:
    """claude CLI(`claude -p`, Max 구독)를 Anthropic messages.create 처럼 쓴다. 글만 주고받는다.
    도구·훅·MCP·프로젝트 지시문(CLAUDE.md)을 끄고 빈 폴더에서 돌려, 요청한 글만 돌려받는다(호출 한 번 5~30초)."""
    MODELS = (("opus", "opus"), ("haiku", "haiku"))

    def create(self, **kw):
        import json
        import os
        import subprocess
        from types import SimpleNamespace
        if kw.get("tools"):
            raise _Unsupported("도구 요청")
        system = _text_of(kw.get("system") or "")
        msgs = list(kw.get("messages") or [])
        prefill = ""
        if msgs and msgs[-1].get("role") == "assistant":       # 응답 앞부분을 정해 둔 요청
            prefill = _text_of(msgs.pop()["content"])
        turns = [(m.get("role"), _text_of(m.get("content"))) for m in msgs]
        if len(turns) == 1:
            prompt = turns[0][1]
        else:
            prompt = "\n\n".join(f"[{'사용자' if r == 'user' else '어시스턴트'}]\n{t}" for r, t in turns) + \
                     "\n\n위 대화에 이어 [어시스턴트]의 다음 답만 써라."
        if prefill:
            prompt += f"\n\n답은 반드시 다음 글자로 시작한다(그대로 이어서 쓴다): {prefill}"
        name = str(kw.get("model") or "")
        model = next((a for k, a in self.MODELS if k in name), "sonnet")
        work = os.path.expanduser("~/.cache/autosns-llm")
        os.makedirs(work, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # 구독 로그인으로만
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(int(kw.get("max_tokens") or 4000))
        cmd = ["claude", "-p", "--model", model, "--tools", "", "--setting-sources", "", "--strict-mcp-config",
               "--disable-slash-commands", "--no-session-persistence", "--output-format", "json"]
        if system:
            cmd += ["--system-prompt", system]
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=work, env=env, timeout=600)
        try:
            d = json.loads(p.stdout)
        except ValueError:
            raise RuntimeError(f"claude CLI 출력 없음(코드 {p.returncode}): {(p.stderr or p.stdout).strip()[:200]}")
        if d.get("is_error") or p.returncode != 0:
            raise RuntimeError(f"claude CLI 오류: {str(d.get('result') or d.get('subtype'))[:200]}")
        text = d.get("result") or ""
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]
        u = d.get("usage") or {}
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               model=f"claude-cli:{model}", role="assistant",
                               usage=SimpleNamespace(input_tokens=u.get("input_tokens", 0),
                                                     output_tokens=u.get("output_tokens", 0)))


class _Cli:
    def __init__(self):
        self.messages = _CliMessages()


def cli_available(cfg):
    import shutil
    return (cfg.get("llm_cli") or {}).get("enabled", True) and bool(
        shutil.which("claude") or shutil.which("claude", path="/usr/local/bin:/opt/homebrew/bin"))


def client(cfg):
    from anthropic import Anthropic
    g = cfg.get("llm_gateway") or {}
    base = g.get("base_url") or DEFAULT_BASE
    gws = []
    if g.get("text_enabled"):           # 예전 방식(게이트웨이로 글 쓰기)을 일부러 켠 경우만
        gws += [(f"학교 게이트웨이{label}", Anthropic(api_key=k, base_url=base, max_retries=1, timeout=180))
                for label, k in usable_gateway_keys(cfg)]
    if cli_available(cfg):
        gws.append(("Max 구독(claude CLI)", _Cli()))
    direct = Anthropic(api_key=cfg["anthropic_api_key"]) if cfg.get("anthropic_api_key") else None
    return _Client(gws, direct, {**DEFAULT_MAP, **(g.get("model_map") or {})})
