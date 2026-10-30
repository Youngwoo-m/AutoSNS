import test from 'node:test';
import assert from 'node:assert/strict';

const module = await import('../ax-console/app/web/execution_panel.js').catch(error => {
  if (error.code !== 'ERR_MODULE_NOT_FOUND') throw error;
  return {};
});
const renderExecutionPanel = (...args) => {
  assert.equal(typeof module.renderExecutionPanel, 'function', '실행 패널 렌더러가 필요합니다.');
  return module.renderExecutionPanel(...args);
};
const bindExecutionPanel = (...args) => {
  assert.equal(typeof module.bindExecutionPanel, 'function', '실행 패널 바인더가 필요합니다.');
  return module.bindExecutionPanel(...args);
};

// Phase5의 createElement 기반 Node 하네스에 포커스/리스너 해제만 보탠다.
function harness() {
  const document = {activeElement:null, createElement:tag => new Node(tag)};
  class Node {
    constructor(tag) { this.tagName=tag; this.children=[]; this.listeners=new Map(); this.attrs={}; this.style={}; this._text=''; this.value=''; this.disabled=false; this.ownerDocument=document; }
    set textContent(value) { this._text=String(value); this.children=[]; }
    get textContent() { return this._text+this.children.map(child=>child.textContent).join(''); }
    set innerHTML(_) { throw new Error('innerHTML 금지'); }
    set outerHTML(_) { throw new Error('outerHTML 금지'); }
    insertAdjacentHTML() { throw new Error('insertAdjacentHTML 금지'); }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { if(this.contains(document.activeElement))document.activeElement=null; this._text='';this.children=children; }
    setAttribute(key,value) { assert.ok(!/^on/i.test(key)); this.attrs[key]=String(value); }
    getAttribute(key) { return this.attrs[key]??null; }
    addEventListener(type,fn) { if(!this.listeners.has(type))this.listeners.set(type,new Set());this.listeners.get(type).add(fn); }
    removeEventListener(type,fn) { this.listeners.get(type)?.delete(fn); }
    contains(target) { return this===target||this.children.some(child=>child.contains(target)); }
    focus() { document.activeElement=this; }
    async fire(type,extra={}) { if(this.disabled)return; const event={target:this,preventDefault(){this.defaultPrevented=true;},...extra};for(const fn of this.listeners.get(type)||[])await fn(event);return event; }
  }
  return {document};
}
const all=node=>[node,...node.children.flatMap(all)];
const action=(root,name)=>all(root).find(node=>node.getAttribute('data-execution-action')===name);
const field=(root,name)=>all(root).find(node=>node.name===name);
const fixture=(extra={})=>({enabled:true,capabilities:Object.fromEntries(['request','refresh','observe','admit','approve'].map(name=>[name,{available:true}])),content:{id:'content-1',revision:4,manifest_hash:'hash-4',title:'선택한 원고',original:'저장된 원고',assets:[]},trigger:{job_id:'production.base',scheduled_at_utc:'2026-10-31T00:00:00Z',phase:'prepare',source:'console',request_kind:'new_publication',mode:'live'},run:{run_id:'run-1',state:'queued',binding_id:'binding-1',content_id:'content-1',content_revision:4,manifest_hash:'hash-4'},delivery:{id:'delivery-1',version:2,run_id:'run-1',context_hash:'context-1',observation_id:'observation-1',state:'queued'},draft:{publication_confirmed:false},pending:{},...extra});
function opened(state=fixture(),controller={}) { const {document}=harness();const root=renderExecutionPanel(state,{document});const cleanup=bindExecutionPanel(root,controller);return {root,state,document,cleanup}; }

test('test_disabled_reason_visible: 기본 비활성과 capability 불가 이유를 표시하고 호출을 막는다',async()=>{
  const state=fixture({enabled:false,disabled_reason:'운영 실행이 꺼져 있습니다.',capabilities:{request:{available:false,reason:'제작 서비스 미연결'}}});
  let calls=0;const {root}=opened(state,{request:async()=>calls++});
  assert.match(root.textContent,/운영 실행이 꺼져 있습니다/);assert.match(root.textContent,/제작 서비스 미연결/);
  for(const name of ['request','observe','admit','approve'])assert.equal(action(root,name).disabled,true);
  await action(root,'request').fire('click');assert.equal(calls,0);
});

