"""비용 증거가 확인되지 않으면 외부 전송 전에 거부한다."""
from .content_store import StoreError
from .oauth_models import OAuthPolicy
from .oauth_catalog import provider_catalog

__all__ = ['OAuthPolicy', 'assert_zero_cost']


def assert_zero_cost(operation: str, endpoint: str | None, evidence_revision: str) -> None:
    """사용자 비용 주장이나 임의 endpoint를 받지 않고 현재 고정 증거와 대조한다.

    현재 공식 감사는 어떤 외부 OAuth operation도 비용 0으로 확인하지 않았다.
    live_enabled=True 역시 이 gate를 우회하지 않는다.
    """
    if not isinstance(operation, str) or not isinstance(endpoint, str) or not isinstance(evidence_revision, str):
        raise StoreError('oauth_contract_blocked')
    matches = [rule for provider in provider_catalog() for rule in provider.operations
               if rule.operation == operation and rule.endpoint == endpoint]
    if not matches:
        raise StoreError('oauth_contract_blocked')
    for rule in matches:
        if rule.contract_status != 'verified':
            raise StoreError('oauth_contract_blocked')
        if rule.evidence_revision != evidence_revision:
            raise StoreError('oauth_evidence_stale')
        if rule.cost_kind != 'no_additional_cost':
            raise StoreError('oauth_cost_blocked')
