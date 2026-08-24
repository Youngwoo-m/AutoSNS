"""이미 올라간 유튜브 영상의 공개 범위를 바꾼다(예: 공개→비공개).

업로드 전용 토큰(token.json, scope=youtube.upload)으로는 수정이 안 되므로,
관리 권한(youtube.force-ssl)으로 별도 토큰(token_manage.json)을 1회 발급받아 사용한다.
기존 status 를 읽어 privacyStatus 만 바꿔 업데이트한다(다른 설정 보존).

사용법:
  .venv\\Scripts\\python set_video_privacy.py <VIDEO_ID> [private|unlisted|public]
  예) .venv\\Scripts\\python set_video_privacy.py A_8jag8laeA private
"""
import os
import sys

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from common import BASE_DIR, CLIENT_SECRET_PATH, log

MANAGE_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
MANAGE_TOKEN = os.path.join(BASE_DIR, "token_manage.json")


def _creds():
    creds = None
    if os.path.exists(MANAGE_TOKEN):
        creds = Credentials.from_authorized_user_file(MANAGE_TOKEN, MANAGE_SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET_PATH):
                raise SystemExit("client_secret.json 이 필요합니다.")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, MANAGE_SCOPES)
            creds = flow.run_local_server(port=0, prompt="consent")
        with open(MANAGE_TOKEN, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds


def set_privacy(video_id, privacy="private"):
    yt = build("youtube", "v3", credentials=_creds(), cache_discovery=False)
    # 기존 status 읽기(다른 설정 보존)
    resp = yt.videos().list(part="status,snippet", id=video_id).execute()
    items = resp.get("items", [])
    if not items:
        raise SystemExit(f"영상을 찾을 수 없습니다: {video_id} (본인 계정 소유 영상인지 확인)")
    status = items[0]["status"]
    old = status.get("privacyStatus")
    status["privacyStatus"] = privacy
    body = {"id": video_id, "status": status}
    yt.videos().update(part="status", body=body).execute()
    log(f"공개범위 변경 완료: {video_id}  {old} → {privacy}")
    return {"video_id": video_id, "from": old, "to": privacy}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("사용법: python set_video_privacy.py <VIDEO_ID> [private|unlisted|public]")
    vid = sys.argv[1]
    priv = sys.argv[2] if len(sys.argv) > 2 else "private"
    print(set_privacy(vid, priv))
