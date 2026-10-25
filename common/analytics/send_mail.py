"""주간 리포트를 지정한 지메일 계정으로 보낸다. (표준 라이브러리만 사용)

보내는 주소를 우리가 정해야 해서 Gmail 커넥터 대신 SMTP 로 직접 부친다.
비밀번호는 구글 계정의 '앱 비밀번호'(2단계 인증 사용 시 발급)를 쓴다.
로그인 비밀번호를 그대로 넣으면 구글이 막는다.

mail_config.json (git 에 올라가지 않음):
{
  "sender": "semyungds@gmail.com",
  "app_password": "",   ← 비워 둔다. 앱 비밀번호는 암호화 저장소의 MAIL_APP_PASSWORD(set_mail_password.py 로 입력)
  "to": ["ds2eye@gmail.com", "yunju24@semyung.ac.kr"],
  "sender_name": "세명대 재난안전학과"
}

사용:  python3 send_mail.py out/weekly_2026-08-31.html "제목" [첨부.hwpx 첨부.xlsx ...]
"""
import json
import os
import re
import smtplib
import sys
import time
from email.header import Header
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))))
from analytics.common import BASE_DIR, log  # noqa: E402

CONFIG_PATH = os.path.join(BASE_DIR, "mail_config.json")
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465


def load_config():
    if not os.path.exists(CONFIG_PATH):
        raise SystemExit(
            "mail_config.json 이 없습니다. mail_config.example.json 을 복사해\n"
            "  sender / app_password / to 를 채우세요.\n"
            "앱 비밀번호는 https://myaccount.google.com/apppasswords 에서 발급합니다."
        )
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 앱 비밀번호는 암호화 저장소에 있다(2026-10-17). 파일에는 보내는 계정·받는 사람만.
    from shared.secret_get import get
    cfg["app_password"] = get("MAIL_APP_PASSWORD") or cfg.get("app_password", "")
    for k in ("sender", "app_password", "to"):
        if not cfg.get(k):
            raise SystemExit(f"mail_config.json 에 {k} 값이 비어 있습니다.")
    return cfg


def to_plain(html):
    """HTML 을 못 읽는 메일 클라이언트용 대체 본문."""
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.S)
    t = re.sub(r"</(p|div|h1|h2|tr|li)>", "\n", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n", t)).strip()


def build_message(html_path, subject, cfg, attachments=None):
    """보낼 메시지를 조립한다. (발송 전에 내용을 확인할 수 있도록 분리)"""
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    body = MIMEMultipart("alternative")
    body.attach(MIMEText(to_plain(html), "plain", "utf-8"))
    body.attach(MIMEText(html, "html", "utf-8"))

    files = [p for p in (attachments or []) if p and os.path.exists(p)]
    if files:
        msg = MIMEMultipart("mixed")
        msg.attach(body)
        for path in files:
            with open(path, "rb") as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(path))
            # 한글 파일명은 RFC2231 로 인코딩해야 클라이언트에서 깨지지 않는다.
            part.set_param("name", os.path.basename(path), charset="utf-8", language="ko")
            part.add_header("Content-Disposition", "attachment")
            part.set_param("filename", os.path.basename(path), header="Content-Disposition",
                           charset="utf-8", language="ko")
            msg.attach(part)
    else:
        msg = body

    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg.get("sender_name", "재난안전학과"), "utf-8")),
                              cfg["sender"]))
    msg["To"] = ", ".join(cfg["to"])
    return msg, files


def send(html_path, subject, cfg=None, attachments=None, tries=3):
    """attachments: 첨부할 파일 경로 목록(없는 파일은 건너뛴다).

    절전 해제 직후처럼 네트워크가 덜 올라온 때를 대비해 몇 번 다시 시도한다.
    인증 오류(앱 비밀번호 문제)는 다시 걸어도 소용없으므로 바로 올린다."""
    cfg = cfg or load_config()
    msg, files = build_message(html_path, subject, cfg, attachments)
    for attempt in range(1, tries + 1):
        try:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
                s.login(cfg["sender"], cfg["app_password"])
                s.sendmail(cfg["sender"], cfg["to"], msg.as_string())
            break
        except smtplib.SMTPAuthenticationError:
            raise
        except Exception as e:
            if attempt == tries:
                raise
            log(f"발송 실패({type(e).__name__}) — {attempt}/{tries}, 60초 뒤 다시 시도한다")
            time.sleep(60)
    log(f"메일 발송: {cfg['sender']} → {', '.join(cfg['to'])} / {subject}"
        + (f" (첨부 {len(files)}개)" if files else ""))
    return {"status": "sent", "to": cfg["to"], "from": cfg["sender"], "attachments": len(files)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("사용: python3 send_mail.py <리포트.html> <제목> [첨부파일 ...]")
    send(sys.argv[1], sys.argv[2], attachments=sys.argv[3:])
