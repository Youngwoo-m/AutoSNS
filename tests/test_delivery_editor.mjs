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

// Small DOM surface for exercising the production listeners without a browser dependency.
class TestElement {
 constructor(tag='',text=''){this.tagName=tag;this.children=[];this.attrs={};this.listeners={};this._text=text;this.disabled=false;this.value='';}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=[...nodes];}
 setAttribute(key,value){this.attrs[key]=value;}
 getAttribute(key){return this.attrs[key];}
 set textContent(value){this._text=value;this.children=[];}
 addEventListener(name,fn){this.listeners[name]=fn;}
 get textContent(){return this._text+this.children.map(node=>node.textContent||'').join('');}
 querySelectorAll(selector){const match=node=>selector.startsWith('[')?Object.hasOwn(node.attrs,selector.slice(1,-1)):node.tagName===selector;return this.children.flatMap(node=>node instanceof TestElement?[...(match(node)?[node]:[]),...node.querySelectorAll(selector)]:[]);}
 querySelector(selector){return this.querySelectorAll(selector)[0]||null;}
}
const useTestDocument=()=>{const old=globalThis.document;globalThis.document={createElement:tag=>new TestElement(tag),createTextNode:text=>new TestElement('',text)};return ()=>{globalThis.document=old;};};
const tick=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
const findButton=(root,label)=>root.querySelectorAll('button').find(node=>node.textContent===label);
const findInput=(root,label)=>root.querySelectorAll('label').find(node=>node.children[0]?.textContent===label)?.children.at(-1);
const fullContent={...content,source:'managed',title:'제목',kind:'article',series:'',status:'drafting',original:'원문',variants:[],sources:[],assets:[],reviews:[]};
const stubApi=extra=>({listConnections:async()=>({items:[]}),listDeliveries:async()=>({items:[{...plan,platform:'youtube'}]}),getContent:async()=>fullContent,listRevisions:async()=>({items:[{revision:4}]}),...extra});
test('렌더 뒤 입력한 슬롯은 기존 새 계획·선택 버튼의 실제 핸들러에서도 보존한다',async()=>{
 const restore=useTestDocument();try{
  let reads=0;const editor=delivery.createDeliveryEditor({api:stubApi({getDelivery:async()=>{reads++;return plan;}}),writable:()=>true});await editor.open(fullContent);
  const oldNew=findButton(editor.element,'새 계획 작성'),oldSelect=editor.element.querySelectorAll('button').find(node=>node.textContent.includes('버전 4'));
  const slot=findInput(editor.element,'일정 슬롯 (계획 생성 후 고정)');slot.value='unsaved';slot.listeners.input({target:slot});
  await oldNew.listeners.click();await oldSelect.listeners.click();
  assert.equal(findInput(editor.element,'일정 슬롯 (계획 생성 후 고정)').value,'unsaved');assert.equal(editor.hasUnsavedChanges(),true);assert.equal(reads,0);assert.equal(oldNew.disabled,true);
  const discard=findButton(editor.element,'입력 버리고 계획 다시 불러오기');assert.equal(discard.hidden,false);await discard.listeners.click();await tick();assert.equal(editor.hasUnsavedChanges(),false);
 }finally{restore();}
});
test('부모 원본 저장·자산 업로드 실제 핸들러는 자식 초안과 처리 중 요청을 보존한다',async()=>{
 const restore=useTestDocument();try{
  const {createContentEditor}=await import('../ax-console/app/web/content_editor.js');let writes=0,uploads=0,finish;
  const api=stubApi({updateContent:async()=>{writes++;return {...fullContent,revision:5};},uploadAsset:async()=>{uploads++;return {...fullContent,revision:5};},getDelivery:()=>new Promise(resolve=>finish=resolve),deliveryEvents:async()=>({items:[]})});
  const editor=createContentEditor({api,writable:()=>true});await editor.open(fullContent);await tick();
  const form=editor.element.querySelector('form'),upload=editor.element.querySelectorAll('input').find(node=>node.attrs.type==='file');
  const slot=findInput(editor.element,'일정 슬롯 (계획 생성 후 고정)');slot.value='keep';slot.listeners.input({target:slot});
  await form.listeners.submit({preventDefault(){}});await upload.listeners.change({target:{files:[{name:'a.png'}]}});
  assert.equal(writes,0);assert.equal(uploads,0);assert.equal(findButton(editor.element,'원본 저장').disabled,true);assert.equal(upload.disabled,true);assert.equal(findInput(editor.element,'일정 슬롯 (계획 생성 후 고정)').value,'keep');
  await findButton(editor.element,'입력 버리고 계획 다시 불러오기').listeners.click();await tick();
  // A clean child selection is busy without any dirty draft; the busy guard is independent.
  const pending=editor.element.querySelectorAll('button').find(node=>node.textContent.includes('버전 4')&&node.textContent.includes('youtube')).listeners.click();await tick();
  assert.equal(editor.isBusy(),true);assert.equal(findButton(editor.element,'원본 저장').disabled,true);
  await form.listeners.submit({preventDefault(){}});await upload.listeners.change({target:{files:[{}]}});assert.equal(writes,0);assert.equal(uploads,0);
  finish({...plan,scheduled_at:'2026-11-01T01:00:00+00:00',timezone:'Asia/Seoul'});await pending;
  assert.equal(editor.isBusy(),false);
  // The explicit discard path releases the parent, rather than leaving both editors locked.
  await editor.element.querySelector('form').listeners.submit({preventDefault(){}});assert.equal(writes,1);
 }finally{restore();}
});