test('test_queued_is_not_published: 접수·제작 완료·공개 확인과 한도·로그인·미지원을 구분한다',()=>{
  const {document}=harness();
  for(const [state,label] of [['queued','접수 대기'],['completed','실행 완료'],['published','공개 게시 확인'],['quota_exceeded','한도 초과'],['needs_auth','로그인 필요'],['unsupported','미지원'],['unknown','게시 여부 불확실']]) {
    const root=renderExecutionPanel(fixture({run:{run_id:'r',state},delivery:null}),{document});
    assert.match(root.textContent,new RegExp(label));
    if(state==='queued'||state==='completed')assert.doesNotMatch(root.textContent,/공개 게시 확인/);
  }
});

test('prepare는 연 상세의 정확한 content/revision과 trigger 6필드만 접수하며 응답 바인딩을 표시한다',async()=>{
  const sent=[];const state=fixture({run:null,delivery:null});state.trigger.owner='금지';state.trigger.production_unit_id='금지';
  const {root}=opened(state,{request:async body=>{sent.push(body);return {run_id:'new-run',state:'queued',binding_id:'frozen-binding',content_id:'content-1',content_revision:4,manifest_hash:'frozen-hash'};}});
  await action(root,'request').fire('click');
  assert.deepEqual(sent,[{trigger:{job_id:'production.base',scheduled_at_utc:'2026-10-31T00:00:00Z',phase:'prepare',source:'console',request_kind:'new_publication',mode:'live'},content_id:'content-1',expected_revision:4}]);
  assert.match(root.textContent,/frozen-binding/);assert.match(root.textContent,/frozen-hash/);assert.match(root.textContent,/동결 원고 버전: 4/);assert.equal(state.pending.request,undefined);
});

test('제작 외 phase는 원고를 자동 선택하지 않고 content_id와 revision을 null로 보낸다',async()=>{
  const state=fixture({run:null,delivery:null});state.trigger.phase='verify';let body;
  const {root}=opened(state,{request:async value=>{body=value;return {run_id:'verify-run',state:'queued'};}});
  await action(root,'request').fire('click');assert.equal(body.content_id,null);assert.equal(body.expected_revision,null);
});

for(const status of [401,409,503])test(`test_401_conflict_retains_inputs_and_request_key: 승인 ${status}는 확인 입력·CAS·키를 보존한다`,async()=>{
  const sent=[];let reject;const state=fixture();const {root}=opened(state,{approve:async(id,body)=>{sent.push({id,...body});return new Promise((_,fail)=>reject=fail);}});
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');
  const first=action(root,'approve').fire('click');await action(root,'approve').fire('click');assert.equal(sent.length,1);
  reject(Object.assign(new Error('<img onerror=bad>'),{status}));await first;
  assert.equal(field(root,'publication_confirmed').checked,true);assert.match(root.textContent,/보존/);
  assert.match(root.textContent,new RegExp(status===401?'인증':status===409?'변경':'사용할 수 없'));
  state.delivery.version=9;state.delivery.context_hash='changed-context';
  const second=action(root,'approve').fire('click');assert.deepEqual(sent[1],sent[0]);
  assert.deepEqual(Object.keys(sent[0]).sort(),['context_hash','expected_version','id','request_key']);assert.equal(typeof sent[0].request_key,'string');
  reject(Object.assign(new Error(),{status}));await second;
  assert.equal(state.pending.approve.body.expected_version,2);
});

test('별도 발행 승인 확인 전에는 승인하지 않고 기획 승인으로 승인 입력을 만들지 않는다',async()=>{
  const state=fixture({planning_approved:true});let calls=0;const {root}=opened(state,{approve:async()=>calls++});
  assert.equal(action(root,'approve').disabled,true);await action(root,'approve').fire('click');assert.equal(calls,0);
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');await action(root,'approve').fire('click');assert.equal(calls,1);
});

test('관측·admit는 엄격한 서버 계약만 보내고 상태 조회는 자동 실행하지 않는다',async()=>{
  const sent=[];const {root}=opened(fixture(),{getRun:async id=>{sent.push(['refresh',id]);return {run_id:id,state:'completed'};},observe:async(id,body)=>{sent.push(['observe',id,body]);return {observation_id:'fresh-observation'};},admit:async(id,body)=>{sent.push(['admit',id,body]);return {id,version:3,context_hash:'current-context',state:'awaiting_approval'};}});
  assert.equal(sent.length,0);await action(root,'observe').fire('click');await action(root,'admit').fire('click');await action(root,'refresh').fire('click');
  assert.deepEqual(sent,[['observe','delivery-1',{run_id:'run-1',expected_version:2}],['admit','delivery-1',{run_id:'run-1',expected_version:2,observation_id:'fresh-observation'}],['refresh','run-1']]);
});

