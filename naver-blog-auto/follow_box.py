"""글 끝 '새 글 받아보기' 상자 — 두 Blogger 블로그 공용.

글을 끝까지 읽은 사람에게 다시 찾아올 길을 준다(2026-10-17 팔로워 늘리기).
- 팔로우: 같은 페이지 사이드바의 Blogger 팔로워 위젯(#Followers1)으로 내려 보낸다.
  팔로우는 그 위젯 안에서만 누를 수 있다(바로 가는 주소가 없다).
- 유튜브 구독: 채널 주소에 ?sub_confirmation=1 을 붙이면 구독 확인 창이 바로 뜬다.
- 이메일 구독: config.<section>.follow.email_url 이 있을 때만(follow.it 등).
- RSS: Blogger 기본 피드.

section 은 config 키 — 'geoai'(GeoAI 블로그) 또는 'blogger'(학과 블로그).
"""
import html

_esc = html.escape

BOX = ('<div style="margin:1.6em 0;padding:16px 18px;border:1px solid #d6e2f0;'
       'border-radius:12px;background:#f4f8fc">'
       '<p style="margin:0 0 8px;font-weight:700">🔔 새 글 받아보기</p>'
       '<p style="margin:0 0 10px">{lead}</p>'
       '<p style="margin:0;line-height:2">{links}</p></div>')


def follow_box_html(cfg, section):
    sec = (cfg or {}).get(section) or {}
    f = sec.get("follow") or {}
    if f.get("enabled", True) is False:
        return ""
    blog = (sec.get("url") or "").rstrip("/")
    yt = f.get("youtube") or next((l["url"] for l in sec.get("links") or []
                                   if "youtube.com/@" in (l.get("url") or "")), "")
    items = [("#Followers1", "➕ 이 블로그 팔로우", False)]
    if f.get("email_url"):
        items.append((f["email_url"], "✉️ 이메일로 받기", True))
    if yt:
        items.append((yt.split("?")[0] + "?sub_confirmation=1", "▶️ 유튜브 구독", True))
    if blog:
        items.append((blog + "/feeds/posts/default", "📡 RSS", True))
    links = " &nbsp;·&nbsp; ".join(
        f'<a href="{_esc(u)}"' + (' target="_blank" rel="noopener"' if ext else "")
        + f'>{_esc(t)}</a>' for u, t, ext in items)
    lead = f.get("text") or "도움이 되셨다면 팔로우해 두세요. 새 글이 올라오면 바로 알 수 있습니다."
    return BOX.format(lead=_esc(lead), links=links)