const selectedPlan={...plan,platform:'youtube',owner_account_id:'personal',destination_account_id:'dept',scheduled_at:'2026-11-01T01:00:00+00:00',timezone:'Asia/Seoul'};
async function selectedEditor(extra={}){
 const api=stubApi({getDelivery:async()=>selectedPlan,deliveryEvents:async()=>({items:[]}),approveDelivery:async()=>({...selectedPlan,version:4,status:'ready'}),previewDeliverySchedule:async()=>({preview_hash:'impact',approval_retained:true}),rescheduleDelivery:async(_id,body)=>({...selectedPlan,...body,version:4}),...extra});
 const editor=delivery.createDeliveryEditor({api,writable:()=>true});await editor.open(fullContent);await editor.element.querySelectorAll('button').find(node=>node.textContent.includes('버전 4')&&node.textContent.includes('youtube')).listeners.click();return editor;
}
function inputValue(editor,label,value){const input=findInput(editor.element,label);input.value=value;input.listeners.input({target:input});}
test('승인 저장은 일정 초안·dirty를 보존하며 이전 버전 일정 미리보기를 폐기한다',async()=>{
 const restore=useTestDocument();try{
  const editor=await selectedEditor();inputValue(editor,'변경할 ISO 시각','2026-11-02T10:00:00+09:00');
  await findButton(editor.element,'일정 영향 미리보기').listeners.click();inputValue(editor,'계획 승인 메모','승인 저장');
  await findButton(editor.element,'이 버전 계획 승인').listeners.click();editor.refreshControls();
  assert.equal(findInput(editor.element,'변경할 ISO 시각').value,'2026-11-02T10:00:00+09:00');assert.equal(findInput(editor.element,'계획 승인 메모').value,'');assert.equal(editor.hasUnsavedChanges(),true);assert.equal(findButton(editor.element,'일정 변경 저장').disabled,true);
  await findButton(editor.element,'새 계획 작성').listeners.click();assert.ok(findInput(editor.element,'변경할 ISO 시각'));
  inputValue(editor,'변경할 ISO 시각','2026-11-01T10:00:00+09:00');assert.equal(editor.hasUnsavedChanges(),false);
 }finally{restore();}
});
test('일정 저장은 승인 메모·dirty를 보존하고 명시적 폐기만 남은 입력을 지운다',async()=>{
 const restore=useTestDocument();try{
  const editor=await selectedEditor();inputValue(editor,'계획 승인 메모','다음 검토 메모');inputValue(editor,'변경할 ISO 시각','2026-11-03T10:00:00+09:00');
  await findButton(editor.element,'일정 영향 미리보기').listeners.click();await findButton(editor.element,'일정 변경 저장').listeners.click();editor.refreshControls();
  assert.equal(findInput(editor.element,'계획 승인 메모').value,'다음 검토 메모');assert.equal(editor.hasUnsavedChanges(),true);assert.equal(findButton(editor.element,'새 계획 작성').disabled,true);
  inputValue(editor,'계획 승인 메모','');assert.equal(editor.hasUnsavedChanges(),false);inputValue(editor,'계획 승인 메모','폐기');await findButton(editor.element,'입력 버리고 계획 다시 불러오기').listeners.click();assert.equal(editor.hasUnsavedChanges(),false);
 }finally{restore();}
});
test('미리보기는 대상 ID·인증·지역 시각·승인과 교차 제외 이유를 한국어로 요약한다',()=>{
 const summary=delivery.deliveryPreviewSummary({...selectedPlan,target_status:'verified',crossposts:[{owner_account_id:'personal',destination_account_id:'dept',platform:'tiktok',status:'ineligible',delivery_owner:'legacy',delay_owner:'legacy_queue_add',delay_seconds:1800,min_gap_seconds:10800,not_before:'2026-11-01T01:30:00+00:00',reasons:['conditions_not_met','slot_not_allowed']}]});
 assert.match(summary.join(' '),/개인 → 학과/);assert.match(summary.join(' '),/대상 ID 확인.*인증 미확인/);assert.match(summary.join(' '),/2026-11-01T10:00:00\+09:00.*Asia\/Seoul/);assert.match(summary.join(' '),/기존 실행기.*조건 불충족.*허용 슬롯 아님/);assert.match(summary.join(' '),/30분.*180분/);
 assert.match(delivery.deliveryPreviewSummary({target_status:'unverified',approval_retained:false}).join(' '),/대상 미확인.*재검토/);
 assert.match(delivery.deliveryPreviewSummary({approval_retained:true}).join(' '),/승인 유지/);
});

