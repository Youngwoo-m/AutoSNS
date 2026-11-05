"""저장된 성과 projection을 보존하는 읽기 전용 기획 근거. 외부 검색·모델 없음."""
from copy import deepcopy
from .planning_context import build_planning_context


UNAVAILABLE_FIELDS = ('search_volume', 'competition', 'ctr', 'predicted_ctr', 'vidiq_score')


def build_research_preview(account_id: str, registry, metrics_store, content_store, *, runtime_store=None) -> dict:
    """대상·정의·기준·기간을 합치지 않는다. content_store에 쓰기/원고 생성 없음."""
    context = build_planning_context(account_id, registry, metrics_store, runtime_store=runtime_store)
    observations = {r['id']: r for r in context['observations']
                    if r['source_kind'] == 'verified_delivery' and r['status'] == 'ok'}
    groups, refs = [], []
    missing = deepcopy(context['missing'])
    for projected in context['destination_metrics']:
        if account_id != 'all' and projected['destination_account_id'] != account_id:
            continue
        ids = list(projected['observation_ids'])
        rows = [observations[i] for i in ids if i in observations]
        # 기존 projection이 검증한 합산 가능성만 사용하며 새 지표를 계산하지 않는다.
        supported = bool(projected['values']) and all(
            a['method'] != 'not_aggregated' for a in projected['aggregation'].values())
        eligible = len(rows) >= 3 and supported
        group = deepcopy(projected)
        group.update(owner_account_ids=sorted({r['owner_account_id'] for r in rows if r.get('owner_account_id')}),
                     sample_count=len(rows), recommendation_status='available' if eligible else 'unavailable',
                     recommendations=[])
        if eligible:
            group['recommendations'].append(dict(kind='review_stored_evidence',
                reason='동일 대상·정의·기준·기간의 검증 관측 3건 이상입니다. 내용별 인과·예측 순위는 산출하지 않습니다.',
                observation_ids=ids))
        else:
            missing.append(dict(observation_ids=ids, status='unavailable',
                                uncertainties=['sample_below_three'] if len(rows) < 3 else ['incompatible_metric_definition']))
        groups.append(group)
        for row in rows:
            # source 원문·credential·임의 URL을 복사하지 않고 불변 근거 식별자만 반환.
            source = row.get('source', {})
            ref = dict(observation_id=row['id'], owner_account_id=row.get('owner_account_id'),
                       destination_account_id=row['destination_account_id'],
                       content_id=row['content_id'], content_revision=source.get('content_revision'))
            if ref not in refs:
                refs.append(ref)
    return dict(groups=groups, missing=missing, evidence_refs=refs,
                unavailable_fields=list(UNAVAILABLE_FIELDS))
