"""가짜 관측 결과 검증. 원격 서비스나 브라우저를 호출하지 않는다."""
from .models import ContractError, ExecutionContext


def validate_observed_target(ctx: ExecutionContext, observed: dict) -> None:
    if not ctx.target_id:
        raise ContractError('target_unverified')
    if not isinstance(observed, dict) or not all(key in observed for key in
        ('platform', 'target_id', 'authenticated', 'login_subject', 'verification_method')):
        raise ContractError('invalid_observation')
    if observed['platform'] != ctx.platform or observed['target_id'] != ctx.target_id:
        raise ContractError('target_mismatch')
    if observed['authenticated'] is not True:
        raise ContractError('authentication_required')
    if not isinstance(observed['login_subject'], str) or not observed['login_subject']:
        raise ContractError('login_subject_mismatch')
    if ctx.expected_login_subject and observed['login_subject'] != ctx.expected_login_subject:
        raise ContractError('login_subject_mismatch')
    if not isinstance(observed['verification_method'], str) or not observed['verification_method']:
        raise ContractError('invalid_observation')
