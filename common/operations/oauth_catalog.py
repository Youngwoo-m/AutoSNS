"""공식 감사의 확인 범위만 담은 서버 소유 불변 목록. 비용 실행 증거는 전부 미확인."""
from .oauth_models import OperationRule, ProviderDefinition

CHECKED_AT = '2026-10-31T00:00:00+00:00'
EVIDENCE_REVISION = 'oauth-official-audits-2026-10-31-v1'


def _rules(known=(), *, unsupported=False):
    contracts = {op: (method, endpoint) for op, method, endpoint in known}
    result = []
    for operation in ('authorize', 'exchange', 'refresh', 'revoke', 'inspect'):
        method, endpoint = contracts.get(operation, ('GET' if operation in ('authorize', 'inspect') else 'POST', None))
        status = 'unsupported' if unsupported else ('verified' if endpoint else 'contract_blocked')
        result.append(OperationRule(operation, method, endpoint, status, 'unknown', EVIDENCE_REVISION, CHECKED_AT))
    return tuple(result)


def _provider(id, platform, method, read=(), publish=(), known=(), pkce='unconfirmed', reasons=(), unsupported=False):
    return ProviderDefinition(id, platform, method, _rules(known, unsupported=unsupported), read, publish,
                              pkce, 'registered_https_exact',
                              ('cost_evidence_unverified', 'app_registration_unverified', 'https_callback_unaccepted') + reasons)


# Endpoint가 없는 operation은 계약 미확인이다. 다른 login의 URL을 대입하지 않는다.
_CATALOG = (
    _provider('instagram_login', 'instagram', 'instagram_login',
              ('instagram_business_basic',), ('instagram_business_content_publish',),
              reasons=('professional_account_required', 'endpoint_scope_contract_unverified')),
    _provider('instagram_facebook', 'instagram', 'facebook_login',
              ('pages_show_list', 'instagram_basic', 'pages_read_engagement'), ('instagram_content_publish',),
              reasons=('professional_account_and_page_required', 'endpoint_scope_contract_unverified')),
    _provider('threads', 'threads', 'threads_login', ('threads_basic',), ('threads_content_publish',),
              (('exchange', 'POST', 'https://graph.threads.net/oauth/access_token'),
               ('refresh', 'GET', 'https://graph.threads.net/refresh_access_token')),
              reasons=('independent_threads_app_required', 'refresh_timing_unverified')),
    _provider('facebook_pages', 'facebook', 'facebook_pages',
              ('pages_show_list', 'pages_read_engagement'), ('pages_manage_posts',),
              reasons=('pages_only', 'page_tasks_unverified', 'endpoint_scope_contract_unverified')),
    _provider('x', 'x', 'oauth2_pkce', ('tweet.read', 'users.read'), ('tweet.write',),
              (('refresh', 'POST', 'https://api.x.com/2/oauth2/token'),), pkce='s256',
              reasons=('paid_gate_unverified', 'offline_access_separate_consent')),
    _provider('tiktok', 'tiktok', 'tiktok_login', ('user.info.basic',), ('video.upload', 'video.publish'),
              (('exchange', 'POST', 'https://open.tiktokapis.com/v2/oauth/token/'),
               ('refresh', 'POST', 'https://open.tiktokapis.com/v2/oauth/token/')),
              reasons=('display_read_only', 'inbox_upload_distinct_from_direct_post',
                       'internal_utility_intended_use_unresolved', 'app_review_unverified', 'direct_post_audit_and_creator_ux_unverified')),
    _provider('youtube', 'youtube', 'google_web', ('https://www.googleapis.com/auth/youtube.readonly',),
              ('https://www.googleapis.com/auth/youtube.upload',),
              reasons=('desktop_client_separate_contract', 'web_pkce_unconfirmed', 'project_quota_billing_unverified',
                       'testing_token_expiry_unverified', 'remote_revoke_project_impact_unverified', 'channel_id_confirmation_required')),
    _provider('blogger', 'blogger', 'google_web', ('https://www.googleapis.com/auth/blogger.readonly',),
              ('https://www.googleapis.com/auth/blogger',),
              reasons=('desktop_client_separate_contract', 'web_pkce_unconfirmed', 'project_quota_billing_unverified',
                       'testing_token_expiry_unverified', 'remote_revoke_project_impact_unverified', 'blog_id_confirmation_required')),
    _provider('naver', 'naver_blog', 'naver_profile', known=(
        ('authorize', 'GET', 'https://nid.naver.com/oauth2.0/authorize'),
        ('exchange', 'POST', 'https://nid.naver.com/oauth2.0/token'),
        ('refresh', 'POST', 'https://nid.naver.com/oauth2.0/token'),
        ('revoke', 'POST', 'https://nid.naver.com/oauth2.0/revoke'),
        ('inspect', 'GET', 'https://openapi.naver.com/v1/nid/me')),
        reasons=('profile_only', 'blog_publication_unsupported', 'paired_token_revocation')),
    _provider('tistory', 'tistory', 'unsupported', unsupported=True,
              reasons=('official_api_discontinued', 'browser_session_separate_policy')),
)


def provider_catalog() -> tuple[ProviderDefinition, ...]:
    """로컬 snapshot만 반환한다. 등록부·자격·네트워크를 읽지 않는다."""
    return _CATALOG
