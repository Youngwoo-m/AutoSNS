"""명시 외부 HTTPS 출처 정책. 생성·검사는 DNS나 네트워크를 사용하지 않는다."""
from collections.abc import Mapping
from dataclasses import dataclass
import ipaddress
import re


_LABEL = re.compile(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z')
_COOKIE_NAME = re.compile(r'[!#$%&\'*+.^_`|~0-9A-Za-z-]+\Z')
_RESERVED = frozenset(('localhost', 'local', 'internal', 'test', 'invalid', 'example', 'onion'))


def _invalid():
    raise ValueError('외부 접속 정책이 올바르지 않습니다')


@dataclass(frozen=True)
class ExternalAccessPolicy:
    public_origin: str

    def __post_init__(self):
        origin = self.public_origin
        if (type(origin) is not str or not origin.startswith('https://')
                or not origin.isascii() or any(ord(c) <= 32 or ord(c) == 127 for c in origin)):
            _invalid()
        host = origin[len('https://'):]
        if (not host or len(host) > 253 or host != host.lower() or '.' not in host
                or any(not _LABEL.fullmatch(label) for label in host.split('.'))
                or host.rsplit('.', 1)[-1] in _RESERVED or host.rsplit('.', 1)[-1].isdigit()):
            _invalid()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            return
        _invalid()

    @property
    def host(self):
        return self.public_origin[len('https://'):]

    @property
    def origin(self):
        return self.public_origin

    @property
    def allow_internal_key(self):
        return False

    def accepts_host(self, host):
        return type(host) is str and host == self.host

    def accepts_origin(self, origin):
        return origin is None or type(origin) is str and origin == self.origin

    def cookie(self, value):
        """인증 backend의 값을 보존하며 외부 전달에 Secure만 추가한다."""
        if (type(value) is not str or not value or not value.isascii()
                or any(ord(c) < 32 or ord(c) == 127 for c in value)):
            _invalid()
        parts = value.split(';')
        name, separator, token = parts[0].partition('=')
        if not separator or not _COOKIE_NAME.fullmatch(name) or any(c in token for c in ',"\\ '):
            _invalid()
        seen = set()
        for raw in parts[1:]:
            attribute, separator, parameter = raw.strip().partition('=')
            attribute = attribute.lower()
            if attribute in seen or attribute not in ('path', 'httponly', 'samesite', 'max-age', 'secure'):
                _invalid()
            seen.add(attribute)
            if attribute in ('httponly', 'secure'):
                if separator:
                    _invalid()
            elif attribute == 'path':
                if parameter != '/':
                    _invalid()
            elif attribute == 'samesite':
                if parameter != 'Strict':
                    _invalid()
            elif not separator or re.fullmatch(r'[0-9]+', parameter) is None:
                _invalid()
        if not {'path', 'httponly', 'samesite', 'max-age'} <= seen:
            _invalid()
        return value if 'secure' in seen else value + '; Secure'

    def public(self):
        return dict(origin=self.origin, enabled=True)

    @classmethod
    def from_mapping(cls, value):
        if not isinstance(value, Mapping) or set(value) != {'public_origin'}:
            _invalid()
        return cls(value['public_origin'])
