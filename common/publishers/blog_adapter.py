"""다섯 고정 블로그 연결의 공통 adapter. 외부 I/O는 bridge에서만 실행한다."""
from collections.abc import Mapping
from datetime import datetime, timezone

from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext, SubmissionResult, LookupResult, VerificationResult, utc
from common.operations.verification import snapshot_fingerprints, strong_identity
from .blog_payloads import build_blog_payload


class BlogAdapter:
    def __init__(self, platform, registry, bridge):
        self.platform, self.registry, self.bridge = platform, registry, bridge

    def _binding(self, ctx):
        from .blog_runtime import BLOG_BINDINGS
        connection = self.registry.connections.get(ctx.connection_id)
        binding = BLOG_BINDINGS.get(ctx.connection_id)
        if (not binding or ctx.platform != self.platform or not connection or
            connection.platform != self.platform or connection.account_id != ctx.destination_account_id or
            connection.target_id != ctx.target_id or not ctx.target_id or
            ctx.registry_revision != self.registry.revision):
            raise ContractError('blog_context_mismatch')
        return binding['executor_id']

    def inspect_target(self, ctx):
        executor = self._binding(ctx)
        return self.bridge.read(executor, 'inspect_target', ctx, {})

    def prepare(self, ctx, snapshot: Mapping):
        if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
        self._binding(ctx)
        return build_blog_payload(self.platform, snapshot, ctx)

    def submit(self, ctx, prepared: Mapping, permit):
        if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
        executor = self._binding(ctx)
        for name in ('platform', 'target_id', 'connection_id', 'owner_account_id', 'destination_account_id'):
            if prepared.get(name) != getattr(ctx, name):
                raise ContractError('blog_prepared_mismatch')
        try:
            raw = self.bridge.submit(executor, ctx, prepared, permit)
        except Exception:
            # 관문/전송 오류를 '미발행'으로 단정하지 않는다. nonce·예외 원문도 내보내지 않는다.
            return SubmissionResult('unknown', evidence={'reason': 'blog_submission_uncertain'})
        outcome = raw.get('outcome')
        if outcome not in ('submitted', 'unknown', 'failed'):
            return SubmissionResult('unknown', evidence={'reason': 'invalid_blog_result'})
        return SubmissionResult(outcome, remote_id=raw.get('remote_id'), url=raw.get('url'),
                                evidence=raw.get('evidence', {}))

    def lookup(self, ctx, attempt):
        executor = self._binding(ctx)
        if not isinstance(attempt, Mapping):
            return LookupResult('unsupported', evidence={'reason': 'attempt_required'})
        try:
            raw = self.bridge.read(executor, 'lookup', ctx, {'attempt': dict(attempt)})
            candidates = raw.get('candidates', [])
            if not isinstance(candidates, list): raise ValueError()
            if raw.get('unsupported'):
                return LookupResult('unsupported', candidates, {'reason': 'remote_lookup_incomplete'})
            # 원격 ID가 있어도 본문·매체·시각의 강한 일치가 필요하다.
            content_store = getattr(getattr(self.bridge, 'store', None), 'content_store', None)
            if content_store is None:
                return LookupResult('unsupported', candidates, {'reason': 'approved_snapshot_unavailable'})
            snapshot = content_store.get(ctx.content_id, ctx.content_revision)
            now = raw['checked_at']
            prior_result = attempt.get('result')
            expected_id = attempt.get('remote_id') or (prior_result.get('remote_id') if isinstance(prior_result, Mapping) else None)
            matched = [item for item in candidates
                       if strong_identity(ctx.to_dict(), snapshot, item, attempt, now, remote_id=expected_id)]
            if len(matched) == 1 and len(candidates) == 1:
                return LookupResult('matched', matched)
            if candidates:
                insufficient = any(item.get('body_sha256') is None or item.get('media_sha256') is None for item in candidates)
                return LookupResult('unsupported' if insufficient else 'ambiguous', candidates)
            # 한정된 목록은 원격 부재를 증명하지 않는다.
            return LookupResult('unsupported', evidence={'reason': 'remote_absence_unproven'})
        except Exception:
            return LookupResult('error', evidence={'reason': 'blog_lookup_error'})

    def verify(self, ctx, remote_id, snapshot):
        executor = self._binding(ctx)
        now = datetime.now(timezone.utc)
        try:
            expected_body, expected_media = snapshot_fingerprints(ctx.to_dict(), snapshot)
            raw = self.bridge.read(executor, 'verify', ctx, {'remote_id': remote_id})
            checked = utc(raw['checked_at'])
            observation = raw.get('observation')
            if not isinstance(observation, Mapping):
                return VerificationResult('unsupported', checked, {'reason': 'remote_observation_unavailable'})
            evidence = dict(observation)
            if observation.get('remote_id') != remote_id or observation.get('target_id') != ctx.target_id:
                return VerificationResult('failed', checked, {'reason': 'remote_identity_mismatch'})
            if observation.get('body_sha256') is None or observation.get('media_sha256') is None:
                return VerificationResult('unsupported', checked, evidence)
            if observation['body_sha256'] != expected_body or observation['media_sha256'] != expected_media:
                return VerificationResult('failed', checked, evidence)
            if observation.get('visibility') != 'public':
                return VerificationResult('pending', checked, evidence)
            return VerificationResult('verified', checked, evidence)
        except Exception:
            return VerificationResult('error', now, {'reason': 'blog_verification_error'})
