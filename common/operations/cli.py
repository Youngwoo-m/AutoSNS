"""명시 주입한 서버 서비스만 사용하는 제한된 실행 CLI."""
import argparse
import json
from collections.abc import Mapping
from .models import ContractError
from .content_store import StoreError

_PUBLIC_FIELDS = frozenset({
    'id', 'run_id', 'binding_id', 'base_job_id', 'execution_job_id', 'job_id',
    'content_id', 'content_revision', 'manifest_hash', 'delivery_id', 'state',
    'enabled', 'execution_enabled', 'route', 'version', 'error', 'reason_code',
    'runs', 'deliveries', 'scheduled_at_utc', 'phase', 'mode', 'source', 'request_kind',
})


def _public_result(value):
    if isinstance(value, Mapping):
        return {key: _public_result(item) for key, item in value.items() if key in _PUBLIC_FIELDS}
    if isinstance(value, (tuple, list)):
        return [_public_result(item) for item in value]
    if value is None or type(value) in (str, bool, int, float):
        return value
    return None


def _positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError('양의 정수가 필요합니다')
    return number


def _nonnegative(value):
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError('0 이상의 정수가 필요합니다')
    return number


def _parser():
    parser = argparse.ArgumentParser(prog='autosns-operations', allow_abbrev=False)
    commands = parser.add_subparsers(dest='command', required=True)
    submit = commands.add_parser('submit', allow_abbrev=False)
    submit.add_argument('--job', required=True)
    submit.add_argument('--scheduled-at', required=True)
    submit.add_argument('--phase', choices=('prepare', 'submit', 'verify'), required=True)
    submit.add_argument('--source', choices=('launchd', 'console'), required=True)
    submit.add_argument('--request-kind', choices=('new_publication', 'resume'), default='new_publication')
    submit.add_argument('--mode', choices=('dry', 'shadow', 'live'), default='dry')
    submit.add_argument('--content')
    submit.add_argument('--revision', type=_positive)
    worker = commands.add_parser('worker', allow_abbrev=False)
    worker.add_argument('--once', action='store_true', required=True)
    commands.add_parser('status', allow_abbrev=False)
    reconcile = commands.add_parser('reconcile', allow_abbrev=False)
    reconcile.add_argument('--delivery', required=True)
    reconcile.add_argument('--expected-version', type=_nonnegative, required=True)
    reconcile.add_argument('--request-key', required=True)
    guard = commands.add_parser('guard-legacy', allow_abbrev=False)
    guard.add_argument('--caller', required=True)
    guard.add_argument('--job', required=True)
    return parser


def _service(services, name):
    value = services.get(name) if isinstance(services, Mapping) else getattr(services, name, None)
    if value is None:
        raise StoreError('services_unavailable')
    return value


def main(argv: list[str] | None = None, *, services=None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(argv)
        if args.command == 'submit':
            if args.phase == 'prepare' and (not args.content or args.revision is None):
                parser.error('prepare에는 --content와 --revision이 필요합니다')
            if args.phase != 'prepare' and (args.content is not None or args.revision is not None):
                parser.error('--content와 --revision은 prepare에서만 허용됩니다')
        if services is None:
            if args.command == 'status':
                result = {'enabled': False, 'state': 'unconfigured'}
            else:
                raise StoreError('services_unavailable')
        elif args.command == 'submit':
            callers = _service(services, 'caller_ids')
            if not isinstance(callers, Mapping) or not isinstance(callers.get(args.source), str) or not callers[args.source]:
                raise StoreError('unknown_caller')
            request = dict(job_id=args.job, scheduled_at_utc=args.scheduled_at, phase=args.phase,
                           source=args.source, request_kind=args.request_kind, mode=args.mode)
            result = _service(services, 'submit')(request, callers[args.source],
                content_id=args.content, expected_revision=args.revision)
        elif args.command == 'worker':
            result = _service(services, 'worker_once')()
        elif args.command == 'status':
            result = _service(services, 'status')()
        elif args.command == 'reconcile':
            result = _service(services, 'reconcile')(args.delivery,
                expected_version=args.expected_version, request_key=args.request_key)
        else:
            result = _service(services, 'guard_legacy')(args.caller, args.job)
            if not isinstance(result, dict) or result.get('route') != 'legacy':
                raise StoreError('legacy_not_allowed')
        # 서비스 응답의 허용된 공개 결과만 CLI에 기록한다. permit/token은 받지 않는다.
        print(json.dumps(_public_result(result), ensure_ascii=False))
        return 0
    except SystemExit as error:
        return int(error.code)
    except (StoreError, ContractError) as error:
        print(json.dumps({'error': error.code}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
