"""Google Web/Desktop 미확인 계약 및 project grant 영향은 계속 차단한다."""
from .providers import OAuthProvider


class GoogleProvider(OAuthProvider):
    """Web catalog를 Desktop/loopback 계약으로 대체하지 않는다. 원격 revoke 비활성."""
