"""한 편을 조립한다: 인트로(띠 화면) + 본문(3D 영상·내 목소리·자막·라벨) + 아웃트로(띠 화면).

  .venv/bin/python assemble.py 2026-10-06_산불     (AutoSNS 의 .venv 로 실행 — 띠 화면에 크롬 필요)
결과: <편>/final.mp4 (1080x1920, 30fps, -14 LUFS)
"""
import json, os, re, subprocess, sys
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
AUTOSNS = "/Volumes/USB256/devAPP/AutoSNS/channels/youtube-shorts-auto"
sys.path.insert(0, AUTOSNS)
FONT_DIR = "/Volumes/USB256/devAPP/AutoSNS/assets/FONTS"
BOLD = os.path.join(FONT_DIR, "Pretendard-Bold.otf")
MED = os.path.join(FONT_DIR, "Pretendard-Bold.otf")
COMMON = os.path.join(CFG["root"], "common")
W, H, FPS = 1080, 1920, 30
SERIES = "재난 유형별 피해 양상과 대응 방안"


def run(cmd):
    subprocess.run(cmd, check=True)


def ff(*a):
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *a])


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                 "csv=p=0", p], capture_output=True, text=True).stdout.strip())


# 이모지(❌·⭕ 등)는 지우지 않고 애플 컬러 이모지로 그린다 — 지우면 '불 피우기 ❌'가
# '불 피우기'로 뜻이 뒤집힌다(2026-10-03 산불편에서 발견).
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"
_EMO = re.compile("[\U0001F000-\U0001FFFF☀-➿⬀-⯿]️?")


def clean(t):
    return re.sub(r"\s{2,}", " ", t).strip()


def _runs(t):
    """글자와 이모지를 나눈다 → [(is_emoji, text)]."""
    out, i = [], 0
    for m in _EMO.finditer(t):
        if m.start() > i:
            out.append((False, t[i:m.start()]))
        out.append((True, m.group(0))); i = m.end()
    if i < len(t):
        out.append((False, t[i:]))
    return out


