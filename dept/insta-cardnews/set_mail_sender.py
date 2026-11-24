"""인스타 대체 메일을 보낼 계정(config.json instagram.email_from)의 앱 비밀번호를 입력한다(2026-11-24).

입력한 값은 화면에 보이지 않고, 구글 SMTP 로그인이 실제로 되는지 확인한 뒤에만 암호화 저장소에 저장한다.
    python set_mail_sender.py
"""
import getpass
import os
import re
import smtplib
import sys

from common import BASE_DIR, load_config
from email_delivery import SENDER_SECRET

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), "common"))
from shared.secret_get import put  # noqa: E402

sender = (load_config().get("instagram") or {}).get("email_from")
if not sender:
    raise SystemExit("config.json 의 instagram.email_from 이 비어 있습니다.")
print(f"보내는 계정: {sender}")
for _ in range(3):
    pw = re.sub(r"\s+", "", getpass.getpass("앱 비밀번호 16자리(입력해도 화면에 보이지 않습니다): "))
    if len(pw) != 16:
        print(f"  16자리가 아닙니다({len(pw)}자리). 다시 입력하세요.")
        continue
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as s:
            s.login(sender, pw)
    except smtplib.SMTPAuthenticationError:
        print("  구글이 로그인을 거부했습니다. 앱 비밀번호를 다시 확인하세요.")
        continue
    put(SENDER_SECRET, pw)
    print("로그인 확인 — 저장했습니다. 이 창을 닫아도 됩니다.")
    break
else:
    print("저장하지 못했습니다.")
input("Enter 를 누르면 닫힙니다.")
