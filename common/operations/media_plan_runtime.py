"""저장한 숏츠 계획을 버전 고정 자산과 등록 Remotion leaf에 연결한다.

HTTP/모델의 경로·실행명령은 받지 않는다. prepare는 명시 로컬 복사만 수행한다.
검토·재사용 승인은 주입된 renderer/inspector의 책임이며 계획만으로 만들지 않는다.
"""
from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import re
from pathlib import Path
from .content_store import StoreError,ConflictError
from .models import freeze,thaw
from .production_media import RegisteredSceneAsset,render_registered_media

@dataclass(frozen=True)
class PreparedShortMedia:
    artifact_root: Path
    plan_hash: str
    manifest: Mapping
    scene_assets: Mapping
    input_binding: Mapping


def prepare_short_media(record,*,content_store,attempt_id):
    from .media_plans import validate_media_plan,media_plan_readiness
    if (not isinstance(record,Mapping) or not isinstance(attempt_id,str) or
            not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',attempt_id)):
        raise StoreError('invalid')
    revision=record.get('content_revision')
    if type(revision) is not int or revision<1:raise StoreError('invalid')
    snapshot=content_store.get(record.get('content_id'),revision)
    if not snapshot:raise StoreError('not_found')
    if (snapshot['owner_account_id']!=record.get('owner_account_id') or snapshot['manifest_hash']!=record.get('manifest_hash')
            or type(record.get('plan_revision')) is not int or record['plan_revision']<1):
        raise StoreError('invalid')
    plan=validate_media_plan(thaw(record['plan']),snapshot)
    if not media_plan_readiness(plan)['inputs_ready']:raise StoreError('media_inputs_required')
    identity=dict(content_id=snapshot['id'],revision=revision,manifest_hash=snapshot['manifest_hash'],plan_revision=record['plan_revision'],plan=plan)
    digest=hashlib.sha256(json.dumps(identity,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
    root=content_store._path(Path('media-artifacts')/digest/attempt_id)
    root.mkdir(parents=True,exist_ok=False)
    copied={};registrations={}
    suffixes={'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','audio/wav':'.wav'}
    def copy_asset(asset_id):
        if asset_id in copied:return copied[asset_id]
        asset,raw=content_store.read_asset(snapshot['id'],revision,asset_id)
        suffix=suffixes.get(asset['media_type'])
        if not suffix:raise StoreError('invalid')
        path=root/(asset_id+suffix)
        path.write_bytes(raw)
        copied[asset_id]=path
        return path
    scenes=[]
    for scene in plan['scenes']:
        asset_id=scene['asset_id'];path=copy_asset(asset_id)
        source='managed-content:'+snapshot['id']+':r'+str(revision)+':'+asset_id
        request_id='media-plan:'+digest
        registrations[asset_id]=RegisteredSceneAsset(asset_id,str(path),hashlib.sha256(path.read_bytes()).hexdigest(),source,'reuse',
            dict(kind='reuse',record_id=request_id),reuse_request_id=request_id)
        scenes.append(dict(title=scene['title'],caption=scene['caption'],kind=scene['kind'],seconds=scene['seconds'],
            image=str(path),image_asset_id=asset_id))
    manifest={k:plan[k] for k in ('exam','field','source','footer','disclosure')}
    manifest.update(voice=str(copy_asset(plan['voice_asset_id'])),scenes=scenes,output='short.mp4')
    return PreparedShortMedia(root,digest,freeze(manifest),freeze(registrations),
        freeze(dict(content_id=snapshot['id'],content_revision=revision,manifest_hash=snapshot['manifest_hash'],owner_account_id=snapshot['owner_account_id'])))


def render_prepared_short(prepared,*,runner_factory=None,reuse_authorization=None,probe=None,inspect_video=None,
                          defer_video_review=False):
    """명시 실행 전용. 등록 leaf와 실측/검토자를 주입하지 않으면 완료되지 않는다.

    defer_video_review=True이면 사람 검토만 부족한 영상이 awaiting_review로 반환된다(기본 False).
    """
    if not isinstance(prepared,PreparedShortMedia):raise StoreError('invalid')
    if not callable(runner_factory):return dict(status='blocked',reason_code='renderer_unavailable',assets=[])
    runner=runner_factory(scene_assets=prepared.scene_assets,reuse_authorization=reuse_authorization)
    if not callable(runner):raise StoreError('invalid')
    runners={'remotion_video':runner,'scene_assets':prepared.scene_assets,'reuse_authorization':reuse_authorization}
    if probe is not None:runners['probe']=probe
    if inspect_video is not None:runners['inspect_video']=inspect_video
    if defer_video_review is True:runners['defer_video_review']=True
    return render_registered_media('remotion_video',prepared.manifest,artifact_root=prepared.artifact_root,runners=runners)


def ingest_short_output(prepared,result,*,content_store):
    """검증된 렌더 결과만 현재 원고에 CAS 등록한다. 오래된 원고를 덮어쓰지 않는다."""
    from .production import validate_production_result
    if not isinstance(prepared,PreparedShortMedia) or not isinstance(result,Mapping) or result.get('status')!='completed':
        raise StoreError('invalid')
    binding=prepared.input_binding
    snapshot=content_store.get(binding['content_id'])
    if not snapshot:raise StoreError('not_found')
    if any(snapshot[k]!=binding[v] for k,v in (('revision','content_revision'),('manifest_hash','manifest_hash'),('owner_account_id','owner_account_id'))):
        raise ConflictError()
    checked=validate_production_result(dict(text='',assets=result.get('assets',[])),('remotion_video',),prepared.artifact_root)
    if checked['status']!='completed' or len(checked['assets'])!=1:raise StoreError('invalid')
    asset=checked['assets'][0]
    if asset['media_type']!='video/mp4':raise StoreError('invalid')
    raw=Path(asset['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=asset['sha256']:raise StoreError('storage_error')
    content=content_store.add_asset(binding['content_id'],binding['content_revision'],asset['filename'],asset['media_type'],raw)
    return dict(content=content,review_status='not_checked',plan_hash=prepared.plan_hash)
