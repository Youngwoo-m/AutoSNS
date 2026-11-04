"""관리 웹의 채널 구현 현황을 계산하는 순수 manifest.

인증 기록·대상 ID 기록은 현재 로그인이나 API 권한의 성공 증거가 아니다. 이 manifest는
기본 비활성인 관리 발행 서버의 구현 범위만 표시하며 원본 launchd 자동 작업의 실행
상태를 대변하지 않는다. registry와 공식 계약 snapshot 외에 파일·DB·vault·API를 읽지 않는다.
"""
from collections.abc import Mapping
from .content_store import StoreError
from .models import Registry,Connection
from .oauth_catalog import provider_catalog

_PLATFORMS=('naver_blog','blogger','tistory','youtube','instagram','threads','x','facebook','tiktok')
_LABELS={'naver_blog':'네이버 블로그','blogger':'Blogger','tistory':'Tistory','youtube':'YouTube',
         'instagram':'Instagram','threads':'Threads','x':'X','facebook':'Facebook','tiktok':'TikTok'}
_AUTH_STATUSES=frozenset(('connected','unknown','not_checked','needs_auth','reauth_required',
                         'disconnected','revoked','expired','error'))
_PUBLISHERS={'naver_blog':'browser_implemented','blogger':'implemented','tistory':'browser_implemented',
             'youtube':'implemented','instagram':'implemented','threads':'text_only_implemented','facebook':'text_only_implemented','x':'text_only_implemented','tiktok':'local_preparation_only'}
_VERIFIERS={'naver_blog':'hash_implemented','blogger':'hash_implemented','tistory':'hash_implemented',
            'youtube':'receipt_implemented','instagram':'public_probe_required','threads':'public_probe_required','facebook':'public_probe_required','x':'public_probe_required'}
_ACTIONS={
 'naver_blog':('네이버 OAuth는 회원 프로필 확인용입니다. 블로그 게시에는 기존 브라우저 로그인 연결이 필요합니다.',),
 'blogger':('Blogger 연결의 실제 게시·공개 확인 시험이 남아 있습니다.',),
 'tistory':('공식 API가 종료되어 기존 브라우저 로그인 방식으로 연결해야 합니다.',),
 'youtube':('계정별 로그인 연결과 실제 업로드·공개 확인·성과 수집 시험이 남아 있습니다.',),
 'instagram':('이미지·REELS·캐러셀 준비, 수동 검토와 원본 전달 영수증 결속 기반은 개발됐습니다.',
              '만료·전달 중지와 HTTPS 통신 경계는 개발됐으며 공개 도메인 연결과 실제 계정 시험이 남아 있습니다.',
              '실제 프로페셔널 계정·권한 확인, 공개 호스팅·익명 공개 확인(probe), 실제 전송과 서버 기동 연결은 미수락 상태입니다.',
              'Instagram Login 방식과 직접 업로드는 후속 개발 범위입니다.'),
 'threads':('텍스트 게시 기반은 개발됐으며, 실제 게시 연결과 공개 페이지 확인은 개발·검증이 남아 있습니다.',),
 'x':('API 이용 비용을 확인해야 합니다. 추가 결제 없이 사용할 연결 방식을 검토 중입니다.',
      '텍스트 게시·중복 방지·공개 검증 기반은 개발됐으며 실제 계정·비용 허가·익명 공개 확인 시험이 남아 있습니다.',
      '이미지·영상 게시와 성과 수집은 후속 개발 범위입니다.'),
 'facebook':('Facebook 페이지를 명시 선택하고 로그인 주체와 페이지 자격·관리 권한(tasks)을 확인해야 합니다.',
             '텍스트 게시 기반은 개발됐으며, 실제 서버 전송·로그인 연결과 익명 공개 페이지 확인은 아직 등록·검증되지 않았습니다.'),
 'tiktok':('영상·캡션 로컬 준비와 명시 기술 검사를 사용할 수 있습니다. 업로드·게시는 실행하지 않습니다.',
           '본인·팀 계정용 내부 도구는 공식 Direct Post 적합 사례가 아니므로 자동 공개 게시 가능성을 전제하지 않습니다.',
           '최종 게시 방식은 확인 대기이며, 기존 중지 대기열은 그대로 유지합니다.'),
}


def _invalid():raise StoreError('invalid')


def _actions(platform,connection,providers):
    actions=[]
    if connection is None:
        actions.append('이 계정의 채널 연결을 등록하세요.')
    elif connection.target_status=='unverified':
        actions.append('게시 대상 ID를 확인하세요.')
    else:
        actions.append('저장된 대상 ID와 현재 계정의 일치 여부를 서버에서 다시 확인하세요.')
    if platform in providers and platform not in ('naver_blog','tistory'):
        actions.append('새 OAuth 연결을 사용할 경우 공식 앱 등록·HTTPS 복귀 주소·필요한 권한을 확인하세요.')
    actions.extend(_ACTIONS.get(platform,('이 채널의 게시·공개 확인·성과 수집 연결은 개발이 남아 있습니다.',)))
    actions.append('실제 운영을 켜기 전에 게시·공개 확인 시험이 남아 있습니다.')
    actions.append('원본 자동 작업 상태는 기존 자동 작업 화면에서 따로 확인하세요.')
    return actions


def _row(account,platform,connection,providers):
    auth=connection.auth_status if connection is not None and connection.auth_status in _AUTH_STATUSES else 'unknown'
    label=connection.target_label if connection is not None and connection.target_label.strip() else _LABELS.get(platform,platform)
    return dict(account_id=account,platform=platform,connection_id=connection.id if connection is not None else None,
        label=label,planning_enabled=connection.planning_enabled if connection is not None else False,
        target_status=connection.target_status if connection is not None else 'no_connection',
        authentication_status=auth if connection is not None else 'no_connection',
        publisher_status=_PUBLISHERS.get(platform,'not_implemented'),
        verification_status=_VERIFIERS.get(platform,'not_implemented'),
        metrics_status='implemented' if platform=='youtube' else 'stored_only',live_enabled=False,
        next_actions=_actions(platform,connection,providers))


def build_channel_readiness(registry,account='all',*,services=None):
    """계정별 채널 구현 현황. 등록되지 않은 계정/채널 조합에는 가짜 ID를 만들지 않는다.

    services는 향후 명시 서버 능력 모델을 위한 예약 인수다. 현재는 None/빈 mapping만
    허용한다. 임의 enabled/capabilities 값으로 인증이나 실발행 상태를 합성하지 않는다.
    """
    if not isinstance(registry,Registry) or type(account) is not str or account not in ('all','personal','dept'):_invalid()
    if services is not None and (not isinstance(services,Mapping) or services):_invalid()
    accounts=[key for key in ('personal','dept') if key in registry.accounts] if account=='all' else [account]
    if account!='all' and account not in registry.accounts:_invalid()
    providers={provider.platform for provider in provider_catalog()}
    channels=[]
    for owner in accounts:
        grouped={platform:[] for platform in _PLATFORMS}
        for identifier,connection in registry.connections.items():
            if not isinstance(connection,Connection) or connection.id!=identifier:_invalid()
            if connection.account_id!=owner:continue
            grouped.setdefault(connection.platform,[]).append(connection)
        for platform,connections in grouped.items():
            if connections:
                channels.extend(_row(owner,platform,connection,providers) for connection in connections)
            else:
                channels.append(_row(owner,platform,None,providers))
    return dict(account_id=account,channels=channels)
