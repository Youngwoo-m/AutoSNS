"""임시 DB에 A5 제작/독립 검토를 실제 연결하는 fixture. 운영 provider 등록 없음."""
from dataclasses import replace
import json

from common.operations.models import thaw
from common.operations.production import produce_content
from common.operations.production_models import ProductionRequest, ProviderPolicy
from common.operations.production_store import ProductionStore
from common.operations.quota import bucket_id, quota_window
from common.operations.review_runner import RegisteredReviewRunner, SubscriptionReviewProvider, run_reviews


class _FixtureProvider:
    def __init__(self, text, execution_id):
        self.text=text;self.execution_id=execution_id;self.calls=[]

    def generate(self, request, prompt, policy):
        self.calls.append((request,prompt,policy))
        return dict(status='completed',text=self.text,provider_id='claude-subscription',
                    execution_id=self.execution_id,observed_usage=None)


def produce_reviewed_fixture(content_store, runtime_store, registry, snapshot, now):
    """최초 draft→완료 revision→source review→불변 output/budget link를 준비한다."""
    base_id='fixture-produce'
    job=dict(id=base_id,kind='production',enabled=True,execution_owner='managed',schedule_owner='console',
             owner_account_id=snapshot['owner_account_id'],policy_revision='p',subscription_only=True,
             required_outputs=['text'],brief={'topic':'발행 관문 fixture'})
    registry=replace(registry,jobs={**thaw(registry.jobs),base_id:job})
    runtime_store.registry=registry
    production_store=ProductionStore(runtime_store.root,registry=registry);production_store.initialize()
    binding=production_store.bind_input(base_id,snapshot,job,registry.revision,create=True)
    request=ProductionRequest(base_id,snapshot['owner_account_id'],binding['binding_id']+':fixture-production-run',
                              snapshot['id'],snapshot['revision'],binding['input_payload']['brief'],('text',))
    policy=ProviderPolicy('legacy-subscription:'+snapshot['owner_account_id']+':'+base_id,snapshot['owner_account_id'],
                          (base_id,),True,('claude-subscription',),('text',),())
    # 제작 전 최초 owner 관측만 등록한다. target/API는 각 시험 시나리오가 준비한다.
    for requirement in registry.policies['p']['quota_requirements']:
        if requirement['scope_kind']!='owner':continue
        start,end=quota_window(requirement,now)
        runtime_store.observe_bucket(bucket_id('owner',requirement['scope_id'],requirement['metric'],start,end),
                                     requirement['limit'],0,now,end)
    provider=_FixtureProvider(snapshot['original'],'fixture-production-execution')
    result=produce_content(request,provider=provider,media_runner={},content_store=content_store,
                           production_store=production_store,runtime_store=runtime_store,policy=policy,now=now)
    if result['status']!='completed' or len(provider.calls)!=1:raise AssertionError(result)
    final=content_store.get(result['content_id'],result['revision'])
    review_provider=_FixtureProvider(json.dumps({'verdict':'pass','findings':[]}), 'fixture-source-review-execution')
    runner=RegisteredReviewRunner({'reviewer':SubscriptionReviewProvider(review_provider,request=request,policy=policy,principal_id='reviewer')},
        source_checker=lambda snapshot:dict(available=True,checked=True,method='fixture-source-check'))
    review=run_reviews(final,producer=result['producer'],authorities=registry.policies['p'],runner=runner,runtime_store=runtime_store,now=now)
    if review['status']!='completed' or len(review_provider.calls)!=1:raise AssertionError(review)
    linked=runtime_store.get_production_for_output(final['id'],final['revision'],final['manifest_hash'])
    if not linked or linked['production_id']!=request.production_unit_id:raise AssertionError('A5 fixture output link missing')
    return dict(registry=registry,snapshot=final,producer=result['producer'],review=review,
                production_store=production_store,unit_id=request.production_unit_id)
