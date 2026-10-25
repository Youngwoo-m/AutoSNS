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
import re

DEFAULT_BASE = "https://factchat-cloud.mindlogic.ai/v1/gateway/claude"
# Anthropic 키(대비책)로 나갈 때: 옛 모델 이름을 같은 값 싼 새 모델로. Sonnet 4.6($3/$15) → Sonnet 5($2/$10), 33% 절약(2026-10-19 비용 검토).
# 5.5 가 아니라 5 인 까닭: Sonnet 5.5 는 thinking disabled 를 400 으로 거절해 지금 코드(사고 끔)를 그대로 못 쓴다.
DIRECT_MAP = {"claude-sonnet-4-6": "claude-sonnet-5", "claude-sonnet-4-5": "claude-sonnet-5"}
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
        dkw = dict(kw)
        dkw["model"] = DIRECT_MAP.get(kw.get("model"), kw.get("model"))
        if dkw["model"] in DIRECT_MAP.values():
            # sonnet-5 는 사고를 켜 두면 max_tokens 를 사고에 다 써 글 블록이 비는 일이 있었다(게이트웨이 때와 같다) — 끈다
            dkw.setdefault("thinking", {"type": "disabled"})
        _log(f"LLM: Anthropic 키({dkw['model']})")
        return _text_first(self._direct.messages.create(**dkw))


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
    """이 창구가 받을 수 없는 요청 — 실패로 세지 않고 다음 창구로 넘긴다."""


class _Block:
    """Anthropic 응답 블록 흉내(text·tool_use). 에이전트 루프가 model_dump() 로 대화에 다시 넣는다."""
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self, exclude_none=True):
        return {k: v for k, v in self.__dict__.items() if not (exclude_none and v is None)}


def _get(b, k, default=None):
    return b.get(k, default) if isinstance(b, dict) else getattr(b, k, default)