test('원고 버전·해시 변경은 동결 표시를 바꾸지 않고 기존 배포 조치를 막는다',async()=>{
  const state=fixture();state.content.revision=5;state.content.manifest_hash='hash-5';let calls=0;const {root}=opened(state,{observe:async()=>calls++,admit:async()=>calls++,approve:async()=>calls++});
  assert.match(root.textContent,/동결 원고 버전: 4/);assert.match(root.textContent,/hash-4/);assert.match(root.textContent,/별도 제작 요청/);
  for(const name of ['observe','admit','approve']){assert.equal(action(root,name).disabled,true);await action(root,name).fire('click');}assert.equal(calls,0);
});

test('test_keyboard_focus_and_320px_layout: 네이티브 버튼·라벨·줄바꿈, Escape 및 비동기 포커스 보존',async()=>{
  const {root,document}=opened(fixture(),{getRun:async id=>({run_id:id,state:'queued'})});
  assert.equal(root.style.minWidth,'0');assert.equal(root.style.maxWidth,'100%');assert.equal(root.style.overflowWrap,'anywhere');
  for(const node of all(root).filter(n=>['button','input','textarea','a'].includes(n.tagName)))assert.equal(node.style.maxWidth,'100%');
  const confirm=field(root,'publication_confirmed');assert.ok(all(root).some(n=>n.tagName==='label'&&n.contains(confirm)));
  action(root,'refresh').focus();await action(root,'refresh').fire('click');assert.equal(document.activeElement,action(root,'refresh'));
  const detail=all(root).find(n=>n.tagName==='details');detail.open=true;const event=await detail.fire('keydown',{key:'Escape'});
  assert.equal(detail.open,false);assert.equal(document.activeElement,detail.children[0]);assert.equal(event.defaultPrevented,true);
  const status=all(root).find(n=>n.getAttribute('role')==='status');assert.equal(status.getAttribute('aria-live'),'polite');
});

test('외부로 이동한 포커스는 요청 완료가 가져오지 않으며 cleanup 뒤 늦은 응답은 무시한다',async()=>{
  let finish;const state=fixture();const {root,document,cleanup}=opened(state,{getRun:id=>new Promise(resolve=>finish=()=>resolve({run_id:id,state:'published'}))});
  const first=action(root,'refresh').fire('click');const outside=document.createElement('input');outside.focus();cleanup();finish();await first;
  assert.equal(document.activeElement,outside);assert.equal(state.run.state,'queued');await action(root,'refresh').fire('click');assert.equal(state.busy,false);
});

test('test_untrusted_text_is_text_and_unsafe_media_urls_rejected: 원고·파일명·오류는 텍스트, 자산 endpoint만 링크한다',()=>{
  const attack='<img src=x onerror=alert(1)>';const state=fixture({error:{status:409,message:attack},nonce:'SECRET_NONCE',credential:'SECRET_CREDENTIAL',path:'/private/key'});
  state.content.title=attack;state.content.original=attack;state.content.assets=[{id:'asset-1',filename:attack,url:'javascript:alert(1)',media_type:'image/png'},{filename:'unsafe',url:'data:image/png,x'},{filename:'unsafe-file',url:'file:///private/key'},{filename:'remote',url:'https://evil.example/x.png'},{id:'../escape',filename:'unsafe-id'}];
  const {document}=harness();const root=renderExecutionPanel(state,{document});assert.equal(root.textContent.split(attack).length-1,4);
  assert.equal(all(root).filter(n=>['img','script','iframe','video','audio'].includes(n.tagName)).length,0);
  const links=all(root).filter(n=>n.tagName==='a');assert.equal(links.length,1);assert.equal(links[0].getAttribute('href'),'/api/v2/contents/content-1/revisions/4/assets/asset-1');
  assert.doesNotMatch(root.textContent,/SECRET_NONCE|SECRET_CREDENTIAL|\/private\/key/);
  for(const node of all(root))for(const [key,value] of Object.entries(node.attrs)){assert.ok(!/^on/i.test(key));if(key==='href'||key==='src')assert.ok(!/^(javascript:|data:|file:|https?:)/i.test(value));}
});

