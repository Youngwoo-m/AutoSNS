"""Explicit recovery only: preserve legacy/history/unknown refs; never enumerate a vault.

Callers explicitly inject an owned backend. Import and construction perform no
initialization, migration, cleanup or native I/O. Reports describe this journal
inspection, not exhaustive orphan reclamation or real Keychain acceptance.
"""
from collections import Counter
from dataclasses import dataclass

from .content_store import ConflictError, StoreError
from .credential_backend import CredentialError
from .oauth_stage_models import OwnedCredentialRef
from .oauth_workspace import oauth_write_guard, validate_workspace_context


_REASONS = frozenset({'candidate', 'deleted', 'absent', 'referenced', 'pending', 'unknown',
    'manual_review', 'denied', 'locked', 'unavailable', 'integrity_failed', 'graph_blocked',
    'revision_conflict', 'owner_mismatch', 'backend_required', 'invalid_arguments', 'workspace_busy'})
_FAULTS = {'credential_not_found': 'absent', 'credential_denied': 'denied',
    'credential_locked': 'locked', 'credential_unavailable': 'unavailable',
    'credential_ownership_unproven': 'integrity_failed', 'credential_owner_mismatch': 'integrity_failed',
    'credential_invalid_ref': 'integrity_failed'}


@dataclass(frozen=True)
class RecoveryReport:
    mode: str
    status: str
    journal_revision: int | None = None
    graph_revision: int | None = None
    stage_count: int = 0
    candidate_count: int = 0
    deleted_count: int = 0
    absent_count: int = 0
    preserved_count: int = 0
    already_deleted_count: int = 0
    legacy_protected_count: int = 0
    reason_counts: tuple = ()

    def __post_init__(self):
        if self.mode not in ('inspect', 'cleanup') or self.status not in ('inspected', 'cleaned', 'blocked', 'partial'):
            raise ValueError('invalid_recovery_report')
        for name in ('journal_revision', 'graph_revision', 'stage_count', 'candidate_count',
                     'deleted_count', 'absent_count', 'preserved_count', 'already_deleted_count', 'legacy_protected_count'):
            value = getattr(self, name)
            if value is None and name in ('journal_revision', 'graph_revision'):
                continue
            if type(value) is not int or value < 0:
                raise ValueError('invalid_recovery_report')
        if (type(self.reason_counts) is not tuple or any(type(pair) is not tuple or len(pair) != 2
                or pair[0] not in _REASONS or type(pair[1]) is not int or pair[1] < 0 for pair in self.reason_counts)):
            raise ValueError('invalid_recovery_report')

    def to_dict(self):
        return dict(mode=self.mode, status=self.status, journal_revision=self.journal_revision,
            graph_revision=self.graph_revision, stage_count=self.stage_count, candidate_count=self.candidate_count,
            deleted_count=self.deleted_count, absent_count=self.absent_count, preserved_count=self.preserved_count,
            already_deleted_count=self.already_deleted_count, legacy_protected_count=self.legacy_protected_count,
            reason_counts=dict(self.reason_counts))


class _Abort(Exception):
    def __init__(self, reason):
        self.reason = reason


class _Result:
    def __init__(self, mode):
        self.mode = mode; self.snapshot = None; self.stage_count = 0
        self.candidates = self.deleted = self.absent = self.already_deleted = 0
        self.finalized = 0; self.attempted = False; self.fault = False
        self.reasons = Counter()

    def report(self, status):
        snap = self.snapshot
        return RecoveryReport(self.mode, status,
            snap.journal_revision if snap else None, snap.graph_revision if snap else None,
            self.stage_count, self.candidates, self.deleted, self.absent,
            self.stage_count - self.already_deleted - self.finalized, self.already_deleted,
            len(snap.legacy_protected) if snap else 0, tuple(sorted(self.reasons.items())))


def _snapshot(context, journal, result):
    snap = journal.recovery_snapshot(context.owner)
    result.snapshot = snap
    if snap.blockers:
        raise _Abort('graph_blocked')
    return snap


def _validate_inputs(context, journal, owned_backend, expected_workspace_id):
    current = validate_workspace_context(context)
    if type(expected_workspace_id) is not str or expected_workspace_id != current.owner.workspace_id:
        raise _Abort('owner_mismatch')
    if owned_backend is None:
        raise _Abort('backend_required')
    for other in (journal.context, owned_backend.context):
        checked = validate_workspace_context(other)
        if checked.root != current.root or checked.owner != current.owner:
            raise _Abort('owner_mismatch')
    if journal.root.resolve() != current.root:
        raise _Abort('owner_mismatch')