class _CliMessages:
    """claude CLI(`claude -p`, Max 구독)를 Anthropic messages.create 처럼 쓴다.
    - 글: 도구·훅·MCP·프로젝트 지시문(CLAUDE.md)을 끄고 빈 폴더에서 돌려 요청한 글만 받는다(한 번 5~30초).
    - 그림(image 블록): 작업 폴더에 파일로 저장하고 CLI 의 Read 도구로만 열게 한다.
    - 도구(tools): 도구 설명을 시스템 지시에 넣고 <tool_call>{json}</tool_call> 로 부르게 해 tool_use 블록으로 바꾼다.
      도구 결과(tool_result)는 다음 호출 때 대화 기록에 <tool_result> 로 넣는다(호출마다 전체 대화를 다시 보낸다)."""
    MODELS = (("opus", "opus"), ("haiku", "haiku"))
    CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)

    def __init__(self):
        import os
        self.work = os.path.expanduser("~/.cache/autosns-llm")
        os.makedirs(self.work, exist_ok=True)
        self.images = []

    def _image(self, b):
        import base64
        import hashlib
        import os
        src = _get(b, "source") or {}
        if _get(src, "type") != "base64":
            raise _Unsupported("주소로 준 그림")
        data = base64.b64decode(_get(src, "data"))
        ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif", "image/webp": ".webp"}.get(
            _get(src, "media_type"), ".png")
        path = os.path.join(self.work, "img_" + hashlib.sha1(data).hexdigest()[:16] + ext)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)
        self.images.append(path)
        return f"[그림 파일: {path} — Read 도구로 열어 본다]"

    def _render(self, content):
        """메시지 내용 → 글. 글·그림·tool_use·tool_result 블록을 모두 글로 바꾼다."""
        import json
        if isinstance(content, str):
            return content
        out = []
        for b in content or []:
            t = _get(b, "type")
            if t == "text":
                out.append(_get(b, "text") or "")
            elif t == "image":
                out.append(self._image(b))
            elif t == "tool_use":
                out.append("<tool_call>" + json.dumps({"name": _get(b, "name"), "input": _get(b, "input") or {}},
                                                      ensure_ascii=False) + "</tool_call>")
            elif t == "tool_result":
                c = _get(b, "content")
                body = c if isinstance(c, str) else self._render(c)
                err = " 오류" if _get(b, "is_error") else ""
                out.append(f"<tool_result{err}>\n{body}\n</tool_result>")
            elif t in ("thinking", "redacted_thinking"):
                continue
            else:
                raise _Unsupported(f"모르는 블록({t})")
        return "\n".join(out)

    def _tools_text(self, tools):
        import json
        lines = ["## 쓸 수 있는 도구",
                 "도구를 부르려면 답에 다음 형식의 줄을 쓴다(여러 개 가능). 형식 밖의 말은 짧게.",
                 '<tool_call>{"name": "도구이름", "input": {…입력…}}</tool_call>',
                 "도구를 부른 차례에는 결과를 지어내지 말고 거기서 답을 끝낸다. 결과는 다음 차례에 <tool_result> 로 온다.",
                 "아래 도구 말고 다른 도구(파일 읽기 등)는 없다고 여긴다.", ""]
        for t in tools:
            lines.append(f"- {t['name']}: {t.get('description', '')}\n  입력 스키마: "
                         + json.dumps(t.get("input_schema") or {}, ensure_ascii=False))
        return "\n".join(lines)

    def create(self, **kw):
        import json
        import os
        import subprocess
        import uuid
        self.images = []
        tools = kw.get("tools") or []
        system = self._render(kw.get("system") or "")
        if tools:
            system = (system + "\n\n" if system else "") + self._tools_text(tools)
        msgs = list(kw.get("messages") or [])
        prefill = ""
        if msgs and msgs[-1].get("role") == "assistant" and isinstance(msgs[-1].get("content"), str):
            prefill = msgs.pop()["content"]                     # 응답 앞부분을 정해 둔 요청
        turns = [(m.get("role"), self._render(m.get("content"))) for m in msgs]
        if len(turns) == 1 and not tools:
            prompt = turns[0][1]
        else:
            prompt = "\n\n".join(f"[{'사용자' if r == 'user' else '어시스턴트'}]\n{t}" for r, t in turns) + \
                     "\n\n위 대화에 이어 [어시스턴트]의 다음 차례만 써라([어시스턴트] 머리표는 빼고)."
        if prefill:
            prompt += f"\n\n답은 반드시 다음 글자로 시작한다(그대로 이어서 쓴다): {prefill}"
        name = str(kw.get("model") or "")
        model = next((a for k, a in self.MODELS if k in name), "sonnet")
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}   # 구독 로그인으로만
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + env.get("PATH", "/usr/bin:/bin")
        env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(int(kw.get("max_tokens") or 4000))
        allow = "Read" if self.images else ""
        # stream-json 으로 받아 모든 assistant 메시지의 글을 이어 붙인다. 긴 글은 한 응답이 두 메시지로 나뉘어 올 때가 있고
        # (문장 중간에서 끊겨 다음 메시지가 이어짐) json 출력의 result 는 마지막 메시지 글만 담는다 —
        # 2026-10-19 18:00 GeoAI 시리즈 글이 result 의 꼬리(약 290자)만 받아 '형식 파싱 실패'로 멈췄다.
        cmd = ["claude", "-p", "--model", model, "--tools", allow, "--setting-sources", "", "--strict-mcp-config",
               "--disable-slash-commands", "--no-session-persistence", "--output-format", "stream-json", "--verbose"]
        if allow:
            cmd += ["--allowedTools", allow]
        if system:
            cmd += ["--system-prompt", system]
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=self.work, env=env, timeout=900)
        d, pieces = None, []
        for line in p.stdout.splitlines():
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            if ev.get("type") == "assistant":
                pieces += [b.get("text", "") for b in (ev.get("message") or {}).get("content", []) if b.get("type") == "text"]
            elif ev.get("type") == "result":
                d = ev
        if d is None:
            raise RuntimeError(f"claude CLI 출력 없음(코드 {p.returncode}): {(p.stderr or p.stdout).strip()[:200]}")
        if d.get("is_error") or p.returncode != 0:
            raise RuntimeError(f"claude CLI 오류: {str(d.get('result') or d.get('subtype'))[:200]}")
        text = "".join(pieces) if pieces else (d.get("result") or "")
        if prefill and text.startswith(prefill):
            text = text[len(prefill):]
        blocks, stop = [], "end_turn"
        if tools:
            known = {t["name"] for t in tools}
            for m in self.CALL.finditer(text):
                try:
                    c = json.loads(m.group(1), strict=False)   # 문자열 안의 줄바꿈 글자도 받는다
                except ValueError:
                    continue
                if c.get("name") in known:
                    blocks.append(_Block(type="tool_use", id="toolu_cli_" + uuid.uuid4().hex[:20],
                                         name=c["name"], input=c.get("input") or {}))
            if blocks:
                stop = "tool_use"
                text = self.CALL.sub("", text).strip()
        if text or not blocks:
            blocks.insert(0, _Block(type="text", text=text))
        u = d.get("usage") or {}
        return _Block(content=blocks, stop_reason=stop, model=f"claude-cli:{model}", role="assistant",
                      usage=_Block(input_tokens=(u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0)
                                                 + u.get("cache_creation_input_tokens", 0)),
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
