"""불변 제작 입력·CAS 실행 기록. 읽기는 이행/파일 생성을 하지 않는다."""
from collections.abc import Mapping
import json
from pathlib import Path

from .content_store import ContentStore, StoreError, ConflictError, _json
from .models import thaw
from .production_models import ProductionRequest, ProviderPolicy
from .runtime_store import RuntimeStore, digest, stamp


def _request(request):
    if not isinstance(request, ProductionRequest): raise StoreError('invalid_production_request')
    return {k:thaw(getattr(request,k)) for k in ('job_id','owner_account_id','occurrence_id','content_id',
            'expected_revision','brief','required_outputs','production_unit_id')}


class ProductionStore(RuntimeStore):
    def __init__(self, root, *, registry=None):
        super().__init__(root, registry=registry, content_store=ContentStore(root))

    def bind_input(self, base_job_id, snapshot: Mapping, job: Mapping, registry_revision, *, create):
        if (type(create) is not bool or not isinstance(snapshot, Mapping) or not isinstance(job, Mapping)
                or job.get('id') != base_job_id or job.get('kind') != 'production'
                or job.get('base_job_id') is not None or not isinstance(registry_revision,str) or not registry_revision
                or not isinstance(job.get('policy_revision'),str) or not job['policy_revision']):
            raise StoreError('invalid_binding')
        registered=getattr(self.registry,'jobs',{}).get(base_job_id)
        if (getattr(self.registry,'revision',None)!=registry_revision or not isinstance(registered,Mapping)
                or thaw(registered)!=thaw(job) or registered.get('execution_owner')!='managed'
                or registered.get('enabled') is not True):raise StoreError('invalid_binding')
        current=self.content_store.get(snapshot.get('id'),snapshot.get('revision'))
        if not current or current['owner_account_id'] != job.get('owner_account_id'):
            raise StoreError('invalid_binding')
        # 대조한 서버 원고만 동결한다. id/hash만 같게 둔 payload 위조도 거부한다.
        if any(thaw(snapshot.get(k)) != thaw(v) for k,v in current.items() if k not in ('reviews',)):
            raise StoreError('invalid_binding')
        brief=thaw(job.get('brief', {k:current[k] for k in ('title','original','sources')}))
        outputs=thaw(job.get('required_outputs'))
        try: ProductionRequest(base_job_id,current['owner_account_id'],'binding',current['id'],current['revision'],brief,outputs)
        except (ValueError,TypeError) as exc: raise StoreError('invalid_binding') from exc
        payload=dict(base_job_id=base_job_id,content_id=current['id'],content_revision=current['revision'],
                     manifest_hash=current['manifest_hash'],owner_account_id=current['owner_account_id'],
                     policy_revision=job['policy_revision'],registry_revision=registry_revision,
                     brief=brief,required_outputs=outputs)
        binding_id=digest(payload)
        result=dict(binding_id=binding_id,execution_job_id='production.'+binding_id,**{k:v for k,v in payload.items() if k not in ('brief','required_outputs')},input_payload=payload)
        with self._db(create) as conn:
            if conn is None: raise StoreError('binding_not_found')
            row=conn.execute('SELECT * FROM production_bindings WHERE binding_id=?',(binding_id,)).fetchone()
            if row:
                prior=dict(row,input_payload=json.loads(row['input_payload']))
                if prior != result: raise ConflictError()
                return prior
            if not create: raise StoreError('binding_not_found')
            conn.execute('INSERT INTO production_bindings VALUES(?,?,?,?,?,?,?,?,?,?)',
                         tuple(result[k] for k in ('binding_id','base_job_id','execution_job_id','content_id','content_revision',
                               'manifest_hash','owner_account_id','policy_revision','registry_revision'))+(_json(payload),))
        return result

    def list_bindings(self):
        with self._db() as conn:
            if conn is None or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_bindings'").fetchone(): return []
            result=[]
            for row in conn.execute('SELECT * FROM production_bindings ORDER BY binding_id'):
                item=dict(row,input_payload=json.loads(row['input_payload']))
                payload=item['input_payload']
                if (digest(payload)!=item['binding_id'] or item['execution_job_id']!='production.'+item['binding_id']
                        or any(payload.get(key)!=item[key] for key in ('base_job_id','content_id','content_revision',
                                  'manifest_hash','owner_account_id','policy_revision','registry_revision'))):raise ConflictError()
                result.append(item)
            return result

    def _attempt(self, conn, unit_id):
        row=conn.execute('SELECT * FROM production_attempts WHERE unit_id=?',(unit_id,)).fetchone()
        return dict(row,provenance=json.loads(row['provenance']),result=json.loads(row['result']) if row['result'] else None) if row else None

    def get(self, unit_id):
        with self._db() as conn:
            if conn is None or not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='production_attempts'").fetchone(): return None
            return self._attempt(conn,unit_id)

    def start(self, request: ProductionRequest, policy: ProviderPolicy, now):
        raw=_request(request)
        if (not isinstance(policy,ProviderPolicy) or request.job_id not in policy.job_ids
                or request.owner_account_id != policy.owner_account_id): raise StoreError('provider_policy_violation')
        binding_id,separator,run_id=request.occurrence_id.partition(':')
        if not separator or not run_id:raise StoreError('invalid_binding_occurrence')
        binding=next((b for b in self.list_bindings() if b['binding_id']==binding_id),None)
        if binding is None: raise StoreError('binding_not_found')
        if (binding['base_job_id']!=request.job_id or binding['owner_account_id']!=request.owner_account_id
                or binding['content_id']!=request.content_id or binding['content_revision']!=request.expected_revision
                or binding['input_payload']['brief']!=thaw(request.brief)
                or binding['input_payload']['required_outputs']!=list(request.required_outputs)):raise ConflictError()
        registry=self.registry
        jobs=getattr(registry,'jobs',None);policies=getattr(registry,'policies',None)
        if not isinstance(jobs,Mapping) or not isinstance(policies,Mapping):raise StoreError('production_registry_required')
        base=jobs.get(request.job_id)
        if (getattr(registry,'revision',None)!=binding['registry_revision'] or not isinstance(base,Mapping)
                or base.get('kind')!='production' or base.get('base_job_id') is not None
                or base.get('execution_owner')!='managed' or base.get('enabled') is not True
                or base.get('owner_account_id')!=binding['owner_account_id']
                or base.get('policy_revision')!=binding['policy_revision']
                or thaw(base.get('required_outputs'))!=binding['input_payload']['required_outputs']):raise StoreError('invalid_binding')
        current_policy=policies.get(base['policy_revision'])
        if not isinstance(current_policy,Mapping):raise StoreError('unknown_policy')
        if (base.get('provider_policy_id') is not None and base['provider_policy_id']!=policy.id
                or (base.get('subscription_only') is True or current_policy.get('subscription_only') is True) and not policy.subscription_only):
            raise StoreError('provider_policy_violation')
        if 'brief' in base and thaw(base['brief'])!=binding['input_payload']['brief']:raise StoreError('invalid_binding')
        request_hash=digest(dict(request=raw,policy=thaw(policy.__dict__),binding_id=binding['binding_id']))
        with self._db(True) as conn:
            old=self._attempt(conn,request.production_unit_id)
            if old:
                if old['request_hash'] != request_hash: raise ConflictError()
                return dict(old,claimed=False)
            current=conn.execute('SELECT current_revision FROM contents WHERE id=?',(request.content_id,)).fetchone()
            if not current or current[0]!=request.expected_revision: raise ConflictError()
            snapshot=self.content_store.get(request.content_id,request.expected_revision)
            if not snapshot or snapshot['manifest_hash']!=binding['manifest_hash']: raise ConflictError()
            for asset in snapshot['assets']: self.content_store.read_asset(snapshot['id'],snapshot['revision'],asset['id'])
            provenance=dict(binding_id=binding['binding_id'],request=raw,policy_id=policy.id,started_at=stamp(now))
            conn.execute("INSERT INTO production_attempts VALUES(?,?,'running',1,?,NULL)",
                         (request.production_unit_id,request_hash,_json(provenance)))
            return dict(self._attempt(conn,request.production_unit_id),claimed=True)

    def finish(self, unit_id: str, expected_version: int, result: dict):
        if type(expected_version) is not int or not isinstance(result,dict) or result.get('status') not in ('completed','blocked','unknown'):
            raise StoreError('invalid_production_result')
        raw=thaw(result)
        raw.setdefault('observed_usage',None)
        with self._db(True) as conn:
            old=self._attempt(conn,unit_id)
            if not old or old['version']!=expected_version or old['state']!='running': raise ConflictError()
            provenance=old['provenance']
            if raw['status']=='completed':
                producer=raw.get('producer')
                if (not isinstance(producer,dict) or set(producer)!={'principal_id','execution_id'}
                        or not all(isinstance(v,str) and v for v in producer.values())): raise StoreError('invalid_production_provenance')
                request=provenance['request']
                snapshot=self.content_store.get(request['content_id'])
                if (not snapshot or snapshot['owner_account_id']!=request['owner_account_id']
                        or raw.get('content_id')!=snapshot['id'] or raw.get('revision')!=snapshot['revision']
                        or raw.get('manifest_hash')!=snapshot['manifest_hash']): raise ConflictError()
                for asset in snapshot['assets']: self.content_store.read_asset(snapshot['id'],snapshot['revision'],asset['id'])
                provenance=dict(provenance,producer=producer,output=dict(content_id=snapshot['id'],revision=snapshot['revision'],
                                manifest_hash=snapshot['manifest_hash'],assets=snapshot['assets']))
            conn.execute('UPDATE production_attempts SET state=?,version=version+1,provenance=?,result=? WHERE unit_id=? AND version=?',
                         (raw['status'],_json(provenance),_json(raw),unit_id,expected_version))
            return self._attempt(conn,unit_id)