def _eligibility(stage, snap, owner):
    ref = stage.owned_ref
    if (type(ref) is not OwnedCredentialRef or ref.stage_id != stage.stage_id
            or (ref.workspace_id, ref.root_binding) != (owner.workspace_id, owner.root_binding)):
        raise _Abort('owner_mismatch')
    if stage.state == 'deleted':
        return 'deleted'
    op = snap.operations.get(stage.operation_id)
    if op is None:
        raise _Abort('graph_blocked')
    if op.outcome == 'unknown' or op.remote_state in ('in_flight', 'unknown'):
        return 'unknown'
    if op.outcome == 'pending' or stage.operation_id in snap.pending_receipts:
        return 'pending'
    if stage.state == 'referenced' or ref in snap.protected_refs or op.outcome == 'referenced':
        return 'referenced'
    if (stage.state in ('intent', 'stored', 'preserved') and op.outcome == 'unused'
            and op.remote_state in ('local_only', 'not_started', 'returned')):
        return 'candidate'
    return 'manual_review'


def _current_candidate(context, journal, result, previous, stage, *, unchanged=False):
    fresh = _snapshot(context, journal, result)
    if unchanged and (fresh.journal_revision, fresh.graph_revision) != (previous.journal_revision, previous.graph_revision):
        raise _Abort('revision_conflict')
    current = next((item for item in fresh.stages if item.stage_id == stage.stage_id), None)
    if current != stage or _eligibility(current, fresh, context.owner) != 'candidate':
        raise _Abort('revision_conflict')
    return fresh


def _backend_reason(error):
    return _FAULTS.get(error.code, 'unavailable') if isinstance(error, CredentialError) else 'unavailable'


def _record_event(context, journal, result, snap, stage, code):
    journal.record_recovery_event(stage.stage_id, stage.revision, code)
    fresh = _current_candidate(context, journal, result, snap, stage)
    # Recovery events change only journal revision. A repeated event inserts
    # nothing. Any graph change invalidates this pass before native deletion.
    delta = (fresh.journal_revision - snap.journal_revision, fresh.graph_revision - snap.graph_revision)
    if delta not in ((0, 0), (1, 0)):
        raise _Abort('revision_conflict')
    return fresh


def _recover(mode, context, journal, owned_backend, expected_workspace_id, expected_journal_revision=None,
             expected_graph_revision=None):
    result = _Result(mode)
    try:
        with oauth_write_guard(context):
            _validate_inputs(context, journal, owned_backend, expected_workspace_id)
            snap = _snapshot(context, journal, result)
            if mode == 'cleanup' and (type(expected_journal_revision) is not int or expected_journal_revision < 0
                    or type(expected_graph_revision) is not int or expected_graph_revision < 0
                    or (expected_journal_revision, expected_graph_revision) != (snap.journal_revision, snap.graph_revision)):
                raise _Abort('revision_conflict')
            result.stage_count = len(snap.stages)
            # Classify the whole snapshot before any candidate vault reads.
            candidates = []
            for stage in snap.stages:
                reason = _eligibility(stage, snap, context.owner)
                if reason == 'candidate':
                    candidates.append(stage)
                elif reason == 'deleted':
                    result.already_deleted += 1
                else:
                    result.reasons[reason] += 1
            for stage in candidates:
                snap = _current_candidate(context, journal, result, snap, stage, unchanged=True)
                result.candidates += 1; result.attempted = True
                reason = 'candidate'
                try:
                    owned_backend.read_owned(stage.owned_ref)
                except Exception as error:
                    reason = _backend_reason(error)
                # No transaction stays open across native work. A changed graph,
                # including an unrelated change, invalidates this observation.
                snap = _current_candidate(context, journal, result, snap, stage, unchanged=True)
                if mode == 'inspect':
                    result.reasons[reason] += 1
                    if reason == 'absent':
                        result.absent += 1
                    continue
                if reason not in ('candidate', 'absent'):
                    snap = _record_event(context, journal, result, snap, stage, reason)
                    result.reasons[reason] += 1; result.fault = True
                    continue
                snap = _record_event(context, journal, result, snap, stage, 'delete_intent')
                if reason != 'absent':
                    try:
                        owned_backend.delete_owned(stage.owned_ref)
                        reason = 'deleted'
                    except Exception as error:
                        reason = _backend_reason(error)
                # Full snapshot revalidation also precedes metadata completion.
                snap = _current_candidate(context, journal, result, snap, stage, unchanged=True)
                snap = _record_event(context, journal, result, snap, stage, reason)
                if reason in ('deleted', 'absent'):
                    journal.mark_deleted(stage.stage_id, stage.revision)
                    result.finalized += 1
                    if reason == 'deleted':
                        result.deleted += 1
                    else:
                        result.absent += 1
                else:
                    result.fault = True
                result.reasons[reason] += 1
                snap = _snapshot(context, journal, result)
            return result.report('inspected' if mode == 'inspect' else 'partial' if result.fault else 'cleaned')
    except _Abort as error:
        reason = error.reason
    except ConflictError:
        reason = 'revision_conflict'
    except (CredentialError, StoreError) as error:
        reason = ('workspace_busy' if error.code == 'oauth_workspace_busy' else
                  'owner_mismatch' if error.code in ('credential_owner_mismatch', 'oauth_workspace_invalid_context',
                                                     'oauth_workspace_invalid_marker', 'oauth_workspace_root_mismatch')
                  else 'unavailable')
    except Exception:
        reason = 'unavailable'
    result.reasons[reason] += 1
    return result.report('partial' if mode == 'cleanup' and result.attempted else 'blocked')


