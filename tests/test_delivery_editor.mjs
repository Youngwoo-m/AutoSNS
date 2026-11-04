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

const facebookConnections=[
 {id:'personal.facebook',account_id:'personal',platform:'facebook',planning_enabled:true,capabilities:['text_only','visibility:public']},
 {id:'dept.facebook',account_id:'dept',platform:'facebook',planning_enabled:true,capabilities:['visibility:public']},
 {id:'dept.threads',account_id:'dept',platform:'threads',planning_enabled:true,capabilities:['text_only','visibility:public']},
 {id:'personal.youtube',account_id:'personal',platform:'youtube',planning_enabled:true,capabilities:['text_only']}];
const connectionField=editor=>findInput(editor.element,'실제 등록 연결 (도구 선호와 별개)');
const selectConnection=(editor,id)=>{const field=connectionField(editor);field.value=id;field.listeners.input({target:field});};
test('Facebook 페이지 텍스트 전용은 실제 등록 기능에 있을 때만 선택하고 개인 타임라인과 구분한다',async()=>{
 const restore=useTestDocument();try{
  let writes=0;const editor=delivery.createDeliveryEditor({api:stubApi({listConnections:async()=>({items:facebookConnections}),previewDelivery:async()=>{writes++;}}),writable:()=>true});await editor.open(fullContent);
  selectConnection(editor,'personal.facebook');const box=editor.element.querySelector('[data-facebook-text-only]');assert.ok(box);assert.match(editor.element.textContent,/Facebook 페이지에 텍스트만 발행/);assert.match(editor.element.textContent,/개인 타임라인 게시 아님/);box.checked=true;box.listeners.change({target:box});assert.equal(editor.hasUnsavedChanges(),true);assert.equal(writes,0);
  selectConnection(editor,'dept.facebook');assert.equal(editor.element.querySelector('[data-facebook-text-only]'),null);
  selectConnection(editor,'personal.youtube');assert.equal(editor.element.querySelector('[data-facebook-text-only]'),null);assert.equal(editor.element.querySelector('[data-threads-text-only]'),null);
  assert.equal(editor.element.querySelectorAll('nav').length,0);
 }finally{restore();}
});
test('연결 전환은 텍스트 전용 선택을 지우고 기존 Threads checkbox 동작을 보존한다',async()=>{
 const restore=useTestDocument();try{
  const editor=delivery.createDeliveryEditor({api:stubApi({listConnections:async()=>({items:facebookConnections})}),writable:()=>true});await editor.open(fullContent);
  selectConnection(editor,'personal.facebook');let box=editor.element.querySelector('[data-facebook-text-only]');box.checked=true;box.listeners.change({target:box});
  selectConnection(editor,'dept.threads');box=editor.element.querySelector('[data-threads-text-only]');assert.ok(box);assert.equal(box.checked,false);assert.match(editor.element.textContent,/Threads에 텍스트만 발행/);box.checked=true;box.listeners.change({target:box});
  selectConnection(editor,'personal.facebook');assert.equal(editor.element.querySelector('[data-facebook-text-only]').checked,false);
 }finally{restore();}
});
test('Facebook 텍스트 전용 미리보기와 저장 계획은 원본 자산 제외를 페이지 문구로 표시한다',async()=>{
 const preview={...selectedPlan,platform:'facebook',options:{text_only:true},target_label:'개인 소유 페이지'};
 const summary=delivery.deliveryPreviewSummary(preview).join(' ');assert.match(summary,/Facebook 페이지 텍스트 전용/);assert.match(summary,/개인 타임라인 게시가 아닙니다/);assert.match(summary,/이미지·영상은 이 배포에 포함하지 않습니다/);assert.doesNotMatch(summary,/Threads 텍스트 전용/);
 assert.match(delivery.deliveryPreviewSummary({...preview,platform:'threads'}).join(' '),/Threads 텍스트 전용/);
 const restore=useTestDocument();try{
  const editor=await selectedEditor({getDelivery:async()=>preview});assert.match(editor.element.textContent,/Facebook 페이지 텍스트 전용/);assert.match(editor.element.textContent,/개인 타임라인 게시가 아닙니다/);assert.doesNotMatch(editor.element.textContent,/Threads 텍스트 전용/);
 }finally{restore();}
});

