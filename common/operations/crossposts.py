"""교차 경로 관측 및 순수 시각 계산. 기존 실행기를 불러오지 않는다."""
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from collections.abc import Mapping
from .models import ContractError, thaw


def _date(value):
    try:
        result=datetime.fromisoformat(value) if isinstance(value,str) else value
        if not isinstance(result,datetime) or result.tzinfo is None or result.utcoffset() is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except (ValueError,TypeError):
        raise ContractError('invalid_crosspost_time') from None


def earliest_post_time(rule, source_public_at, last_destination_post_at=None):
    """원본 시각 기준 지연은 한 번만 더한다. source 소유는 이미 지연된 입력이다."""
    source=_date(source_public_at)
    delay=rule.get('delay_seconds',0); gap=rule.get('min_gap_seconds',0)
    if any(type(value) is not int or value<0 for value in (delay,gap)):
        raise ContractError('invalid_crosspost_rule')
    owner=rule.get('delay_owner','managed')
    if owner not in ('managed','legacy_queue_add','queue_add','source','none'):
        raise ContractError('invalid_delay_owner')
    candidate=source+timedelta(seconds=delay if owner in ('managed','legacy_queue_add','queue_add') else 0)
    if last_destination_post_at is not None:
        candidate=max(candidate,_date(last_destination_post_at)+timedelta(seconds=gap))
    window=rule.get('window')
    if window:
        try:
            zone=ZoneInfo(window.get('timezone','Asia/Seoul'))
            start=time.fromisoformat(window['start']); end=time.fromisoformat(window['end'])
            if start.tzinfo or end.tzinfo or start==end: raise ValueError()
            local=candidate.astimezone(zone); clock=local.time().replace(tzinfo=None)
            if start<end:
                if clock<start: local=datetime.combine(local.date(),start,zone)
                elif clock>=end: local=datetime.combine(local.date()+timedelta(days=1),start,zone)
            elif end<=clock<start:
                local=datetime.combine(local.date(),start,zone)
            candidate=local.astimezone(timezone.utc)
        except (ValueError,TypeError,KeyError,ZoneInfoNotFoundError):
            raise ContractError('invalid_crosspost_window') from None
    return candidate


def _matches(condition,event):
    if not condition: return True
    if 'all' in condition: return all(_matches(item,event) for item in condition['all'])
    if 'any' in condition: return any(_matches(item,event) for item in condition['any'])
    if 'not' in condition: return not _matches(condition['not'],event)
    if 'field' not in condition:
        return all(event.get(key)==value for key,value in condition.items())
    field=condition.get('field'); op=condition.get('op','eq'); expected=condition.get('value')
    if field not in event: return False
    actual=event[field]
    if op=='eq': return actual==expected
    if op=='in': return actual in expected
    if op=='not_in': return actual not in expected
    if op=='contains': return isinstance(actual,str) and expected in actual
    if op=='not_contains': return isinstance(actual,str) and expected not in actual
    if op=='gte': return isinstance(actual,(int,float)) and not isinstance(actual,bool) and actual>=expected
    if op=='lte': return isinstance(actual,(int,float)) and not isinstance(actual,bool) and actual<=expected
    if op=='truthy': return actual is True
    raise ContractError('invalid_crosspost_condition')


def preview_crossposts(event: dict, registry) -> list[dict]:
    if not isinstance(event,Mapping): raise ContractError('invalid_crosspost_event')
    rows=[]
    rules=registry.crossposts.values() if isinstance(registry.crossposts,Mapping) else registry.crossposts
    for frozen in rules:
        rule=thaw(frozen)
        if event.get('source_connection_id') != rule.get('source_connection_id'): continue
        destination=registry.connections.get(rule['destination_connection_id'])
        def attr(name): return destination.get(name) if isinstance(destination,Mapping) else getattr(destination,name,None)
        eligible=True; reasons=[]
        checks=[(event.get('owner_account_id')==rule.get('owner_account_id'),'owner_mismatch'),(not rule.get('allowed_slots') or event.get('slot',event.get('schedule_slot')) in rule['allowed_slots'],'slot_not_allowed'),(_matches(rule.get('trigger'),event),'trigger_not_met'),(_matches(rule.get('conditions'),event),'conditions_not_met')]
        for ok,reason in checks:
            if not ok: eligible=False; reasons.append(reason)
        enabled=rule.get('enabled')
        status='ineligible' if not eligible else 'disabled' if enabled is False else 'unknown' if enabled is not True else 'observe_legacy' if rule.get('delivery_owner')=='legacy' else 'planned' if rule.get('delivery_owner')=='managed' else 'unknown'
        if status!='planned': reasons.append(status)
        not_before=None
        if event.get('source_public_at') is not None:
            not_before=earliest_post_time(rule,event['source_public_at'],event.get('last_destination_post_at')).isoformat()
        rows.append(dict(rule_id=rule['id'],content_id=event.get('content_id'),revision=event.get('revision'),owner_account_id=rule.get('owner_account_id'),source_connection_id=rule.get('source_connection_id'),destination_connection_id=rule.get('destination_connection_id'),connection_id=rule.get('destination_connection_id'),destination_account_id=attr('account_id'),platform=attr('platform'),status=status,eligible=eligible,reasons=reasons,activation_evidence=rule.get('activation_evidence',[]),conditions=rule.get('conditions',{}),trigger=rule.get('trigger',{}),allowed_slots=rule.get('allowed_slots',[]),delivery_owner=rule.get('delivery_owner'),delay_owner=rule.get('delay_owner'),delay_seconds=rule.get('delay_seconds',0),min_gap_seconds=rule.get('min_gap_seconds',0),window=rule.get('window'),dedupe_strategy=rule.get('dedupe_strategy'),transform_id=rule.get('transform_id'),not_before=not_before,execution_enabled=False))
    return rows


def crosspost_intents(event: dict, registry) -> tuple[dict,...]:
    return tuple(row for row in preview_crossposts(event,registry) if row['status']=='planned')
