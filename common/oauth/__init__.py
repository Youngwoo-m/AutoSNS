"""비활성 OAuth adapter. import는 외부 호출/자격 탐색을 하지 않는다."""
from .providers import OAuthProvider, build_providers
from .transport import OAuthTransport

__all__ = ['OAuthProvider', 'build_providers', 'OAuthTransport']