test('Facebook 실제 계획 미리보기 화면에 텍스트 전용 승인 범위를 표시하고 발행은 요청하지 않는다',async()=>{
 const restore=useTestDocument();try{
  const calls=[];const editor=delivery.createDeliveryEditor({api:stubApi({listConnections:async()=>({items:facebookConnections}),previewDelivery:async body=>{calls.push(body);return {...selectedPlan,platform:'facebook',options:body.options,crossposts:[]};},createDelivery:async()=>{throw new Error('저장 클릭 없음');},submit:async()=>{throw new Error('발행 금지');}}),writable:()=>true});await editor.open(fullContent);selectConnection(editor,'personal.facebook');
  const box=editor.element.querySelector('[data-facebook-text-only]');box.checked=true;box.listeners.change({target:box});inputValue(editor,'예정 시각 (예: 2026-11-01T10:00:00+09:00)','2026-11-02T10:00:00+09:00');
  await findButton(editor.element,'계획 미리보기').listeners.click();assert.equal(calls.length,1);assert.deepEqual(calls[0].options,{text_only:true});assert.match(editor.element.textContent,/Facebook 페이지 텍스트 전용/);assert.match(editor.element.textContent,/이미지·영상은 이 배포에 포함하지 않습니다/);assert.match(editor.element.textContent,/실행 안 함/);
 }finally{restore();}
});

const igAssets=[{id:'jpeg-a',filename:'a.jpg',media_type:'image/jpeg',size:20,sha256:'b'.repeat(64)},{id:'jpeg-b',filename:'b.jpg',media_type:'image/jpeg',size:21,sha256:'c'.repeat(64)},{id:'video-a',filename:'a.mp4',media_type:'video/mp4',size:22,sha256:'d'.repeat(64)},{id:'png-a',filename:'a.png',media_type:'image/png',size:23,sha256:'e'.repeat(64)}];
const xConnections=[...facebookConnections,
 {id:'personal.x',account_id:'personal',platform:'x',planning_enabled:true,capabilities:['text_only','visibility:public']},
 {id:'dept.x',account_id:'dept',platform:'x',planning_enabled:true,capabilities:['visibility:public']}];