test('조회 응답의 다른 바인딩·원고 버전은 이미 동결된 입력을 대체하지 않는다',async()=>{
  const state=fixture();const {root}=opened(state,{getRun:async()=>({run_id:'run-1',state:'completed',binding_id:'wrong-binding',content_id:'wrong-content',content_revision:99,manifest_hash:'wrong-hash',credential:'SECRET'})});
  await action(root,'refresh').fire('click');assert.equal(state.run.state,'completed');assert.equal(state.run.binding_id,'binding-1');assert.equal(state.run.content_revision,4);assert.equal(state.run.manifest_hash,'hash-4');assert.equal(state.run.credential,undefined);assert.doesNotMatch(root.textContent,/wrong-binding|wrong-hash|SECRET/);
});

test('승인 성공은 pending만 완료 처리하며 queued 결과를 공개 완료로 바꾸지 않는다',async()=>{
  const state=fixture();const {root}=opened(state,{approve:async id=>({id,version:3,state:'queued',credential:'SECRET'})});
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');await action(root,'approve').fire('click');
  assert.equal(state.pending.approve,undefined);assert.equal(state.delivery.version,3);assert.equal(state.delivery.state,'queued');assert.equal(state.draft.publication_confirmed,false);assert.doesNotMatch(root.textContent,/공개 게시 확인|SECRET/);
});

for(const status of [401,409,503])test(`제작 ${status} 재시도는 선택 입력과 원래 trigger 본문을 유지하고 callback의 변경을 격리한다`,async()=>{
  const state=fixture({run:null,delivery:null});const sent=[];const {root}=opened(state,{request:async body=>{sent.push(structuredClone(body));body.trigger.job_id='callback-mutation';throw Object.assign(new Error(),{status});}});
  await action(root,'request').fire('click');state.trigger.scheduled_at_utc='2026-11-01T00:00:00Z';await action(root,'request').fire('click');
  assert.deepEqual(sent[1],sent[0]);assert.equal(state.content.revision,4);assert.equal(state.pending.request.body.trigger.job_id,'production.base');assert.equal(state.trigger.scheduled_at_utc,'2026-11-01T00:00:00Z');
});

test('320px 준비 화면에서도 원고 ID나 저장 버전이 없으면 임의 최신 원고 제작을 요청하지 않는다',()=>{
  for(const content of [null,{id:'content-1'},{id:'../escape',revision:4},{id:'content-1',revision:0}]) {
    const {root}=opened(fixture({content,run:null,delivery:null}),{request:async()=>{throw new Error('호출 금지');}});assert.equal(action(root,'request').disabled,true);
  }
});

test('체크한 대상·발행 의도·버전이 바뀌면 새 승인 전 다시 직접 확인한다',async()=>{
  const state=fixture();let calls=0;let {root,cleanup}=opened(state,{approve:async id=>{calls++;return {id,version:3,state:'queued'};}});
  let confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');cleanup();
  state.delivery={...state.delivery,id:'other-delivery',context_hash:'other-context'};
  ({root}=opened(state,{approve:async()=>calls++}));assert.equal(field(root,'publication_confirmed').checked,true);assert.equal(action(root,'approve').disabled,true);await action(root,'approve').fire('click');assert.equal(calls,0);
});

test('조회 중 외부로 이동한 포커스는 정상 완료에도 그대로 유지한다',async()=>{
  let finish;const {root,document}=opened(fixture(),{getRun:id=>new Promise(resolve=>finish=()=>resolve({run_id:id,state:'completed'}))});
  action(root,'refresh').focus();const pending=action(root,'refresh').fire('click');const outside=document.createElement('input');outside.focus();finish();await pending;assert.equal(document.activeElement,outside);
});

for(const [old,next] of [[{state:'queued'},{status:'completed'}],[{status:'queued'},{state:'needs_auth'}]])test(`I1 실행 상태 별칭 전환 ${Object.keys(old)[0]}→${Object.keys(next)[0]}은 최신 상태 하나만 표시한다`,async()=>{
  const state=fixture({run:{run_id:'run-1',...old},delivery:null});const {root}=opened(state,{getRun:async()=>({run_id:'run-1',...next})});
  await action(root,'refresh').fire('click');assert.equal(state.run.state,Object.values(next)[0]);assert.equal(state.run.status,undefined);
  assert.match(root.textContent,new RegExp(Object.values(next)[0]==='completed'?'실행 완료':'로그인 필요'));assert.doesNotMatch(root.textContent,/접수 대기/);
});

