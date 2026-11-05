"""기존 검증 쿠키의 단방향 결속과 서버 프로세스 전용 CSRF."""
import base64
import hashlib
import hmac
import re
import time

from common.operations.oauth_service import SessionContext


class OAuthSessionError(Exception):
    def __init__(self,status,code):self.status=status;self.code=code


def require_oauth_session(handler):
    token=handler._token()
    if not token or not handler.server.auth_backend.check(token):
        raise OAuthSessionError(403 if handler.headers.get('X-AX-Internal') else 401,'oauth_session_required')
    return SessionContext('console_user',hashlib.sha256(token.encode()).hexdigest())


def mint_csrf(session,key,*,now=None):
    now=int(time.time() if now is None else now);expires=now+600
    message=(session.session_binding+':'+str(expires)).encode()
    signature=base64.urlsafe_b64encode(hmac.digest(key,message,'sha256')).rstrip(b'=').decode()
    from datetime import datetime,timezone
    return dict(csrf_token=str(expires)+'.'+signature,
                expires_at=datetime.fromtimestamp(expires,timezone.utc).isoformat())


def verify_csrf(session,token,key,*,now=None):
    now=int(time.time() if now is None else now)
    if not isinstance(token,str) or len(token)>128:return False
    try:
        expiry,signature=token.split('.')
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}',signature):return False
        if not expiry.isascii() or not expiry.isdecimal() or str(int(expiry))!=expiry:return False
        expiry=int(expiry)
    except (ValueError,OverflowError):return False
    if not now<expiry<=now+600:return False
    expected=base64.urlsafe_b64encode(hmac.digest(key,(session.session_binding+':'+str(expiry)).encode(),'sha256')).rstrip(b'=').decode()
    return hmac.compare_digest(expected,signature)
