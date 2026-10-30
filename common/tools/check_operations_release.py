"""서버 고정 기준선으로 증거를 읽기 전용 분류하는 CLI. 발행 권한이 아니다."""
import argparse
from collections.abc import Mapping
import json
from pathlib import Path

from common.operations.cutover import assess_cutover, ROOT
from common.operations.models import ContractError
from common.operations.registry import load_registry


def check_release(evidence: Mapping, *, mode: str = 'offline') -> dict:
    if mode not in ('offline', 'production'):
        return dict(offline_ready=False, production_ready=False,
                    blockers=['offline:invalid_mode'], evidence_refs={})
    try:
        registry = load_registry(ROOT / 'ax-console/config/operations.json')
        inventory = json.loads((ROOT / 'docs/runbooks/execution-entrypoint-inventory.json').read_text())
        # CLI에는 실제 원장 경로/실증거 권한을 전달하는 기능이 없다.
        results = [assess_cutover(None, job_id, evidence, registry=registry, inventory=inventory)
                   for job_id in registry.jobs]
        blockers = list(dict.fromkeys(item for result in results for item in result['blockers']))
        return dict(offline_ready=bool(results) and all(result['offline_ready'] for result in results),
                    production_ready=False, blockers=blockers,
                    evidence_refs=results[0]['evidence_refs'] if results else {})
    except (OSError, ValueError, TypeError, ContractError):
        return dict(offline_ready=False, production_ready=False,
                    blockers=['offline:server_baseline_unavailable'], evidence_refs={})


def main(argv=None):
    parser = argparse.ArgumentParser(description='운영 전환 증거의 읽기 전용 분류')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--mode', choices=('offline', 'production'), default='offline')
    args = parser.parse_args(argv)
    try:
        evidence = json.loads(args.evidence.read_text(encoding='utf-8'))
        result = check_release(evidence, mode=args.mode)
    except (OSError, ValueError, UnicodeError):
        result = dict(offline_ready=False, production_ready=False,
                      blockers=['offline:evidence_unreadable'], evidence_refs={})
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result['offline_ready' if args.mode == 'offline' else 'production_ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
