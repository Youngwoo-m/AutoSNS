"""mail_config.json 에 앱 비밀번호를 입력한다. 화면에 찍히지 않고 셸 기록에도 남지 않는다.

사용:  python3 set_mail_password.py
"""
import getpass
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analytics.common import BASE_DIR  # noqa: E402

PATH = os.path.join(BASE_DIR, "mail_config.json")

if not os.path.exists(PATH):
    raise SystemExit("mail_config.json 이 없습니다. mail_config.example.json 을 먼저 복사하세요.")

with open(PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

print(f"보내는 계정: {cfg.get('sender', '(미설정)')}")
pw = getpass.getpass("앱 비밀번호(입력해도 화면에 보이지 않습니다): ").strip()
pw = re.sub(r"\s+", "", pw)          # 구글이 4자씩 띄어서 보여주므로 공백은 지운다
if len(pw) != 16:
    raise SystemExit(f"앱 비밀번호는 16자리여야 합니다(입력값 {len(pw)}자리). 다시 실행하세요.")

cfg["app_password"] = pw
with open(PATH, "w", encoding="utf-8") as f:
    json.dump(cfg, f, ensure_ascii=False, indent=1)
os.chmod(PATH, 0o600)
print("저장했습니다. 이제 ./run_weekly_report.sh 로 시험 발송할 수 있습니다.")