def _emoji_img(ch, size):
    f = ImageFont.truetype(EMOJI_FONT, 160)
    im = Image.new("RGBA", (220, 220), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((10, 10), ch, font=f, embedded_color=True)
    im = im.crop(im.getbbox() or (0, 0, 160, 160))
    return im.resize((size, size), Image.LANCZOS)


def text_w(d, t, font, size):
    return sum(size * 1.1 if e else d.textlength(x, font=font) for e, x in _runs(t))


def draw_text(img, d, xy, t, font, size, fill):
    x, y = xy
    for e, part in _runs(t):
        if e:
            img.alpha_composite(_emoji_img(part, size), (int(x + size * 0.05), int(y + size * 0.08))); x += size * 1.1
        else:
            d.text((x, y), part, font=font, fill=fill); x += d.textlength(part, font=font)


_BREAK_AFTER = (",", "·", ":", "!", "?", ".", "→")   # 이 글자로 끝나는 낱말 뒤가 좋은 줄바꿈 자리
_BREAK_BEFORE = ("→",)                                 # 이 글자로 시작하면 그 앞에서 바꿔도 좋다


def _words(text):
    words = []
    for w in text.split(" "):          # ❌·⭕ 만 있는 낱말은 앞 낱말에 붙여 혼자 줄바꿈되지 않게
        if words and w and not _EMO.sub("", w).strip():
            words[-1] += " " + w
        else:
            words.append(w)
    return [w for w in words if w]


def _good_breaks(lines):
    """줄이 모두 쉼표·화살표 같은 뜻이 끊기는 자리에서 나뉘었는가."""
    return all(a.rstrip().endswith(_BREAK_AFTER) or b.lstrip().startswith(_BREAK_BEFORE)
               for a, b in zip(lines, lines[1:]))


def _wrap(draw, text, font, max_w, max_lines=3):
    """읽기 좋게 줄을 나눈다.

    한 줄에 들어가면 그대로. 넘치면 가능한 줄 수(2→3) 안에서 모든 나눔을 따져,
    ① 줄마다 폭 안에 들고 ② 쉼표·가운뎃점·화살표 같은 뜻이 끊기는 자리에서 나누며
    ③ 줄 길이가 고르고(한 낱말만 다음 줄로 넘어가는 '돼요' 같은 외톨이 줄 없이)
    ④ 아랫줄이 윗줄보다 너무 길지 않은 나눔을 고른다."""
    import itertools
    words = _words(text)
    W_ = lambda t: text_w(draw, t, font, font.size)
    if W_(" ".join(words)) <= max_w or len(words) < 2:
        return [" ".join(words)]
    best = None
    for n in range(2, max_lines + 1):
        if n > len(words):
            break
        for cut in itertools.combinations(range(1, len(words)), n - 1):
            idx = (0,) + cut + (len(words),)
            lines = [" ".join(words[idx[i]:idx[i + 1]]) for i in range(n)]
            ws = [W_(l) for l in lines]
            if max(ws) > max_w:
                continue
            score = max(ws) - min(ws)                          # 고른 길이
            for i in range(n - 1):
                a, b = words[idx[i + 1] - 1], words[idx[i + 1]]
                if a.endswith(_BREAK_AFTER) or b.startswith(_BREAK_BEFORE):
                    score -= max_w * 0.35                      # 뜻이 끊기는 자리 우대
            if len(words[idx[-2]:]) == 1 and len(words) > 2:
                score += max_w * 0.5                           # 마지막 줄 외톨이 낱말 벌점
            score += n * max_w * 0.15                          # 줄 수는 적을수록
            if best is None or score < best[0]:
                best = (score, lines)
        if best:
            break                                              # 2줄로 되면 3줄은 보지 않는다
    if best:
        return best[1]
    lines, cur = [], ""                                        # 어떤 나눔도 폭에 안 들면 예전 방식
    for w in words:
        t = (cur + " " + w).strip()
        if W_(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur); cur = w
    return lines + ([cur] if cur else [])


def caption_png(text, out, size=62, y_center=1330):
    """화면 아래쪽 자막(반투명 검은 상자 + 흰 글씨, 최대 2줄)."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    f = ImageFont.truetype(BOLD, size)
    lines = _wrap(d, clean(text), f, W - 160, max_lines=2)
    if len(lines) > 1 and not _good_breaks(lines):
        for s2 in (58, 54):                                    # 조금 작게 해서 뜻 단위로 나뉘면 그쪽을 쓴다
            f2 = ImageFont.truetype(BOLD, s2); l2 = _wrap(d, clean(text), f2, W - 160, max_lines=2)
            if _good_breaks(l2) or len(l2) == 1:
                f, lines, size = f2, l2, s2
                break
    lh = size + 18; total = lh * len(lines)
    y = y_center - total // 2
    for ln in lines:
        tw = text_w(d, ln, f, size); x = (W - tw) / 2
        d.rounded_rectangle((x - 28, y - 10, x + tw + 28, y + size + 12), 18, fill=(0, 0, 0, 175))
        draw_text(img, d, (x, y), ln, f, size, (255, 255, 255, 255)); y += lh
    img.save(out)


def chrome_png(series_tag, labels, out, credit=None):
    """본문 내내 보이는 틀: 위쪽 시리즈 띠 + 장면 라벨(설계도 꼬리표 느낌) + AI 고지."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    fk = ImageFont.truetype(BOLD, 40)
    tw = d.textlength(series_tag, font=fk)
    d.rounded_rectangle((48, 150, 48 + tw + 56, 150 + 72), 14, fill=(14, 32, 66, 215))
    d.rectangle((48, 150, 60, 222), fill=(255, 200, 61, 255))
    d.text((48 + 34, 163), series_tag, font=fk, fill=(255, 255, 255, 255))
    y = 270
    if credit:                                  # 루프 편: 인트로 대신 교수 소개를 위쪽 띠 아래에 계속 보여 준다
        fc = ImageFont.truetype(BOLD, 34); cw = d.textlength(credit, font=fc)
        d.rounded_rectangle((48, 232, 48 + cw + 48, 232 + 56), 12, fill=(0, 0, 0, 150))
        d.text((48 + 24, 232 + 9), credit, font=fc, fill=(255, 255, 255, 235)); y = 310
    fl = ImageFont.truetype(BOLD, 44)
    for lab in labels or []:
        lab = clean(lab); w = text_w(d, lab, fl, 44)
        d.rounded_rectangle((48, y, 48 + w + 56, y + 70), 12, fill=(10, 60, 120, 150), outline=(120, 200, 255, 255), width=3)
        draw_text(img, d, (48 + 28, y + 12), lab, fl, 44, (220, 240, 255, 255)); y += 88
    fd = ImageFont.truetype(BOLD, 28)
    disc = "※ 배경은 AI로 생성한 재현 영상입니다"
    d.text(((W - d.textlength(disc, font=fd)) / 2, 1540), disc, font=fd, fill=(255, 255, 255, 190))
    img.save(out)


def norm_args():
    return ["-r", str(FPS), "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart"]


def band(raw, out, headline, kicker, text):
    """HeyGen 가로 영상을 학과 채널 띠 화면에 얹는다(AutoSNS band_layout 재사용)."""
    os.chdir(AUTOSNS)
    import band_layout as BL
    from heygen_anchor import _caption_chunks
    from common import load_config
    hc = load_config().get("heygen", {})
    d = dur(raw)
    tmp = out + ".tmp.mp4"
    BL.compose(hc, raw, tmp, headline, kicker, "", _caption_chunks(text, d), d)
    ff("-i", tmp, "-vf", f"scale={W}:{H},setsar=1", *norm_args(), out)
    os.remove(tmp)
    return out


def intro():
    out = os.path.join(COMMON, "intro.mp4")
    if not os.path.exists(out):
        band(os.path.join(COMMON, "intro_raw.mp4"), out, SERIES, "세명대학교 재난안전학과", CFG["intro_text"])
    return out


def outro(ep_dir, next_text):
    out = os.path.join(ep_dir, "outro.mp4")
    if not os.path.exists(out):
        band(os.path.join(COMMON, "outro_raw.mp4"), out, clean(next_text) or SERIES, SERIES, CFG["outro_text"])
    return out


def card_png(sc, s, out):
    """핵심 정리 카드(무료) — 남색 바탕에 Pretendard Bold 로 제목·수칙 3줄·출처."""
    img = Image.new("RGBA", (W, H), (12, 26, 54, 255)); d = ImageDraw.Draw(img)
    for y in range(H):                                          # 위아래로 살짝 밝아지는 바탕
        d.line([(0, y), (W, y)], fill=(12 + int(10 * y / H), 26 + int(18 * y / H), 54 + int(30 * y / H), 255))
    c = s["card"]; ft = ImageFont.truetype(BOLD, 84); fi = ImageFont.truetype(BOLD, 58); fs = ImageFont.truetype(BOLD, 34)
    d.rectangle((90, 430, 104, 530), fill=(255, 200, 61, 255))
    d.text((130, 432), c.get("title", "핵심 정리"), font=ft, fill=(255, 255, 255, 255))
    y = 640
    for i, item in enumerate(c["items"]):
        d.rounded_rectangle((90, y, W - 90, y + 170), 28, fill=(30, 56, 100, 255), outline=(120, 200, 255, 255), width=3)   # 불투명 색(투명값은 저장 때 흰색이 된다)
        d.ellipse((120, y + 50, 190, y + 120), fill=(255, 200, 61, 255))
        num = str(i + 1); nw = d.textlength(num, font=fi)
        d.text((155 - nw / 2, y + 52), num, font=fi, fill=(12, 26, 54, 255))
        lines = _wrap(d, clean(item), fi, W - 330, max_lines=2)
        ty = y + 85 - len(lines) * 36
        for ln in lines:
            draw_text(img, d, (220, ty), ln, fi, 58, (255, 255, 255, 255)); ty += 72
        y += 200
    src = c.get("source", f"출처: 행정안전부 국민안전24 국민행동요령({sc['type']})")
    d.text(((W - d.textlength(src, font=fs)) / 2, y + 30), src, font=fs, fill=(200, 215, 235, 255))
    img.convert("RGB").save(out)
    return out


def scene_clip(ep_dir, sc, s, style):
    """장면 영상 경로. scene['shots'] 가 있으면 컷들을 이어 붙인 영상을, media=card 면 정리 카드 영상을 만든다."""
    n = s["id"]
    if s.get("media") == "model":                 # anatomy 모형 영상(미리 만들어 둔 것). 없으면 AI 영상으로 대체
        mp = os.path.join(ep_dir, "clips", f"scene{n}_model.mp4")
        if os.path.exists(mp):
            return mp
    if s.get("media") == "diorama":               # 실사 디오라마 + (있으면) 오른쪽 위 계기판 덧씌우기
        dio = os.path.join(ep_dir, "clips", f"scene{n}_{style}_{sc.get('clip_seconds', 8)}s_diorama.mp4")
        gauge = os.path.join(ep_dir, "clips", f"scene{n}_gauge.mp4")
        if os.path.exists(dio):
            if not os.path.exists(gauge) or not (s.get("gauge") or "").strip():
                return dio
            out = dio.replace(".mp4", "_gauge.mp4")
            if not os.path.exists(out):
                ff("-i", dio, "-i", gauge, "-filter_complex",
                   "[0:v]scale=720:1280,setsar=1[b];[1:v]scale=230:-2[g];[b][g]overlay=W-w-22:120:shortest=1[v]",
                   "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out)
            return out
    if s.get("media") == "card":
        png = os.path.join(ep_dir, "clips", f"scene{n}_card.png"); out = png.replace(".png", ".mp4")
        if not os.path.exists(out):
            card_png(sc, s, png)
            ff("-loop", "1", "-i", png, "-vf", "scale=1440:2560,zoompan=z='1+0.04*on/240':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=240:s=720x1280:fps=24,format=yuv420p",
               "-frames:v", "240", "-c:v", "libx264", "-crf", "18", out)
        return out
    if not s.get("shots"):
        return os.path.join(ep_dir, "clips", f"scene{n}_{style}_{sc.get('clip_seconds', 8)}s.mp4")
    parts = [os.path.join(ep_dir, "clips", f"scene{n}_{style}_{sh.get('seconds', 4)}s_shot{k}.mp4")
             for k, sh in enumerate(s["shots"])]
    out = os.path.join(ep_dir, "clips", f"scene{n}_{style}_combined.mp4")
    if not os.path.exists(out):
        inp = sum((["-i", p] for p in parts), [])
        fc = "".join(f"[{i}:v]scale=720:1280,setsar=1,fps=24[v{i}];" for i in range(len(parts)))
        fc += "".join(f"[v{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=1:a=0[v]"
        ff(*inp, "-filter_complex", fc, "-map", "[v]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", out)
    return out


def body(ep_dir, sc, style):
    work = os.path.join(ep_dir, "work"); os.makedirs(work, exist_ok=True)
    tag = f"재난 대응 · {sc['type']}"
    parts = []
    for s in sc["scenes"]:
        n = s["id"]
        voice = os.path.join(ep_dir, "voice", f"scene{n}.wav")
        clip = scene_clip(ep_dir, sc, s, style)
        vd = dur(voice); t = max(vd + 0.45, 3.0); cd = dur(clip)
        slow = min(max(t / cd, 1.0), 1.3)             # 나레이션이 영상보다 길면 최대 1.3배까지 늦추고,
        pad = max(t - cd * slow, 0) + 0.1             # 그래도 모자라면 마지막 장면을 잠깐 멈춰 채운다
        chrome = os.path.join(work, f"chrome{n}.png"); chrome_png(tag, s.get("labels_3d"), chrome, CREDIT if sc.get("loop") else None)
        subs = subs_for(s); caps = []
        for i, (line, (a0, b0)) in enumerate(zip(subs, spans(subs, t))):
            p = os.path.join(work, f"cap{n}_{i}.png"); caption_png(line, p)
            caps.append((a0, b0, p))
        inputs = ["-i", clip, "-i", voice, "-loop", "1", "-i", chrome]
        for _, _, p in caps:
            inputs += ["-loop", "1", "-i", p]
        fc = [f"[0:v]setpts={slow:.4f}*PTS,tpad=stop_mode=clone:stop_duration={pad:.2f},scale={W}:{H}:flags=lanczos,setsar=1[v0]", "[v0][2:v]overlay=0:0[v1]"]
        last = "v1"
        for i, (a, b, _) in enumerate(caps):
            fc.append(f"[{last}][{i + 3}:v]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[c{i}]"); last = f"c{i}"
        fc.append(f"[1:a]apad=whole_dur={t:.2f},loudnorm=I=-14:TP=-1.5[a]")
        part = os.path.join(work, f"part{n}.mp4")
        ff(*inputs, "-filter_complex", ";".join(fc), "-map", f"[{last}]", "-map", "[a]", "-t", f"{t:.2f}",
           *norm_args(), part)
        parts.append(part)
    return parts


MAX_SEC = 29.5
REMOTION = os.path.join(CFG["root"], "remotion")   # 10/15 본문 조립을 Remotion 으로(실패하면 예전 ffmpeg 방식)
CREDIT = "세명대학교 재난안전학과 나영우 교수"


def _chunks(narration, maxlen=20):
    """나레이션을 문장 → 단어 단위로 끊어 화면 자막 조각으로 만든다(대본 문장 그대로, 줄이거나 바꾸지 않는다)."""
    out = []
    for sent in re.split(r"(?<=[.!?])\s+", clean(narration).strip()):
        if not sent:
            continue
        if len(sent) <= maxlen + 4:
            out.append(sent); continue
        cur = ""
        for w in sent.split(" "):
            if cur and len(cur) + 1 + len(w) > maxlen:
                out.append(cur); cur = w
            else:
                cur = (cur + " " + w).strip()
        if cur:
            out.append(cur)
    return out


def subs_for(s):
    """화면 자막 조각들. config.captions_from_script(기본 true)면 대본 문장 그대로, 아니면 대본에 따로 쓴 subtitle."""
    if CFG.get("captions_from_script", True) and (s.get("narration") or "").strip():
        return _chunks(s["narration"])
    return list(s.get("subtitle") or [])


def spans(subs, total):
    """글자 수에 비례해 자막 조각마다 보여 줄 구간(0~total)을 나눈다."""
    w = [max(len(re.sub(r"\s", "", x)), 1) for x in subs]; tot = float(sum(w)) or 1.0
    out, acc = [], 0.0
    for x in w:
        out.append((total * acc / tot, total * (acc + x) / tot)); acc += x
    return out


def hook_lines(sc):
    """첫 2.6초 화면 훅(2줄 이내). script.hook_text(문자열·목록) 없으면 제목의 '|' 앞부분."""
    h = sc.get("hook_text")
    if isinstance(h, list):
        return [clean(x) for x in h if clean(x)][:2]
    t = clean(h or (sc.get("title") or "").split("|")[0]).strip()
    if not t:
        return []
    if len(t) <= 11:
        return [t]
    mid = len(t) // 2
    cuts = [i for i, ch in enumerate(t) if ch in " ,"]
    i = min(cuts, key=lambda k: abs(k - mid)) if cuts else mid
    a, b = t[:i + 1].strip(), t[i + 1:].strip()
    return [x for x in (a, b) if x]


def hook_png(lines, out, y=1450):
    """인트로 위에 얹는 훅 박스(투명 1080x1920 PNG). 아바타 얼굴·AI 표시 띠 아래 빈 공간에 둔다."""
    from shared.fonts import font_path, DISPLAY
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(img)
    longest = max(len(x) for x in lines)
    size = min(104, 880 // max(longest, 1))
    f = ImageFont.truetype(font_path(DISPLAY), size)
    tw = max(d.textlength(x, font=f) for x in lines)
    lh = int(size * 1.25); padx, pady, bar = 46, 34, 14
    bw, bh = int(tw + padx * 2 + bar), int(lh * len(lines) + pady * 2)
    x0 = (W - bw) // 2
    d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=26, fill=(8, 18, 40, 212))
    d.rounded_rectangle([x0, y, x0 + bar + 10, y + bh], radius=14, fill=(255, 200, 61, 255))
    d.rectangle([x0 + bar, y, x0 + bar + 14, y + bh], fill=(8, 18, 40, 212))
    for i, ln in enumerate(lines):
        d.text((x0 + bar + padx, y + pady + i * lh), ln, font=f, fill=(255, 227, 163, 255) if i == 0 else (255, 255, 255, 255))
    img.save(out)


def overlay_hook(video, lines, seconds, work, y=1450):
    """final 영상 맨 앞 seconds 초에 훅 박스를 얹는다(페이드 인·아웃)."""
    png = os.path.join(work, "hook_overlay.png"); hook_png(lines, png, y)
    tmp = video + ".hook.mp4"; fo = max(seconds - 0.4, 0.5)
    ff("-i", video, "-loop", "1", "-t", f"{seconds:.2f}", "-i", png, "-filter_complex",
       f"[1:v]format=rgba,fade=t=in:st=0:d=0.3:alpha=1,fade=t=out:st={fo:.2f}:d=0.4:alpha=1[h];"
       f"[0:v][h]overlay=0:0:eof_action=pass:enable='lt(t,{seconds + 0.1:.2f})'[v]",
       "-map", "[v]", "-map", "0:a", *norm_args(), tmp)
    os.replace(tmp, video)



def caption_layout(text, size=62):
    """caption_png 과 같은 규칙으로 줄을 나누고 글자 크기를 고른다 → (lines, size)."""
    d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    f = ImageFont.truetype(BOLD, size)
    lines = _wrap(d, clean(text), f, W - 160, max_lines=2)
    if len(lines) > 1 and not _good_breaks(lines):
        for s2 in (58, 54):
            f2 = ImageFont.truetype(BOLD, s2); l2 = _wrap(d, clean(text), f2, W - 160, max_lines=2)
            if _good_breaks(l2) or len(l2) == 1:
                return l2, s2
    return lines, size


def remotion_body(ep_dir, sc, style, out):
    """장면 영상은 파이썬이 속도·길이를 맞춰 두고, 화면 장식·자막·나레이션 배치는 Remotion 이 그린다."""
    import shutil, subprocess
    work = os.path.join(ep_dir, "work"); os.makedirs(work, exist_ok=True)
    job = os.path.join(REMOTION, "public", "job")
    shutil.rmtree(job, ignore_errors=True); os.makedirs(job)
    def put(src, name):
        dst = os.path.join(job, name)
        try:
            os.link(src, dst)
        except OSError:
            shutil.copy(src, dst)
        return f"job/{name}"
    scenes = []
    for s in sc["scenes"]:
        n = s["id"]
        voice = os.path.join(ep_dir, "voice", f"scene{n}.wav")
        gauge = None
        dio = os.path.join(ep_dir, "clips", f"scene{n}_{style}_{sc.get('clip_seconds', 8)}s_diorama.mp4")
        if s.get("media") == "diorama" and os.path.exists(dio):
            clip = dio
            g = os.path.join(ep_dir, "clips", f"scene{n}_gauge.mp4")
            gauge = put(g, f"gauge{n}.mp4") if (s.get("gauge") or "").strip() and os.path.exists(g) else None   # 필요할 때만
        else:
            clip = scene_clip(ep_dir, sc, s, style)
        vd = dur(voice); t = max(vd + 0.45, 3.0); cd = dur(clip)
        slow = min(max(t / cd, 1.0), 1.3)
        pad = max(t - cd * slow, 0) + 0.1
        prep = os.path.join(work, f"prep{n}.mp4")
        ff("-i", clip, "-vf", f"setpts={slow:.4f}*PTS,tpad=stop_mode=clone:stop_duration={pad:.2f},scale={W}:{H}:flags=lanczos,setsar=1,fps={FPS}",
           "-an", "-t", f"{t:.2f}", "-c:v", "libx264", "-crf", "17", "-pix_fmt", "yuv420p", prep)
        frames = int(round(t * FPS))
        subs = subs_for(s)
        caps = []
        for line, (a0, b0) in zip(subs, spans(subs, frames)):
            lines, size = caption_layout(line)
            caps.append({"lines": lines, "size": size, "from": int(a0), "to": int(b0)})
        scenes.append({"id": n, "clip": put(prep, f"clip{n}.mp4"), "voice": put(voice, f"voice{n}.wav"), "frames": frames,
                       "labels": [clean(x) for x in (s.get("labels_3d") or [])], "captions": caps, "gauge": gauge,
                       "motions": [dict(kind=m["kind"], num=m.get("num"), text=clean(m["text"]), sub=clean(m.get("sub", "")) or None, enter=m.get("enter", "fade"), tone=m.get("tone", "safe"), y=m.get("y", 340),
                                       **{"from": int(round(m["from_s"] * FPS)), "to": frames + int(round(m["to_s"] * FPS)) if m["to_s"] <= 0 else int(round(m["to_s"] * FPS))}) for m in (s.get("motions") or [])]})
    props = {"tag": f"재난 대응 · {sc['type']}", "credit": CREDIT if sc.get("loop") else None, "disclaimer": sc.get("disclaimer", ""), "scenes": scenes,
             "hook": ([] if CFG.get("intro_outro", False) else hook_lines(sc)), "hook_frames": int(round(float(CFG.get("hook_seconds", 2.6)) * FPS))}
    pp = os.path.join(work, "remotion_props.json")
    json.dump(props, open(pp, "w", encoding="utf-8"), ensure_ascii=False)
    npx = shutil.which("npx") or "/usr/local/bin/npx"   # launchd 는 PATH 가 짧다
    env = dict(os.environ, PATH="/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", ""))
    r = subprocess.run([npx, "remotion", "render", "src/index.ts", "DisasterShort", out, f"--props={pp}", "--concurrency=50%", "--log=error"],
                       cwd=REMOTION, env=env, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0 or not os.path.exists(out):
        raise RuntimeError("Remotion 렌더 실패: " + (r.stderr or r.stdout)[-800:])
    return out


def concat(files, out, max_sec=None):
    lst = out + ".txt"
    open(lst, "w").write("".join(f"file '{f}'\n" for f in files))
    total = sum(dur(f) for f in files)
    sp = min(max(total / (max_sec or MAX_SEC), 1.0), 1.2)        # 30초 안으로 — 최대 1.2배까지만(그 이상은 대본을 줄인다)
    v = f"setpts=PTS/{sp:.4f}" if sp > 1 else "null"
    a = (f"atempo={sp:.4f}," if sp > 1 else "") + "loudnorm=I=-14:TP=-1.5"
    ff("-f", "concat", "-safe", "0", "-i", lst, "-vf", v, "-af", a, *norm_args(), out)
    os.remove(lst)
    if sp > 1:
        print(f"  {total:.1f}초 → {sp:.2f}배속")
    return sp


def thumbnail(ep_dir, sc, style, out):
    """썸네일 = 인트로 뒤 본문 첫 화면(장면 1 첫 컷) + 큰 제목.

    작은 자막·꼬리표는 빼고(큰 제목과 겹쳐 지저분해진다), 위쪽을 어둡게 깔아 제목을 크게 얹는다.
    제목 속 재난 이름(예: '산불')은 노란색으로 강조한다."""
    first = next((s for s in sc["scenes"] if s.get("media") not in ("model", "card", "diorama")), sc["scenes"][0])   # 썸네일은 실사 장면에서
    clip = scene_clip(ep_dir, sc, first, style)
    raw = out + ".raw.png"
    ff("-ss", "0.3", "-i", clip, "-frames:v", "1", "-vf", f"scale={W}:{H}:flags=lanczos", raw)
    img = Image.open(raw).convert("RGBA"); os.remove(raw)
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sd = ImageDraw.Draw(shade)
    for y in range(0, 1100):                                   # 위에서 아래로 옅어지는 어두운 판
        sd.line([(0, y), (W, y)], fill=(5, 12, 28, int(225 * max(0, 1 - y / 1100) ** 0.8)))
    img.alpha_composite(shade); d = ImageDraw.Draw(img)
    # 시리즈 꼬리표
    fk = ImageFont.truetype(BOLD, 44); tag = f"재난 대응 #{sc.get('ep_no', 1)} · {sc['type']}"
    tw = d.textlength(tag, font=fk)
    d.rounded_rectangle((70, 190, 70 + tw + 64, 190 + 80), 16, fill=(220, 40, 50, 235))
    d.text((70 + 32, 190 + 14), tag, font=fk, fill=(255, 255, 255, 255))
    # 큰 제목(‘|’ 앞 부분), 최대 3줄
    title = sc["title"].split("|")[0].strip()
    size, lines = 112, None
    for sz in (112, 104, 96):                                  # 두 줄에 들어가는 가장 큰 크기
        ft = ImageFont.truetype(BOLD, sz)
        l = _wrap(d, title, ft, W - 150, max_lines=2)
        if len(l) <= 2:
            size, lines = sz, l
            break
    if lines is None:                                          # 그래도 안 되면 큰 글씨로 세 줄
        ft = ImageFont.truetype(BOLD, size); lines = _wrap(d, title, ft, W - 150, max_lines=3)
    y = 320; key = sc["type"]
    for ln in lines:
        x = 70
        for i, part in enumerate(ln.split(key)):              # 재난 이름만 노란색
            for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (3, 3), (-3, 3), (3, -3), (-3, -3)):
                d.text((x + dx, y + dy), part, font=ft, fill=(0, 0, 0, 255))
            d.text((x, y), part, font=ft, fill=(255, 255, 255, 255)); x += d.textlength(part, font=ft)
            if i < len(ln.split(key)) - 1:
                for dx, dy in ((-4, 0), (4, 0), (0, -4), (0, 4), (3, 3), (-3, 3), (3, -3), (-3, -3)):
                    d.text((x + dx, y + dy), key, font=ft, fill=(0, 0, 0, 255))
                d.text((x, y), key, font=ft, fill=(255, 210, 60, 255)); x += d.textlength(key, font=ft)
        y += int(size * 1.22)
    # 아래 학과 이름 — 크게, 진한 남색 띠 위에 흰 글씨(+노란 강조선)로 어디서나 읽히게
    fs = ImageFont.truetype(BOLD, 76); s = "세명대학교 재난안전학과"
    sw = d.textlength(s, font=fs); bx0 = (W - sw) / 2 - 44; by0 = 1560
    d.rounded_rectangle((bx0, by0, bx0 + sw + 88, by0 + 132), 22, fill=(14, 32, 66, 240))
    d.rectangle((bx0 + 22, by0 + 112, bx0 + sw + 66, by0 + 120), fill=(255, 200, 61, 255))
    d.text(((W - sw) / 2, by0 + 18), s, font=fs, fill=(255, 255, 255, 255))
    img.convert("RGB").save(out, quality=92)
    return out


def assemble(ep):
    ep_dir = os.path.join(CFG["root"], ep)
    sc = json.load(open(os.path.join(ep_dir, "script.json"), encoding="utf-8"))
    style = sc.get("style", "3d_real")
    use_io = bool(CFG.get("intro_outro", False))         # 인트로·아웃트로(인준 아바타) 붙이기 — 2026-10-22
    files = None
    if os.path.isdir(os.path.join(REMOTION, "node_modules")) and not os.environ.get("SHORTS_NO_REMOTION"):
        try:
            files = [remotion_body(ep_dir, sc, style, os.path.join(ep_dir, "work", "remotion_body.mp4"))]
            print("본문 조립: Remotion")
        except Exception as e:
            print("Remotion 실패 → 예전 방식으로:", str(e)[:300])
    if files is None:
        files = body(ep_dir, sc, style)
    if use_io:
        # Remotion 본문은 yuvj420p·다른 타임베이스라 인트로·아웃트로와 바로 이으면 영상이 몇 배로 늘어난다 — 같은 규격으로 맞춘 뒤 잇는다.
        nb = os.path.join(ep_dir, "work", "body_norm.mp4")
        ff("-i", files[0], "-vf", f"scale={W}:{H}:out_range=tv,setsar=1,fps={FPS}", *norm_args(), nb)
        files = [intro(), nb, outro(ep_dir, sc.get("next_episode_text", ""))]
    out = os.path.join(ep_dir, "final.mp4")
    sp = concat(files, out, sc.get("max_seconds"))
    if use_io and hook_lines(sc):          # 인트로 위 훅(2026-10-22 사용자 승인): 첫 프레임부터 보이게
        overlay_hook(out, hook_lines(sc), float(CFG.get("hook_seconds", 2.6)), os.path.join(ep_dir, "work"), int(CFG.get("hook_y", 1450)))
    intro_end = dur(files[0]) / sp if CFG.get("intro_outro", False) else 0.0
    thumbnail(ep_dir, sc, style, os.path.join(ep_dir, "thumbnail.jpg"))
    json.dump({"speed": round(sp, 4), "intro_end": round(intro_end, 2)},
              open(os.path.join(ep_dir, "meta.json"), "w"), indent=1)
    print(f"완료: {out} ({dur(out):.1f}초)")
    return out


if __name__ == "__main__":
    assemble(sys.argv[1])