test('일정 미리보기 실제 화면은 한국어 요약을 먼저 보이고 JSON은 접힌 기술 정보에 둔다',async()=>{
 const restore=useTestDocument();try{
  const editor=await selectedEditor({previewDeliverySchedule:async()=>({...selectedPlan,preview_hash:'impact',approval_retained:true})});
  await findButton(editor.element,'일정 영향 미리보기').listeners.click();
  assert.match(editor.element.textContent,/대상 ID 확인 · 인증 미확인/);assert.match(editor.element.textContent,/로컬 예정 시각:/);
  const details=editor.element.querySelector('details');assert.ok(details);assert.equal(details.attrs.open,undefined);assert.ok(details.querySelector('pre'));
 }finally{restore();}
});
test('과거 승인 기록은 현재 승인·재검토·취소 상태를 구분해 한국어로 표시한다',()=>{
 const approval={decision:'approved',scope:'plan',subject_hash:'old',content_revision:4,recorded_at:'2026-11-01T01:00:00Z'};
 assert.match(delivery.approvalRecordLabel({...selectedPlan,approval}),/이전 계획 승인 기록 · 현재 조건은 재검토 필요/);
 assert.match(delivery.approvalRecordLabel({...selectedPlan,status:'ready',approval:{...approval,subject_hash:'subject'}}),/현재 계획 승인 기록 · 승인/);
 assert.match(delivery.approvalRecordLabel({...selectedPlan,status:'cancelled',approval}),/취소 전 기록/);
 assert.match(delivery.approvalRecordLabel({...selectedPlan,approval:{...approval,decision:'rejected'}}),/반려/);
});

test('Threads 텍스트 전용 선택은 명시적 true일 때만 계획 옵션에 보존한다',()=>{
 const content={id:'c',revision:1,manifest_hash:'hash'};
 const draft={connection_id:'dept.threads',scheduled_at:'2026-11-02T10:00:00+09:00',schedule_slot:'main',text_only:true};
 assert.deepEqual(delivery.deliveryPayload(content,draft).options,{text_only:true});
 for(const text_only of [false,undefined,'true',1])assert.deepEqual(delivery.deliveryPayload(content,{...draft,text_only}).options,{});
});
