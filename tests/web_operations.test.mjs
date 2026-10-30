import test from 'node:test';
import assert from 'node:assert/strict';
import {createOperationsApi,createOperationsPanel} from '../ax-console/app/web/operations_panel.js';
class Node {
  constructor(tag){this.tagName=tag;this.children=[];this.listeners={};this.value='';this.disabled=false;this._text='';}
  set textContent(v){this._text=String(v);this.children=[];} get textContent(){return this._text+this.children.map(x=>x.textContent).join('');}
  append(...nodes){this.children.push(...nodes);} replaceChildren(...nodes){this._text='';this.children=nodes;}
  setAttribute(k,v){this[k]=v;} addEventListener(type,fn){this.listeners[type]=fn;}
  async fire(type){if(!this.disabled)return this.listeners[type]?.({preventDefault(){}});}
}
const document={createElement:tag=>new Node(tag)};
const all=n=>[n,...n.children.flatMap(all)];
const find=(n,text)=>all(n).find(x=>x.tagName==='button'&&x.textContent===text);
const field=(n,name)=>all(n).find(x=>x.name===name);
const item=(id='delivery',extra={})=>({id,content_id:'content',owner_account_id:'personal',destination_account_id:'dept',connection_id:'main',platform:'youtube',plan_status:'approved',execution_state:'unknown',version:2,available_actions:['resolve'],attempts:[],evidence:[],blockers:[],execution_enabled:false,...extra});
const listing=(items=[item()])=>({items,summary:{active:1,completed:0,partial:0,waiting:1},control:{global:{state:'clear',version:0,read_only:true},managed:[]},execution_enabled:false,blockers:[]});
const apiFor=(extra={})=>({list:async()=>listing(),get:async id=>item(id),...extra});
async function opened(api=apiFor()){const panel=createOperationsPanel({api,document});await panel.load('all');await find(panel.render(),'상세 · delivery').fire('click');return panel;}
async function fill(panel){let root=panel.render();field(root,'evidence').value='{"remote_id":"post-1"}';await field(root,'evidence').fire('input');field(root,'note').value='검토 완료';await field(root,'note').fire('input');}
test('API는 same-origin 인증과 명시적 경로를 사용하고 오류 status를 보존한다',async()=>{
 const calls=[];const api=createOperationsApi({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>listing()};}});
 await api.list('dept');await api.resolve('a/b',{expected_version:2});
 assert.equal(calls[0].url,'/api/v2/operations?account=dept');assert.equal(calls[0].options.credentials,'same-origin');assert.equal(calls[1].url,'/api/v2/operations/a%2Fb/resolve');assert.equal(calls[1].options.method,'POST');
 await assert.rejects(api.list('invalid'),/계정/);
 const bad=createOperationsApi({fetcher:async()=>({ok:false,status:401})});await assert.rejects(bad.get('d'),e=>e.status===401);
});
test('계정 변경 후 늦은 목록은 무시한다',async()=>{
 const pending=[];const panel=createOperationsPanel({document,api:apiFor({list:account=>new Promise(resolve=>pending.push({account,resolve}))})});
 const a=panel.load('dept'),b=panel.load('personal');pending[1].resolve(listing([item('personal')]));await b;pending[0].resolve(listing([item('dept')]));await a;
 assert.match(panel.render().textContent,/personal/);assert.doesNotMatch(panel.render().textContent,/상세 · dept/);
});
for(const status of [409,401,503])test(`${status} 복구 실패는 입력·버전·요청키를 보존한다`,async()=>{
 const sent=[];const panel=await opened(apiFor({resolve:async(id,body)=>{sent.push(body);throw Object.assign(new Error('unsafe detail'),{status});}}));await fill(panel);
 await all(panel.render()).find(x=>x.tagName==='form').fire('submit');assert.equal(panel.isDirty(),true);assert.equal(field(panel.render(),'note').value,'검토 완료');assert.match(panel.render().textContent,/보존/);
 await all(panel.render()).find(x=>x.tagName==='form').fire('submit');assert.equal(sent[0].request_key,sent[1].request_key);assert.equal(sent[0].expected_version,2);assert.deepEqual(Object.keys(sent[0]).sort(),['evidence','expected_version','kind','note','request_key']);assert.deepEqual(sent[0].evidence,{remote_id:'post-1'});
});
test('기본 retry/reconcile 비활성 및 근거 텍스트 안전 표시',async()=>{
 let called=0;const panel=await opened(apiFor({get:async()=>item('delivery',{available_actions:[],evidence:[{kind:'lookup',note:'<img src=x onerror=alert(1)>',url:'javascript:alert(1)',token:'TOPSECRET'}]}),retry:async()=>called++,reconcile:async()=>called++}));
 const root=panel.render();await find(root,'상태 다시 조회').fire('click');await find(root,'동일 실행 재개').fire('click');assert.equal(called,0);assert.match(root.textContent,/<img/);assert.doesNotMatch(root.textContent,/TOPSECRET/);assert.equal(all(root).filter(x=>x.tagName==='a').length,0);
});
test('재조회는 draft를 유지하고 discard만 입력을 버린다',async()=>{
 const panel=await opened();await fill(panel);await panel.load('all');assert.equal(field(panel.render(),'note').value,'검토 완료');assert.equal(panel.isDirty(),true);panel.discard();assert.equal(panel.isDirty(),false);
});
test('today/accounts는 관리 실행과 legacy STOP 적용 범위를 구분한다',async()=>{
 const calls=[];const panel=createOperationsPanel({document,api:apiFor({list:async()=>({...listing(),control:{global:{state:'stopped',read_only:true},managed:[{scope:'account',id:'dept',state:'running',version:3,available_actions:['pause']}]}}),control:async body=>{calls.push(body);return {};}})});await panel.load('all');
 assert.match(panel.render('today').textContent,/관리 실행/);let root=panel.render('accounts');assert.match(root.textContent,/기존.*STOP/);assert.match(root.textContent,/로컬/);field(root,'reason-account-dept').value='점검';await field(root,'reason-account-dept').fire('input');await find(panel.render('accounts'),'관리 일시중지 · dept').fire('click');assert.equal(calls.length,1);assert.equal(calls[0].scope,'account');assert.equal(calls[0].expected_version,3);assert.equal(calls[0].action,'pause');
});
test('다른 상세 선택은 미저장 입력을 버리지 않으며 계정 변경 후 늦은 상세는 폐기한다',async()=>{
 let getCount=0,finish;const panel=createOperationsPanel({document,api:apiFor({list:async()=>listing([item('one'),item('two')]),get:id=>{getCount++;return id==='two'?new Promise(resolve=>finish=resolve):Promise.resolve(item(id));}})});await panel.load('all');await find(panel.render(),'상세 · one').fire('click');await fill(panel);await find(panel.render(),'상세 · two').fire('click');assert.equal(getCount,1);assert.equal(field(panel.render(),'note').value,'검토 완료');panel.discard();const late=find(panel.render(),'상세 · two').fire('click');await panel.load('dept');finish(item('two'));await late;assert.equal(field(panel.render(),'note'),undefined);
});
test('resolve 성공이 별도 관리 제어 사유를 지우거나 dirty를 해제하지 않는다',async()=>{
 const panel=createOperationsPanel({document,api:apiFor({list:async()=>({...listing(),control:{global:{state:'clear'},managed:[{scope:'account',id:'dept',state:'running',version:3,available_actions:['pause']}]}}),resolve:async()=>({})})});await panel.load('all');await find(panel.render(),'상세 · delivery').fire('click');await fill(panel);const reason=field(panel.render('accounts'),'reason-account-dept');reason.value='아직 저장하지 않은 제어 사유';await reason.fire('input');await all(panel.render()).find(x=>x.tagName==='form').fire('submit');assert.equal(panel.isDirty(),true);assert.equal(field(panel.render('accounts'),'reason-account-dept').value,'아직 저장하지 않은 제어 사유');
});
test('충돌 후 명시적 최신 버전 확인만 CAS 버전과 요청키를 갱신한다',async()=>{
 let version=2;const sent=[];const panel=await opened(apiFor({get:async()=>item('delivery',{version}),resolve:async(id,body)=>{sent.push(body);throw Object.assign(new Error(),{status:409});}}));await fill(panel);await all(panel.render()).find(x=>x.tagName==='form').fire('submit');version=9;await panel.load('all');assert.equal(field(panel.render(),'note').value,'검토 완료');await find(panel.render(),'내 입력을 유지하고 최신 버전 확인').fire('click');await all(panel.render()).find(x=>x.tagName==='form').fire('submit');assert.equal(sent[1].expected_version,9);assert.notEqual(sent[0].request_key,sent[1].request_key);assert.equal(sent[1].note,'검토 완료');
});
test('관리 제어 409는 사유·요청키를 보존하며 명시적 버전 확인 후 재시도한다',async()=>{
 let version=3;const sent=[];const panel=createOperationsPanel({document,api:apiFor({list:async()=>({...listing(),control:{global:{state:'clear'},managed:[{scope:'account',id:'dept',state:'running',version,available_actions:['pause']}]}}),control:async body=>{sent.push(body);throw Object.assign(new Error(),{status:409});}})});await panel.load();const reason=field(panel.render('accounts'),'reason-account-dept');reason.value='확인 필요';await reason.fire('input');await find(panel.render('accounts'),'관리 일시중지 · dept').fire('click');await find(panel.render('accounts'),'관리 일시중지 · dept').fire('click');assert.equal(sent[0].request_key,sent[1].request_key);version=7;await find(panel.render('accounts'),'제어 최신 버전 확인 · dept').fire('click');await find(panel.render('accounts'),'관리 일시중지 · dept').fire('click');assert.equal(sent[2].expected_version,7);assert.equal(sent[2].reason,'확인 필요');assert.notEqual(sent[0].request_key,sent[2].request_key);
});
