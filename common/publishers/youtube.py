"""학과/개인 YouTube adapter와 서버 고정 child launcher. 기본 등록 없음."""
from collections.abc import Mapping
from datetime import datetime, timezone
from common.operations.models import ContractError
from common.operations.runtime_models import PublicationContext, SubmissionResult, LookupResult, VerificationResult, utc
from .youtube_payloads import build_youtube_payload


class YoutubeAdapter:
    platform = 'youtube'

    def __init__(self, registry, bridge):
        self.registry, self.bridge = registry, bridge

    def _binding(self, ctx):
        from .youtube_runtime import YOUTUBE_BINDINGS
        connection = self.registry.connections.get(ctx.connection_id)
        executor = YOUTUBE_BINDINGS.get(ctx.connection_id)
        if (not executor or not connection or connection.platform != 'youtube' or ctx.platform != 'youtube' or
            connection.account_id != ctx.destination_account_id or connection.target_id != ctx.target_id or
            not ctx.target_id or ctx.registry_revision != self.registry.revision or
            connection.credential_ref != ctx.connection_id + '.credential'):
            raise ContractError('youtube_context_mismatch')
        return executor

    def inspect_target(self, ctx):
        return self.bridge.read(self._binding(ctx), 'inspect_target', ctx, {})

    def prepare(self, ctx, snapshot):
        if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
        self._binding(ctx)
        return build_youtube_payload(snapshot, ctx, ctx.options.get('youtube_config', {}))

    def submit(self, ctx, prepared, permit):
        if not isinstance(ctx,PublicationContext):raise ContractError('publication_context_required')
        executor = self._binding(ctx)
        for name in ('connection_id', 'target_id', 'platform', 'owner_account_id', 'destination_account_id', 'content_id', 'content_revision', 'manifest_hash'):
            if prepared.get(name) != getattr(ctx, name): raise ContractError('youtube_prepared_mismatch')
        try:
            raw = self.bridge.submit(executor, ctx, prepared, permit)
            if raw.get('outcome') not in ('submitted', 'scheduled', 'unknown', 'failed'):
                return SubmissionResult('unknown', evidence={'reason': 'invalid_youtube_result'})
            return SubmissionResult(raw['outcome'], remote_id=raw.get('remote_id'), url=raw.get('url'),
                                    scheduled_at=raw.get('scheduled_at'), evidence=raw.get('evidence', {}))
        except Exception:
            return SubmissionResult('unknown', evidence={'reason': 'youtube_submission_uncertain'})

    def lookup(self, ctx, attempt):
        executor = self._binding(ctx)
        if not isinstance(attempt, Mapping): return LookupResult('unsupported', evidence={'reason': 'attempt_required'})
        try:
            raw = self.bridge.read(executor, 'lookup', ctx, {'attempt': dict(attempt)})
            candidates = raw.get('candidates', [])
            if not isinstance(candidates, list): raise ValueError('invalid_youtube_observation')
            # ID나 제목만으로 strong match를 만들어 unknown을 해소하지 않는다.
            return LookupResult('unsupported', candidates, {'reason': 'media_evidence_required' if candidates else 'remote_absence_unproven'})
        except Exception:
            return LookupResult('error', evidence={'reason': 'youtube_lookup_error'})

    def verify(self, ctx, remote_id, snapshot):
        executor = self._binding(ctx)
        now = datetime.now(timezone.utc)
        try:
            # 승인 snapshot이 달라졌다면 관측을 해당 버전에 결속할 수 없다.
            build_youtube_payload(snapshot, ctx, ctx.options.get('youtube_config', {}))
            raw = self.bridge.read(executor, 'verify', ctx, {'remote_id': remote_id})
            checked = utc(raw['checked_at'])
            item = raw.get('observation')
            if not isinstance(item, Mapping): return VerificationResult('pending', checked, {'reason': 'remote_observation_unavailable'})
            if item.get('remote_id') != remote_id or item.get('target_id') != ctx.target_id:
                return VerificationResult('failed', checked, {'reason': 'remote_identity_mismatch'})
            evidence = dict(item, reason='media_evidence_required')
            if item.get('upload_status') in ('failed', 'rejected', 'deleted') or item.get('processing_status') in ('failed', 'terminated'):
                return VerificationResult('failed', checked, dict(evidence, reason='remote_processing_failed'))
            return VerificationResult('pending', checked, evidence)
        except Exception:
            return VerificationResult('error', now, {'reason': 'youtube_verification_error'})


def build_adapter(registry, bridge):
    return YoutubeAdapter(registry, bridge)


def bridge_bootstrap():
    from .youtube_runtime import bridge_bootstrap as bootstrap
    return bootstrap()


if __name__ == '__main__':
    from .bridge_host import main
    raise SystemExit(main(bootstrap=bridge_bootstrap, bootstrap_module=__spec__.name))
