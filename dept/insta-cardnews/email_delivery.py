"""자동 게시 대신 완성 콘텐츠를 조교에게 이메일로 보낸다 — 조교가 @smu.safety 에 직접 올린다(2026-11-24 사용자 지정).

config.json 의 instagram.paused=true 이고 instagram.email_to 에 받는 사람이 있으면 run_weekly.py 가 이것을 부른다.
먼저 backup/emailed/<날짜_제목>/ 에 캡션·첫 댓글·카드·릴을 모아 두고(메일이 실패해도 콘텐츠가 남는다), 그 폴더를 보낸다.
보내는 계정·앱 비밀번호는 common/analytics/send_mail.py 설정(mail_config.json, MAIL_APP_PASSWORD)을 그대로 쓴다.

  python email_delivery.py --resend backup/emailed/<폴더>   # 실패한 묶음을 다시 보낸다
  python email_delivery.py --resend <폴더> --dry-run        # 보낼 내용만 확인
"""
import argparse
import html
import json
import os
import re
import shutil
import sys
from datetime import datetime

from common import BASE_DIR, load_config, log

SENDER_SECRET = "MAIL_APP_PASSWORD_INSTA"   # instagram.email_from 계정의 앱 비밀번호(암호화 저장소)
_COMMON = os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "common")
OUT_ROOT = os.path.join(BASE_DIR, "backup", "emailed")
MAX_ATTACH = 18 * 1024 * 1024     # Gmail 25MB 한도(첨부는 base64 로 약 4/3배)


def _mailer():
    if _COMMON not in sys.path:
        sys.path.insert(0, _COMMON)
    from analytics import send_mail
    return send_mail