test('X 텍스트 전용은 등록 기능이 있어야 표시하고 선택 해제·연결 전환은 명시 선택을 초기화한다',async()=>{
 const restore=useTestDocument();try{
  const editor=delivery.createDeliveryEditor({api:stubApi({listConnections:async()=>({items:xConnections})}),writable:()=>true});await editor.open(fullContent);
  selectConnection(editor,'personal.x');let box=editor.element.querySelector('[data-x-text-only]');assert.ok(box);assert.equal(box.checked,false);assert.match(editor.element.textContent,/X API 비용 확인/);assert.match(editor.element.textContent,/비용 허용 전에는 실제 조회·발행을 실행하지 않습니다/);
  box.checked=true;box.listeners.change({target:box});box.checked=false;box.listeners.change({target:box});assert.equal(box.checked,false);
  box.checked=true;box.listeners.change({target:box});selectConnection(editor,'dept.threads');assert.equal(editor.element.querySelector('[data-threads-text-only]').checked,false);
  selectConnection(editor,'personal.x');assert.equal(editor.element.querySelector('[data-x-text-only]').checked,false);
  selectConnection(editor,'dept.x');assert.equal(editor.element.querySelector('[data-x-text-only]'),null);
  selectConnection(editor,'personal.youtube');assert.equal(editor.element.querySelector('[data-x-text-only]'),null);
 }finally{restore();}
});
test('X 텍스트 전용 계획은 명시 true를 저장하며 원문·원본 자산을 보존한다',async()=>{
 const restore=useTestDocument();try{
  const source={...fullContent,assets:igAssets},before=structuredClone(source),calls=[];
  const result=body=>({...selectedPlan,...body,platform:'x',options:body.options,crossposts:[]});
  const api=stubApi({listConnections:async()=>({items:xConnections}),deliveryEvents:async()=>({items:[]}),previewDelivery:async body=>{calls.push(['preview',body]);return result(body);},createDelivery:async body=>{calls.push(['save',body]);return result(body);},submit:async()=>{throw new Error('발행 금지');}});
  const editor=delivery.createDeliveryEditor({api,writable:()=>true});await editor.open(source);selectConnection(editor,'personal.x');
  let box=editor.element.querySelector('[data-x-text-only]');box.checked=true;box.listeners.change({target:box});inputValue(editor,'예정 시각 (예: 2026-11-01T10:00:00+09:00)','2026-11-02T10:00:00+09:00');
  await findButton(editor.element,'계획 미리보기').listeners.click();assert.match(editor.element.textContent,/X 텍스트 전용/);assert.match(editor.element.textContent,/이미지·영상은 이 배포에 포함하지 않습니다/);
  await findButton(editor.element,'로컬 계획 저장').listeners.click();assert.deepEqual(calls.map(([kind])=>kind),['preview','save']);for(const [,body]of calls){assert.deepEqual(body.options,{text_only:true});assert.equal(body.connection_id,'personal.x');}assert.deepEqual(source,before);
  const draft={connection_id:'personal.x',schedule_slot:'main',scheduled_at:'2026-11-02T10:00:00+09:00'};for(const value of [false,undefined,'true',1])assert.deepEqual(delivery.deliveryPayload(source,{...draft,text_only:value}).options,{});
 }finally{restore();}
});
const igContent={...fullContent,manifest_hash:'a'.repeat(64),assets:igAssets};
const ttConnection={id:'dept.tiktok',account_id:'dept',platform:'tiktok',planning_enabled:true,capabilities:['plan','visibility:public']};
test('TikTok 준비는 실제 MP4 한 개를 직접 선택하고 원본과 게시 실행을 바꾸지 않는다',async()=>{
 const restore=useTestDocument();try{
  const source={...igContent,variants:[{destination_account_id:'dept',platform:'tiktok',text:'저장된 캡션'}]},before=structuredClone(source),calls=[];
  const result=body=>({...selectedPlan,...body,platform:'tiktok',options:body.options,crossposts:[]});
  const editor=delivery.createDeliveryEditor({api:stubApi({listConnections:async()=>({items:[ttConnection,igConnection]}),deliveryEvents:async()=>({items:[]}),previewDelivery:async body=>{calls.push(['preview',body]);return result(body);},createDelivery:async body=>{calls.push(['save',body]);return result(body);}}),writable:()=>true});
  await editor.open(source);selectConnection(editor,'dept.tiktok');let select=findInput(editor.element,'TikTok 준비용 영상 (MP4 1개)');assert.equal(select.value,'');assert.deepEqual(select.children.map(n=>n.attrs.value),['','video-a']);assert.match(editor.element.textContent,/TikTok 영상 준비 · 실제 업로드·게시 아님/);assert.match(editor.element.textContent,/게시 방식 확인 대기/);
  inputValue(editor,'예정 시각 (예: 2026-11-01T10:00:00+09:00)','2026-11-04T10:00:00+09:00');await findButton(editor.element,'계획 미리보기').listeners.click();assert.equal(calls.length,0);
  inputValue(editor,'TikTok 준비용 영상 (MP4 1개)','video-a');selectConnection(editor,'dept.instagram');selectConnection(editor,'dept.tiktok');assert.equal(findInput(editor.element,'TikTok 준비용 영상 (MP4 1개)').value,'');
  inputValue(editor,'TikTok 준비용 영상 (MP4 1개)','video-a');await findButton(editor.element,'계획 미리보기').listeners.click();assert.match(editor.element.textContent,/선택 자산: video-a/);await findButton(editor.element,'로컬 계획 저장').listeners.click();assert.deepEqual(calls.map(x=>x[0]),['preview','save']);for(const [,body]of calls)assert.deepEqual(body.options,{tiktok:{asset_ids:['video-a']}});assert.deepEqual(source,before);
 }finally{restore();}
});
test('TikTok 준비 자산의 형식·선택·중복을 엄격히 검사하고 원본 갱신 시 선택을 비운다',async()=>{
 const draft={connection_id:'dept.tiktok',schedule_slot:'main',scheduled_at:'2026-11-04T10:00:00+09:00',tiktok_asset_id:'video-a'};
 for(const value of ['',true,['video-a'],'jpeg-a','missing'])assert.throws(()=>delivery.deliveryPayload(igContent,{...draft,tiktok_asset_id:value},ttConnection),/TikTok/);
 for(const change of [{size:true},{size:0},{sha256:'bad'},{media_type:'image/png'}])assert.throws(()=>delivery.deliveryPayload({...igContent,assets:igAssets.map(a=>a.id==='video-a'?{...a,...change}:a)},draft,ttConnection),/TikTok/);
 assert.throws(()=>delivery.deliveryPayload({...igContent,assets:[...igAssets,igAssets[2]]},draft,ttConnection),/TikTok/);
 const restore=useTestDocument();try{
  const source=structuredClone(igContent),editor=delivery.createDeliveryEditor({api:stubApi({listConnections:async()=>({items:[ttConnection]})}),writable:()=>true});await editor.open(source);selectConnection(editor,'dept.tiktok');inputValue(editor,'TikTok 준비용 영상 (MP4 1개)','video-a');source.assets=[];editor.refreshControls();assert.equal(findInput(editor.element,'TikTok 준비용 영상 (MP4 1개)').value,'');await editor.open({...source,revision:5});selectConnection(editor,'dept.tiktok');assert.equal(findInput(editor.element,'TikTok 준비용 영상 (MP4 1개)').value,'');
 }finally{restore();}
});
const igConnection={id:'dept.instagram',account_id:'dept',platform:'instagram',target_id:'123456',target_status:'verified',planning_enabled:true,auth_status:'unknown',capabilities:['plan','visibility:public']};
const igPlan={...selectedPlan,content_id:igContent.id,manifest_hash:igContent.manifest_hash,connection_id:igConnection.id,target_id:igConnection.target_id,platform:'instagram',target_label:'Instagram 구성',options:{instagram:{format:'image',asset_ids:['jpeg-a']}}};
const igChecks={rights_confirmed:false,visual_checked:false,caption_checked:false,composition_checked:false,audio_checked:false};
const igReview={plan_id:igPlan.id,content_id:igPlan.content_id,content_revision:igPlan.revision,manifest_hash:igPlan.manifest_hash,owner_account_id:igPlan.owner_account_id,destination_account_id:igPlan.destination_account_id,connection_id:igPlan.connection_id,target_id:igConnection.target_id,media_format:'image',caption:'고정 캡션',assets:[{id:'jpeg-a',sha256:'b'.repeat(64),size:20,media_type:'image/jpeg'}],subject_hash:'f'.repeat(64),review_revision:0,decision:null,checks:igChecks,notes:'',review_method:'manual',status:'not_reviewed',audio_required:false};
function igApi(extra={}){return stubApi({getContent:async()=>igContent,listConnections:async()=>({items:[igConnection]}),listDeliveries:async()=>({items:[igPlan]}),getDelivery:async()=>igPlan,deliveryEvents:async()=>({items:[]}),getInstagramReview:async()=>igReview,...extra});}
const reviewDetails=editor=>editor.element.querySelectorAll('details').find(n=>n.querySelector('summary')?.textContent==='Instagram 최종 구성 검토');
test('Instagram 선택은 자동 자산 없이 시작하며 형식·순서·MIME을 검증하고 연결 전환 시 지운다',async()=>{
 const restore=useTestDocument();try{
  const editor=delivery.createDeliveryEditor({api:igApi(),writable:()=>true});await editor.open(igContent);selectConnection(editor,'dept.instagram');assert.equal(findInput(editor.element,'Instagram 게시 형식').value,'');assert.equal(findInput(editor.element,'자산 ID 순서 (한 줄에 하나)').value,'');assert.match(editor.element.textContent,/jpeg-a · image\/jpeg/);assert.match(editor.element.textContent,/video-a · video\/mp4/);assert.doesNotMatch(editor.element.textContent,/png-a · image\/png/);
  assert.throws(()=>delivery.deliveryPayload(igContent,{connection_id:'dept.instagram',schedule_slot:'main',scheduled_at:'2026-11-02T10:00:00+09:00'},igConnection),/게시 형식/);
  const draft={connection_id:'dept.instagram',schedule_slot:'main',scheduled_at:'2026-11-02T10:00:00+09:00',instagram_format:'carousel',instagram_asset_ids:['video-a','jpeg-b']};assert.deepEqual(delivery.deliveryPayload(igContent,draft).options.instagram,{format:'carousel',asset_ids:['video-a','jpeg-b']});
  for(const change of [{instagram_format:'image',instagram_asset_ids:['video-a']},{instagram_format:'reels',instagram_asset_ids:['jpeg-a']},{instagram_format:'carousel',instagram_asset_ids:['jpeg-a','jpeg-a']},{instagram_format:'image',instagram_asset_ids:['png-a']}])assert.throws(()=>delivery.deliveryPayload(igContent,{...draft,...change}),/Instagram/);
  inputValue(editor,'Instagram 게시 형식','carousel');inputValue(editor,'자산 ID 순서 (한 줄에 하나)','jpeg-b\njpeg-a');selectConnection(editor,'');selectConnection(editor,'dept.instagram');assert.equal(findInput(editor.element,'Instagram 게시 형식').value,'');assert.equal(findInput(editor.element,'자산 ID 순서 (한 줄에 하나)').value,'');
 }finally{restore();}
});
test('Instagram 저장 계획을 선택해 펼칠 때만 최종 검토 GET하고 자식 초안이 부모 계획 전환을 막는다',async()=>{
 const restore=useTestDocument();try{
  let gets=0;const editor=delivery.createDeliveryEditor({api:igApi({getInstagramReview:async()=>{gets++;return igReview;}}),writable:()=>true});await editor.open(igContent);assert.equal(reviewDetails(editor),undefined);await editor.element.querySelectorAll('button').find(n=>n.textContent.includes('Instagram 구성')).listeners.click();const details=reviewDetails(editor);assert.ok(details);assert.equal(gets,0);details.open=true;await details.listeners.toggle();assert.equal(gets,1);
  const box=details.querySelector('[data-instagram-review-field]');box.checked=true;box.listeners.change({target:box});assert.equal(editor.hasUnsavedChanges(),true);assert.equal(findButton(editor.element,'새 계획 작성').disabled,true);await findButton(editor.element,'새 계획 작성').listeners.click();assert.ok(reviewDetails(editor));assert.equal(box.disabled,false);assert.equal(editor.element.querySelectorAll('button').find(n=>n.textContent==='이 버전 계획 승인').disabled,true);
  const discard=details.querySelectorAll('button').find(n=>n.textContent==='입력 버리기');discard.listeners.click();assert.equal(editor.hasUnsavedChanges(),false);assert.equal(findButton(editor.element,'새 계획 작성').disabled,false);
 }finally{restore();}
});
test('Instagram 최종 검토 초안과 처리 중 요청은 부모 원본 저장·업로드도 잠근다',async()=>{
 const restore=useTestDocument();try{
  const {createContentEditor}=await import('../ax-console/app/web/content_editor.js');let writes=0,finish;const api=igApi({updateContent:async()=>{writes++;return igContent;},recordInstagramReview:()=>new Promise(resolve=>finish=resolve)});const editor=createContentEditor({api,writable:()=>true});await editor.open(igContent);await tick();await editor.element.querySelectorAll('button').find(n=>n.textContent.includes('Instagram 구성')).listeners.click();const details=reviewDetails(editor);details.open=true;await details.listeners.toggle();
  for(const box of details.querySelectorAll('input')){box.checked=true;box.listeners.change({target:box});}assert.equal(editor.hasUnsavedChanges(),true);assert.equal(findButton(editor.element,'원본 저장').disabled,true);await editor.element.querySelector('form').listeners.submit({preventDefault(){}});assert.equal(writes,0);
  const saving=details.querySelectorAll('button').find(n=>n.textContent==='검토 확인 저장').listeners.click();await tick();assert.equal(editor.isBusy(),true);assert.equal(findButton(editor.element,'원본 저장').disabled,true);finish({...igReview,review_revision:1,decision:'approved',status:'approved',checks:{...igChecks,rights_confirmed:true,visual_checked:true,caption_checked:true,composition_checked:true}});await saving;assert.equal(editor.isBusy(),false);
 }finally{restore();}
});
test('Instagram 형식과 자산 순서는 미리보기·저장 계획에 표시되며 미확인 대상은 최종 검토를 열지 않는다',async()=>{
 const summary=delivery.deliveryPreviewSummary({...igPlan,options:{instagram:{format:'carousel',asset_ids:['jpeg-b','jpeg-a']}}}).join(' ');assert.match(summary,/Instagram 게시 형식: 캐러셀/);assert.match(summary,/jpeg-b → jpeg-a/);
 const restore=useTestDocument();try{
  let gets=0;const unverified={...igPlan,target_status:'unverified'};const editor=delivery.createDeliveryEditor({api:igApi({getDelivery:async()=>unverified,listConnections:async()=>({items:[{...igConnection,target_id:null,target_status:'unverified'}]}),getInstagramReview:async()=>{gets++;return igReview;}}),writable:()=>true});await editor.open(igContent);await editor.element.querySelectorAll('button').find(n=>n.textContent.includes('Instagram 구성')).listeners.click();assert.match(editor.element.textContent,/Instagram 게시 형식: 이미지/);const details=reviewDetails(editor);details.open=true;await details.listeners.toggle();assert.equal(gets,0);assert.match(details.textContent,/게시 대상/);
 }finally{restore();}
});

test('Instagram 자식 검토 입력은 부모 refresh에서도 같은 DOM·포커스·선택 범위를 유지한다',async()=>{
 const old=globalThis.document;const {harness}=await import('./helpers/execution_dom.mjs');const {document}=harness();globalThis.document=document;
 try{
  const editor=delivery.createDeliveryEditor({api:igApi(),writable:()=>true});await editor.open(igContent);await editor.element.querySelectorAll('button').find(n=>n.textContent.includes('Instagram 구성')).fire('click');const details=reviewDetails(editor);details.open=true;await details.fire('toggle');
  const notes=details.querySelector('textarea');notes.focus();notes.value='보존할 검토 입력';notes.selectionStart=2;notes.selectionEnd=4;await notes.fire('input');editor.refreshControls();assert.equal(document.activeElement,notes);assert.equal(reviewDetails(editor).querySelector('textarea'),notes);assert.equal(notes.value,'보존할 검토 입력');assert.equal(notes.selectionStart,2);assert.equal(notes.selectionEnd,4);assert.equal(notes.disabled,false);assert.equal(findButton(editor.element,'새 계획 작성').disabled,true);
 }finally{globalThis.document=old;}
});
