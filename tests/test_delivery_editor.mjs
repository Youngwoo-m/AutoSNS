import test from 'node:test';
import assert from 'node:assert/strict';
import * as delivery from '../ax-console/app/web/delivery_editor.js';
import {createContentApi} from '../ax-console/app/web/api.js';
import {scheduleLabel,statusLabel} from '../ax-console/app/web/view_helpers.js';
const content={id:'managed_1',owner_account_id:'personal',revision:4,manifest_hash:'hash'};
const plan={id:'d1',version:3,revision:4,subject_hash:'subject',status:'pending',target_status:'verified',blockers:[],approval:null};
test('계획 요청은 저장 원본 버전을 고정하고 소유자·실행 입력을 배제한다',()=>{
 const body=delivery.deliveryPayload(content,{connection_id:'dept.youtube',scheduled_at:'2026-11-01T10:00:00+09:00',timezone:'Asia/Seoul',schedule_slot:'morning',publication_purpose:'initial',owner_account_id:'dept',execution_enabled:true,condition_kind:'fixed'});
 assert.equal(body.revision,4);assert.equal(body.manifest_hash,'hash');assert.equal(body.owner_account_id,undefined);assert.equal(body.execution_enabled,undefined);assert.deepEqual(body.schedule_condition,{kind:'fixed',at:body.scheduled_at});
});
test('미확인 대상과 취소 계획은 승인할 수 없으며 계획 승인은 CAS·해시를 전송한다',()=>{
 assert.equal(delivery.canApprove({...plan,target_status:'unverified'}),false);assert.equal(delivery.canApprove({...plan,status:'cancelled'}),false);assert.equal(delivery.canApprove(plan),true);
 assert.deepEqual(delivery.approvalPayload(plan,'approved','확인'),{expected_version:3,subject_hash:'subject',decision:'approved',notes:'확인'});
 assert.match(statusLabel('ready'),/계획 승인됨.*실행 안 함/);assert.match(scheduleLabel('local_plan'),/로컬 계획/);
});
test('일정 저장은 현재 버전과 정확한 영향 미리보기 hash를 요구한다',()=>{
 const draft={scheduled_at:'2026-11-02T10:00:00+09:00',timezone:'Asia/Seoul'};
 assert.throws(()=>delivery.schedulePayload(plan,draft,null),/미리보기/);
 assert.deepEqual(delivery.schedulePayload(plan,draft,{preview_hash:'p'}),{expected_version:3,...draft,preview_hash:'p'});
 assert.match(delivery.scheduleImpactLabel({approval_preserved:false}),/재검토/);
});
test('409는 저장 계획 버전·일정 초안을 보존하고 변경된 입력은 이전 미리보기를 폐기한다',async()=>{
 const state=delivery.createDeliverySession();state.plan=plan;state.draft={notes:'유지'};state.preview={preview_hash:'old'};
 await state.write(async()=>{throw Object.assign(new Error('충돌'),{status:409});});
 assert.equal(state.plan.version,3);assert.equal(state.draft.notes,'유지');assert.equal(state.phase,'conflict');state.change('notes','새 입력');assert.equal(state.preview,null);
});
test('늦은 원본별 응답은 현재 계획 목록을 덮어쓰지 않는다',async()=>{
 const state=delivery.createDeliverySession();let finish;
 const old=state.load('old',()=>new Promise(resolve=>finish=resolve));await state.load('new',async()=>({items:[plan]}));finish({items:[{id:'old'}]});await old;assert.equal(state.items[0].id,'d1');
});
test('배포 API는 목록 wrapper와 전체 단일 응답 및 CAS 본문을 보존한다',async()=>{
 const calls=[];const api=createContentApi({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.includes('?')?{items:[plan]}:plan};}});
 assert.equal((await api.listDeliveries('dept','managed_1')).items[0].id,'d1');await api.approveDelivery('d1',delivery.approvalPayload(plan,'approved',''));
 assert.equal(calls[1].url,'/api/v2/deliveries/d1/approvals');assert.equal(JSON.parse(calls[1].options.body).subject_hash,'subject');
 await api.rescheduleDelivery('d1',{expected_version:3,preview_hash:'p'});assert.equal(calls[2].options.method,'PUT');
});
test('저장 UTC 일정은 선택 지역의 offset을 포함한 편집값으로 돌린다',()=>{
 assert.equal(delivery.zonedScheduleValue('2026-11-01T01:00:00+00:00','Asia/Seoul'),'2026-11-01T10:00:00+09:00');
 assert.equal(delivery.scheduleImpactLabel({approval_retained:true}),'계획 승인 유지');
});
