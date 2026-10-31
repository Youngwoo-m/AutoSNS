"""정규화 전 caller/source 권한을 정규화된 회차와 함께 보존하는 서버 전용 경계."""
from .content_store import StoreError
from .entrypoints import resolve_entrypoint
from .models import ContractError
from .runtime_models import utc


def receipt_context(request,caller_id,registry):
    job=registry.jobs.get(request['job_id'])
    if not job:raise StoreError('unknown_job')
    return dict(caller_id=caller_id,request_source=request['source'],
        base_job_id=job.get('base_job_id',request['job_id']),registry_revision=registry.revision)


def pending_receipt(request,caller_id,registry):
    receipt=receipt_context(request,caller_id,registry)
    job=registry.jobs[request['job_id']]
    return dict(receipt,occurrence=dict(request,source=job['schedule_owner'],scheduled_at_utc=utc(request['scheduled_at_utc']).isoformat()))


def validate_receipt(receipt,registry,catalog,*,execution_job_id=None,base_job_id=None):
    if not receipt:raise StoreError('execution_receipt_required')
    occurrence=receipt['occurrence'];base_id=receipt['base_job_id']
    if (receipt['registry_revision']!=registry.revision
        or base_job_id is not None and base_id!=base_job_id
        or execution_job_id is not None and occurrence['job_id']!=execution_job_id):raise StoreError('invalid_execution_receipt')
    base=registry.jobs.get(base_id)
    if (not base or base.get('base_job_id') is not None or base.get('enabled') is not True
        or base.get('execution_owner')!='managed' or occurrence.get('source')!=base.get('schedule_owner')):
        raise StoreError('invalid_execution_receipt')
    # 원래 caller와 원래 source를 대조한다. schedule_owner의 canonical source로 대체하지 않는다.
    route=resolve_entrypoint(receipt['caller_id'],base_id,registry,catalog)
    if route['route']!='managed' or route['source']!=receipt['request_source']:raise StoreError('source_mismatch')
    spec=catalog.executors[route['executor_id']]
    if occurrence['phase'] not in spec.phases:raise StoreError('executor_phase_forbidden')
    return receipt


def permits_binding(receipt,registry,catalog,binding):
    try:
        validate_receipt(receipt,registry,catalog,execution_job_id=binding['execution_job_id'],base_job_id=binding['base_job_id'])
        return receipt['occurrence']['phase']=='prepare'
    except (StoreError,ContractError,KeyError,TypeError):return False


class ReceiptDispatchStore:
    """호출별 불변 DI. 공유 store 속성이나 HTTP 6필드에 신원을 넣지 않는다."""
    def __init__(self,store,receipt):self.store,self.receipt=store,receipt
    def __getattr__(self,name):return getattr(self.store,name)
    def submit_occurrence(self,request,request_hash=None):
        return self.store.submit_occurrence(request,request_hash,execution_receipt=self.receipt)