def inspect_recovery(context, journal, owned_backend, *, expected_workspace_id):
    """Explicit observation; DB/vault write/delete zero (guard lockfile allowed)."""
    return _recover('inspect', context, journal, owned_backend, expected_workspace_id)


def cleanup_recovery(context, journal, owned_backend, *, expected_workspace_id,
                     expected_journal_revision, expected_graph_revision):
    """Clean only proven, unused, unreferenced journal stages under one guard."""
    return _recover('cleanup', context, journal, owned_backend, expected_workspace_id,
                    expected_journal_revision, expected_graph_revision)


def main(argv=None, *, backend_factory=None, stdout=None):
    """Explicit local CLI. The trusted factory hook is for isolated tests only.

    Production has no backend unless --keychain is explicitly supplied; there
    is no in-memory fallback or dynamic module/environment backend loading.
    """
    import argparse
    import json
    import sys
    from .oauth_workspace import load_workspace_owner
    from .oauth_stage_store import OAuthStageStore

    class Parser(argparse.ArgumentParser):
        def error(self, message):
            raise _Abort('invalid_arguments')

    mode = 'inspect'
    try:
        parser = Parser(description='Explicit owned OAuth journal recovery', allow_abbrev=False)
        parser.add_argument('--workspace', required=True)
        parser.add_argument('--mode', required=True, choices=('inspect', 'cleanup'))
        parser.add_argument('--expected-workspace-id', required=True)
        parser.add_argument('--expected-journal-revision', type=int)
        parser.add_argument('--expected-graph-revision', type=int)
        parser.add_argument('--keychain', action='store_true')
        args = parser.parse_args(argv); mode = args.mode
        if mode == 'cleanup' and any(type(value) is not int or value < 0 for value in
                (args.expected_journal_revision, args.expected_graph_revision)):
            raise _Abort('invalid_arguments')
        if backend_factory is None and not args.keychain:
            raise _Abort('backend_required')
        context = load_workspace_owner(args.workspace)
        if args.expected_workspace_id != context.owner.workspace_id:
            raise _Abort('owner_mismatch')
        if backend_factory is None:
            # Public bridge construction is lazy; only explicit recovery calls
            # below may perform exact candidate native operations.
            from .keychain_backend import SecurityFrameworkBridge
            from .oauth_stage_backend import KeychainScopedRawBackend, OwnedStageBackend
            backend = OwnedStageBackend(context, KeychainScopedRawBackend(SecurityFrameworkBridge()))
        else:
            backend = backend_factory(context)
        journal = OAuthStageStore(context)
        if mode == 'inspect':
            report = inspect_recovery(context, journal, backend, expected_workspace_id=args.expected_workspace_id)
        else:
            report = cleanup_recovery(context, journal, backend, expected_workspace_id=args.expected_workspace_id,
                expected_journal_revision=args.expected_journal_revision, expected_graph_revision=args.expected_graph_revision)
    except _Abort as error:
        report = RecoveryReport(mode, 'blocked', reason_counts=((error.reason, 1),))
    except Exception:
        report = RecoveryReport(mode, 'blocked', reason_counts=(('unavailable', 1),))
    print(json.dumps(report.to_dict(), sort_keys=True, separators=(',', ':')), file=stdout or sys.stdout)
    return 0 if report.status in ('inspected', 'cleaned') else 2


if __name__ == '__main__':
    raise SystemExit(main())