for(const [old,next] of [[{execution_state:'queued'},{state:'published'}],[{state:'queued'},{execution_state:'unknown'}]])test(`I1 승인 결과 별칭 전환 ${Object.keys(old)[0]}→${Object.keys(next)[0]}은 이전 배포 상태를 남기지 않는다`,async()=>{
  const state=fixture();delete state.delivery.state;Object.assign(state.delivery,old);const {root}=opened(state,{approve:async id=>({id,version:3,...next})});
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');await action(root,'approve').fire('click');
  assert.equal(state.delivery.state,Object.values(next)[0]);assert.equal(state.delivery.execution_state,undefined);assert.equal(state.error,null);
  const delivery=all(root).find(node=>node.tagName==='p'&&node.textContent.startsWith('배포: '));assert.match(delivery.textContent,new RegExp(Object.values(next)[0]==='published'?'공개 게시 확인':'게시 여부 불확실'));assert.doesNotMatch(delivery.textContent,/접수 대기/);
});

for(const response of [{id:'delivery-1',version:3},{id:'delivery-1',version:3,context_hash:''},{id:'delivery-1',version:3,context_hash:null},{id:'delivery-1',version:-1,context_hash:'new-context'}])test(`I2 잘못된 admit 응답 ${JSON.stringify(response)}는 기존 승인 문맥과 pending을 보존한다`,async()=>{
  const state=fixture();const sent=[];const {root}=opened(state,{admit:async(id,body)=>{sent.push({id,...body});return response;}});
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');const previousDelivery=structuredClone(state.delivery),previousDraft=structuredClone(state.draft);
  await action(root,'admit').fire('click');assert.deepEqual(state.delivery,previousDelivery);assert.deepEqual(state.draft,previousDraft);assert.ok(state.pending.admit);assert.equal(state.error?.status,503);assert.match(root.textContent,/서비스를 사용할 수 없.*보존/);
  await action(root,'admit').fire('click');assert.deepEqual(sent[1],sent[0]);assert.deepEqual(state.delivery,previousDelivery);
});

for(const response of [{id:'delivery-1',version:3},{id:'delivery-1',version:3,state:''},{id:'delivery-1',version:3,execution_state:null},{id:'delivery-1',version:3,state:'queued',execution_state:'published'},{id:'delivery-1',version:-1,state:'published'}])test(`I2 잘못된 approve 응답 ${JSON.stringify(response)}는 확인 입력과 동일 요청키를 보존한다`,async()=>{
  const state=fixture();const sent=[];const {root}=opened(state,{approve:async(id,body)=>{sent.push({id,...body});return response;}});
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');const previousDelivery=structuredClone(state.delivery),previousDraft=structuredClone(state.draft);
  await action(root,'approve').fire('click');assert.deepEqual(state.delivery,previousDelivery);assert.deepEqual(state.draft,previousDraft);assert.ok(state.pending.approve);assert.equal(state.error?.status,503);assert.equal(field(root,'publication_confirmed').checked,true);
  await action(root,'approve').fire('click');assert.deepEqual(sent[1],sent[0]);assert.equal(state.pending.approve.body.context_hash,'context-1');assert.equal(state.pending.approve.body.expected_version,2);
});

for(const response of [{run_id:'run-1'},{run_id:'run-1',status:''},{run_id:'run-1',state:null},{run_id:'run-1',state:'queued',status:'completed'}])test(`I2 잘못된 refresh 응답 ${JSON.stringify(response)}는 기존 상태를 그대로 보존한다`,async()=>{
  const state=fixture();const previousRun=structuredClone(state.run);const {root}=opened(state,{getRun:async()=>response});
  await action(root,'refresh').fire('click');assert.deepEqual(state.run,previousRun);assert.equal(state.error?.status,503);assert.match(root.textContent,/서비스를 사용할 수 없/);
});

test('I2 유효한 admit 최소 응답은 새 context hash와 CAS만 반영하고 새 승인에는 다시 확인을 요구한다',async()=>{
  const state=fixture();const {root}=opened(state,{admit:async id=>({id,version:3,context_hash:'new-context'}),approve:async id=>({id,version:4,state:'queued'})});
  const confirm=field(root,'publication_confirmed');confirm.checked=true;await confirm.fire('change');await action(root,'admit').fire('click');
  assert.equal(state.delivery.context_hash,'new-context');assert.equal(state.delivery.version,3);assert.equal(state.pending.admit,undefined);assert.equal(state.error,null);assert.equal(action(root,'approve').disabled,true);
});
