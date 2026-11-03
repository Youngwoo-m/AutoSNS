"""InstagramServices에 주입할 명시적 미디어 전달 조립.

외부 DNS·TLS·발행을 설정하지 않는다. enabled=True는 비공개 저장소 초기화와
loopback 바인딩만 수행한다. 반환된 server의 실행과 종료는 호출자가 관리한다.
"""
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from common.operations.media_leases import MediaLeaseStore
from common.operations.media_lease_http import build_media_server
from common.operations.models import ContractError
from .instagram_media_leases import BoundInstagramMediaStager, InstagramLeaseAuthorityGuard
from .instagram_media_sources import InstagramMediaSourceFactory, _host


def _invalid():
    raise ContractError('instagram_lease_configuration_invalid') from None


class LeaseInstagramMediaFactory:
    """prepare 호출마다 현재 문맥을 새로 결속한다. 생성은 저장소를 열지 않는다.

    단독 사용 시 write_guard는 실행 허가·최종 검토·STOP을 모두 확인해야 한다.
    assemble_media_delivery는 이 세 검사를 직접 결합한다. 기본 guard는 거부다.
    """
    def __init__(self, media_loader, lease_store, *, public_host, clock, write_guard=None, ttl=timedelta(hours=1)):
        if (not callable(media_loader) or not callable(clock) or
                write_guard is not None and not callable(write_guard) or
                not isinstance(ttl, timedelta) or not timedelta(minutes=5) < ttl <= timedelta(hours=24)):
            _invalid()
        self._loader = media_loader
        self._store = lease_store
        self._host = _host(public_host)
        self._clock = clock
        self._guard = write_guard
        self._ttl = ttl

    def __repr__(self):
        return 'LeaseInstagramMediaFactory(<비공개>)'

    def prepare(self, ctx, prepared):
        stager = BoundInstagramMediaStager(ctx, prepared, self._store, public_host=self._host,
                                          clock=self._clock, write_guard=self._guard, ttl=self._ttl)
        factory = InstagramMediaSourceFactory(self._loader, stager=stager, approval_guard=self._guard,
                                              allowed_hosts=(self._host,), clock=self._clock)
        return factory.prepare(ctx, prepared)


@dataclass(frozen=True, repr=False)
class MediaDeliveryAssembly:
    store: object
    factory: LeaseInstagramMediaFactory
    authority: InstagramLeaseAuthorityGuard
    server: object = None

    def __repr__(self):
        return 'MediaDeliveryAssembly(<비공개>)'

    def close(self):
        """serve_forever를 먼저 종료한 뒤 호출한다. 스레드는 생성하지 않는다."""
        if self.server is not None:
            self.server.server_close()


def assemble_media_delivery(*, workspace_root, content_store, reviews, serving_allowed,
                            write_guard, public_host, clock, enabled=False, port=0,
                            server_factory=build_media_server):
    """관리 화면과 동일한 workspace_root/media-leases에 명시 조립한다.

    write_guard는 현재 실행 허가를 확인한다. reviews.authorize와 serving_allowed는
    매번 다시 확인하며, fetch에는 소모된 실행 허가를 요구하지 않는다.
    기본 설정은 파일·리스너·스레드를 만들지 않고 발급도 거부한다.
    """
    store = MediaLeaseStore(Path(workspace_root) / 'media-leases')
    loader = getattr(content_store, 'read_asset', None)
    review_guard = getattr(reviews, 'authorize', None)
    if enabled is not True:
        factory = LeaseInstagramMediaFactory(loader, store, public_host=public_host, clock=clock)
        return MediaDeliveryAssembly(store, factory, InstagramLeaseAuthorityGuard())
    if (not callable(write_guard) or not callable(review_guard) or not callable(serving_allowed) or
            not callable(server_factory) or type(port) is not int or not 0 <= port <= 65535):
        _invalid()

    def current_write(ctx, prepared):
        try:
            return (serving_allowed() is True and review_guard(ctx, prepared) is True and
                    write_guard(ctx, prepared) is True)
        except Exception:
            return False

    factory = LeaseInstagramMediaFactory(loader, store, public_host=public_host,
                                         clock=clock, write_guard=current_write)
    authority = InstagramLeaseAuthorityGuard(review_guard)
    store.initialize()
    try:
        server = server_factory(store, authority_guard=authority, serving_allowed=serving_allowed,
                                enabled=True, host='127.0.0.1', port=port,
                                expected_host=factory._host, clock=clock)
    except Exception:
        raise ContractError('instagram_lease_transport_unavailable') from None
    return MediaDeliveryAssembly(store, factory, authority, server)
