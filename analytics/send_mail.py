"""주간 리포트를 지정한 지메일 계정으로 보낸다. (표준 라이브러리만 사용)

보내는 주소를 우리가 정해야 해서 Gmail 커넥터 대신 SMTP 로 직접 부친다.
비밀번호는 구글 계정의 '앱 비밀번호'(2단계 인증 사용 시 발급)를 쓴다.
로그인 비밀번호를 그대로 넣으면 구글이 막는다.

mail_config.json (git 에 올라가지 않음):
{
  "sender": "semyungds@gmail.com",
  "app_password": "여기에 앱 비밀번호 16자리",
  "to": ["ds2eye@gmail.com", "yunju24@semyung.ac.kr"],
  "sender_name": "세명대 재난안전학과"
}

사용:  python3 send_mail.py out/weekly_2026-08-31.html "[재난안전학과] SNS 주간 리포트 (8월 25일~8월 31일)"
"""
import json
import os
import re
import smtplib
import sys
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def send(html_path, subject, cfg=None):
    cfg = cfg or load_config()
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg.get("sender_name", "재난안전학과"), "utf-8")),
                              cfg["sender"]))
    msg["To"] = ", ".join(cfg["to"])
    msg.attach(MIMEText(to_plain(html), "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as s:
        s.login(cfg["sender"], cfg["app_password"])
        s.sendmail(cfg["sender"], cfg["to"], msg.as_string())
    log(f"메일 발송: {cfg['sender']} → {', '.join(cfg['to'])} / {subject}")
    return {"status": "sent", "to": cfg["to"], "from": cfg["sender"]}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("사용: python3 send_mail.py <리포트.html> <제목>")
    send(sys.argv[1], sys.argv[2])