def package(data, cfg):
    """보낼 묶음 폴더를 만든다 → 폴더 경로."""
    from post_instagram import _build_caption, _first_comment_text
    ig = cfg.get("instagram", {})
    title = (data.get("title") or "재난안전 카드뉴스").strip()
    safe = re.sub(r'[\\/:*?"<>|\s]+', "_", title)[:40].strip("_")
    d = os.path.join(OUT_ROOT, f"{datetime.now():%Y-%m-%d}_{safe}")
    os.makedirs(d, exist_ok=True)
    files = []
    if cfg.get("reel", {}).get("enabled") and data.get("reel") and os.path.exists(data["reel"]):
        files.append(data["reel"])
        if data.get("cover") and os.path.exists(data["cover"]):
            files.append(data["cover"])
    files += [p for p in (data.get("images") or []) if os.path.exists(p)]
    names, links = [], {}
    for i, p in enumerate(files):
        n = os.path.basename(p)
        if n in names:
            n = f"{i:02d}_{n}"
        dst = os.path.join(d, n)
        shutil.copy2(p, dst)
        if p.lower().endswith(".mp4"):
            # 릴은 줄이지 않고 구글 드라이브에 올려 링크로 보낸다(2026-11-25 사용자 지시). 실패하면 첨부로 넘긴다.
            try:
                from drive_link import upload
                links[n], _ = upload(dst, f"{datetime.now():%Y-%m-%d} {title}.mp4", ig.get("email_to") or ())
                continue
            except Exception as e:  # noqa: BLE001
                log(f"드라이브 업로드 실패 → 첨부로: {type(e).__name__}: {str(e)[:120]}")
        names.append(n)
    caption = _build_caption(data, cfg)
    first = _first_comment_text(data, cfg) if ig.get("first_comment") else ""
    with open(os.path.join(d, "캡션.txt"), "w", encoding="utf-8") as f:
        f.write(caption + "\n")
    if first:
        with open(os.path.join(d, "첫댓글.txt"), "w", encoding="utf-8") as f:
            f.write(first + "\n")
    meta = {"title": title, "made_at": datetime.now().isoformat(timespec="seconds"),
            "files": names, "drive_links": links, "to": ig.get("email_to"), "sent": False}
    with open(os.path.join(d, "delivery.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    log(f"이메일 묶음 준비: {d} (파일 {len(names)}개)")
    return d


def _attachments(d, meta, only=None):
    """첨부를 메일 한 통 용량(MAX_ATTACH) 안으로 나눈다 → (묶음 목록, 한 통에도 안 들어가는 파일).
    릴과 카드를 합치면 한도를 넘어 릴이 빠졌다(2026-11-25) — 넘치면 다음 메일로 나눠 보낸다."""
    groups, left, cur, total = [], [], [], 0
    order = only or (["캡션.txt", "첫댓글.txt"] + list(meta.get("files") or []))
    for n in order:
        p = os.path.join(d, n)
        if not os.path.exists(p):
            continue
        sz = os.path.getsize(p)
        if sz > MAX_ATTACH:
            left.append(n)
            continue
        if cur and total + sz > MAX_ATTACH:
            groups.append(cur)
            cur, total = [], 0
        cur.append(p)
        total += sz
    if cur:
        groups.append(cur)
    return groups, left


def send_folder(d, to=None, dry_run=False, only=None):
    with open(os.path.join(d, "delivery.json"), encoding="utf-8") as f:
        meta = json.load(f)
    to = to or meta.get("to")
    if not to:
        raise RuntimeError("받는 사람(instagram.email_to)이 없습니다")
    caption = open(os.path.join(d, "캡션.txt"), encoding="utf-8").read().strip()
    fp = os.path.join(d, "첫댓글.txt")
    first = open(fp, encoding="utf-8").read().strip() if os.path.exists(fp) else ""
    groups, left = _attachments(d, meta, only)
    n_all = sum(len(g) for g in groups)
    pre = lambda s: f'<pre style="white-space:pre-wrap;font-family:inherit">{html.escape(s)}</pre>'
    base = f"[재난안전학과 인스타 콘텐츠] {meta['title']}"
    mails = []
    for i, g in enumerate(groups or [[]]):
        part = f" ({i + 1}/{len(groups)})" if len(groups) > 1 else ""
        names = ", ".join(os.path.basename(p) for p in g)
        if i == 0 and not only:
            body = (f"<p>이번 회차 학과 인스타그램(@smu.safety) 콘텐츠입니다. 첨부한 릴 영상·카드 이미지와 아래 캡션으로 올려 주세요.</p>"
                    f"<h2>{html.escape(meta['title'])}</h2>"
                    f"<h3>캡션</h3>{pre(caption)}"
                    + (f"<h3>첫 댓글</h3>{pre(first)}" if first else "")
                    + "".join(f'<p>릴 영상(원본, 구글 드라이브): <a href="{html.escape(u)}">{html.escape(u)}</a></p>'
                              for u in (meta.get("drive_links") or {}).values())
                    + f"<p>첨부: 모두 {n_all}개(카드 이미지·캡션 파일)" + (f", 메일 {len(groups)}통에 나눠 보냅니다" if len(groups) > 1 else "")
                    + f". 이 메일: {html.escape(names)}</p>")
        else:
            body = (f"<p>「{html.escape(meta['title'])}」 이어서 보내는 첨부입니다{part}. 캡션은 첫 메일에 있습니다.</p>"
                    f"<p>이 메일: {html.escape(names)}</p>")
        if left and i == len(groups) - 1:
            body += f"<p>너무 커서 못 보낸 파일: {html.escape(', '.join(left))} — 학과 PC {html.escape(d)} 에 있습니다.</p>"
        body += "<p>세명대 재난안전학과 자동 발행 시스템</p>"
        hp = os.path.join(d, f"mail{i + 1}.html")
        with open(hp, "w", encoding="utf-8") as f:
            f.write(body)
        mails.append((hp, base + part, g))
    if dry_run:
        for hp, subj, g in mails:
            log(f"(dry-run) {subj} → {to} / 첨부 {[os.path.basename(p) for p in g]}")
        log(f"(dry-run) 빠짐 {left}")
        return {"status": "dry_run", "mails": len(mails), "attachments": n_all}
    sm = _mailer()
    mcfg = sm.load_config()
    mcfg["to"] = list(to) if isinstance(to, (list, tuple)) else [to]
    sender = (load_config().get("instagram") or {}).get("email_from")
    if sender:   # 2026-11-24 사용자 지시: 학과 계정이 본인 인증에 막혀 개인 계정으로 보낸다
        from shared.secret_get import get
        pw = get(SENDER_SECRET)
        if not pw:
            raise RuntimeError(f"{sender} 앱 비밀번호가 없습니다 — python set_mail_sender.py 로 입력하세요")
        mcfg.update(sender=sender, app_password=pw, smtp_only=True)
    sent = 0
    for hp, subj, g in mails:
        sent += sm.send(hp, subj, cfg=mcfg, attachments=g).get("attachments") or 0
    meta.update(sent=True, sent_at=datetime.now().isoformat(timespec="seconds"), sent_to=mcfg["to"],
                mails=len(mails), not_sent=left)
    with open(os.path.join(d, "delivery.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    return {"status": "emailed", "images": len(meta.get("files") or []), "to": mcfg["to"],
            "attachments": sent, "mails": len(mails)}


def deliver(data, cfg):
    """run_weekly 에서 부른다. 묶음을 만들고 보낸다. 보내기가 실패하면 묶음은 남기고 예외를 올린다."""
    d = package(data, cfg)
    try:
        return send_folder(d, cfg.get("instagram", {}).get("email_to"))
    except Exception as e:
        raise RuntimeError(f"이메일 발송 실패({type(e).__name__}: {str(e)[:120]}) — 묶음은 {d} 에 있습니다. "
                           f"고친 뒤 python email_delivery.py --resend \"{d}\"") from e


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--resend", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", nargs="+", help="이 파일만 보낸다(빠졌던 릴만 다시 보낼 때)")
    a = ap.parse_args()
    print(send_folder(os.path.abspath(a.resend), dry_run=a.dry_run, only=a.only))
