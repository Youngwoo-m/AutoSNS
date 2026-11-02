import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createMediaPlanPanel} from '../ax-console/app/web/media_plan_panel.js';

const content=(over={})=>({id:'c/1',revision:3,manifest_hash:'h'.repeat(64),owner_account_id:'acct-a',title:'원고',series:'시리즈',assets:[
  {id:'img1',filename:'a.png',media_type:'image/png'},{id:'img2',filename:'b.webp',media_type:'image/webp'},
  {id:'wav1',filename:'v.wav',media_type:'audio/wav'},{id:'mp3',filename:'v.mp3',media_type:'audio/mpeg'}],...over});
const plan=(over={})=>({exam:'시험',field:'분야',source:'',footer:'',disclosure:'AI 합성 음성 · 검토 전',voice_asset_id:null,scenes:[],...over});
const row=(c,over={})=>({content_id:c.id,content_revision:c.revision,manifest_hash:c.manifest_hash,owner_account_id:c.owner_account_id,plan_revision:0,plan:plan(),inputs_ready:false,blockers:['voice_required','scenes_required'],execution_enabled:false,review_status:'not_checked',...over});
const res=(status,body)=>({ok:status<400,status,json:async()=>body});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const by=(root,attr,value)=>all(root).filter(n=>n.getAttribute(attr)===value);
const action=(root,name)=>by(root,'data-media-plan-action',name)[0];
const setup=(fetcher)=>{const {document}=harness();const changes=[];const panel=createMediaPlanPanel({document,fetcher,onChange:()=>changes.push(1)});return {panel,changes};};
const inputs=root=>all(root).filter(n=>n.tagName==='input'||n.tagName==='textarea'||n.tagName==='select');

test('열기는 GET만 하고 원고 snapshot을 바꾸지 않으며 응답 전에는 계획을 만들지 않는다',async()=>{
  const c=content();const before=JSON.stringify(c);const gate=deferred();const calls=[];
  const {panel}=setup((url,init)=>{calls.push([url,init]);return gate.promise;});
  const opening=panel.open(c);
  assert.equal(inputs(panel.element).length,0);
  assert.equal(action(panel.element,'save'),undefined);
  assert.equal(panel.isBusy(),true);
  gate.resolve(res(200,row(c)));await opening;
  assert.equal(calls.length,1);
  assert.equal(calls[0][0],'/api/v2/contents/c%2F1/media-plan?revision=3');
  assert.equal(calls[0][1].method,'GET');assert.equal(calls[0][1].body,undefined);
  assert.equal(JSON.stringify(c),before);assert.equal(panel.isDirty(),false);
  assert.match(panel.element.textContent,/숏츠 제작 계획/);assert.match(panel.element.textContent,/원고 버전 3 · 소유 계정 acct-a/);
});

test('저장은 expected_revision과 plan만 POST하고 응답 revision으로 CAS를 이어간다',async()=>{
  const c=content();const calls=[];let rev=0;
  const {panel}=setup(async(url,init)=>{calls.push([url,init]);if(init.method==='GET')return res(200,row(c));rev+=1;const body=JSON.parse(init.body);return res(200,row(c,{plan_revision:rev,plan:body.plan}));});
  await panel.open(c);
  const exam=inputs(panel.element)[0];exam.value='새 시험';await exam.fire('input');
  assert.equal(panel.isDirty(),true);
  await action(panel.element,'add-scene').fire('click');
  assert.equal(by(panel.element,'data-media-plan-scene','0').length,1);
  await action(panel.element,'save').fire('click');
  const post=calls.find(([,i])=>i.method==='POST');
  const body=JSON.parse(post[1].body);
  assert.deepEqual(Object.keys(body),['expected_revision','plan']);
  assert.equal(body.expected_revision,0);assert.equal(body.plan.exam,'새 시험');
  assert.deepEqual(Object.keys(body.plan),['exam','field','source','footer','disclosure','voice_asset_id','scenes']);
  assert.deepEqual(Object.keys(body.plan.scenes[0]),['asset_id','kind','seconds','title','caption']);
  assert.equal(body.plan.scenes[0].asset_id,'img1');
  assert.equal(panel.isDirty(),false);assert.equal(panel.isBusy(),false);
  await action(panel.element,'save').fire('click');
  assert.equal(JSON.parse(calls.at(-1)[1].body).expected_revision,1);
});

test('409와 401은 입력을 보존하고 메시지만 보인다',async()=>{
  const c=content();let status=409;
  const {panel}=setup(async(url,init)=>init.method==='GET'?res(200,row(c)):res(status,{}));
  await panel.open(c);
  const exam=inputs(panel.element)[0];exam.value='보존할 입력';await exam.fire('input');
  await action(panel.element,'save').fire('click');
  assert.match(panel.element.textContent,/다른 창에서 제작 계획이 바뀌었습니다/);
  assert.equal(inputs(panel.element)[0].value,'보존할 입력');assert.equal(panel.isDirty(),true);assert.equal(panel.isBusy(),false);
  status=401;await action(panel.element,'save').fire('click');
  assert.match(panel.element.textContent,/로그인 후 다시 시도/);assert.equal(inputs(panel.element)[0].value,'보존할 입력');
});

test('읽기 전용은 입력이 잠기고 POST하지 않으며 refreshControls로만 풀린다',async()=>{
  const c=content();const calls=[];
  const {panel}=setup(async(url,init)=>{calls.push(init.method);return res(200,row(c));});
  await panel.open(c,{writable:false});
  assert.ok(inputs(panel.element).every(n=>n.disabled===true));
  await action(panel.element,'save').fire('click');await action(panel.element,'add-scene').fire('click');
  assert.deepEqual(calls,['GET']);
  panel.refreshControls({writable:true});
  assert.ok(inputs(panel.element).every(n=>n.disabled===false));
  assert.equal(action(panel.element,'save').disabled,false);
});

test('늦게 도착한 이전 원고 응답과 open(null) 이후 POST 응답은 반영되지 않는다',async()=>{
  const a=content({id:'a',title:'A원고'}),b=content({id:'b',title:'B원고',owner_account_id:'acct-b'});
  const gateA=deferred();
  const {panel}=setup((url,init)=>{if(url.includes('/a/'))return gateA.promise;if(url.includes('/b/')){return Promise.resolve(res(200,row(b)));}return Promise.resolve(res(500,{}));});
  const openA=panel.open(a);await panel.open(b);
  gateA.resolve(res(200,row(a)));await openA;
  assert.match(panel.element.textContent,/B원고/);assert.doesNotMatch(panel.element.textContent,/A원고/);
  // 진행 중 POST 중에 open(null)로 비우면 늦은 응답이 상태를 되살리지 못한다
  const post=deferred();const c=content();
  const {panel:p2}=setup((url,init)=>init.method==='GET'?Promise.resolve(res(200,row(c))):post.promise);
  await p2.open(c);const saving=action(p2.element,'save').fire('click');
  assert.equal(p2.isBusy(),true);assert.ok(inputs(p2.element).every(n=>n.disabled===true));
  await p2.open(null);post.resolve(res(200,row(c,{plan_revision:1})));await saving;
  assert.equal(p2.isBusy(),false);assert.equal(inputs(p2.element).length,0);assert.equal(p2.isDirty(),false);
});

test('계정·원고 버전·hash가 다른 응답은 거부하고 계획을 만들지 않는다',async()=>{
  const c=content();
  for(const bad of [{owner_account_id:'acct-x'},{content_revision:4},{manifest_hash:'z'.repeat(64)},{execution_enabled:true},{review_status:'passed'},{extra:1}]){
    const {panel}=setup(async()=>res(200,{...row(c),...bad}));
    await panel.open(c);
    assert.equal(inputs(panel.element).length,0,JSON.stringify(bad));
    assert.match(panel.element.textContent,/확인할 수 없습니다/);
  }
});

const scene=()=>({asset_id:'img1',kind:'diorama',seconds:3,title:'장면 제목',caption:'원래 자막'});
const previous=(c,over={})=>row({...c,revision:2,manifest_hash:'a'.repeat(64)},{plan_revision:4,plan:plan({scenes:[scene()],voice_asset_id:'wav1'}),...over});

test('이전 계획 조회는 GET만 하고 명시 가져오기만 현재 버전 CAS POST한다',async()=>{
  const c=content(),calls=[];const old=previous(c);
  const {panel}=setup(async(url,init)=>{calls.push([url,init]);if(init.method==='POST')return res(200,row(c,{plan_revision:1,plan:old.plan}));return res(200,url.endsWith('revision=2')?old:row(c));});
  await panel.open(c);
  assert.equal(by(panel.element,'data-media-plan-field','source-revision')[0].value,'2');
  await action(panel.element,'lookup-previous').fire('click');
  assert.deepEqual(calls.map(([,i])=>i.method),['GET','GET']);
  assert.match(panel.element.textContent,/이전 버전 2 · 계획 4 · 장면 1개/);
  await action(panel.element,'import-previous').fire('click');
  assert.equal(calls.at(-1)[0],'/api/v2/contents/c%2F1/media-plan?revision=3');
  assert.deepEqual(JSON.parse(calls.at(-1)[1].body),{action:'import',expected_revision:0,source_revision:2,source_plan_revision:4,voice_asset_id:null});
  assert.equal(panel.isDirty(),false);assert.match(panel.element.textContent,/가져왔습니다/);
});

test('새 음성 선택만 바뀐 경우 가져올 수 있고 다른 미저장 변경은 덮어쓰지 않는다',async()=>{
  const c=content(),calls=[];
  const {panel}=setup(async(url,init)=>{calls.push([url,init]);return res(200,url.endsWith('revision=2')?previous(c):row(c));});
  await panel.open(c);await action(panel.element,'lookup-previous').fire('click');
  const voice=inputs(panel.element).find(n=>n.tagName==='select');voice.value='wav1';await voice.fire('change');
  assert.equal(action(panel.element,'import-previous').disabled,false);
  await action(panel.element,'import-previous').fire('click');
  assert.equal(JSON.parse(calls.at(-1)[1].body).voice_asset_id,'wav1');
  const exam=inputs(panel.element)[0];exam.value='변경한 시험';await exam.fire('input');
  assert.equal(action(panel.element,'import-previous').disabled,true);
  const before=calls.length;await action(panel.element,'import-previous').fire('click');
  assert.equal(calls.length,before);assert.equal(inputs(panel.element)[0].value,'변경한 시험');
});

test('이전 계획 409·네트워크 오류는 선택 음성과 미리보기를 보존한다',async()=>{
  const c=content();let failure=409;
  const {panel}=setup(async(url,init)=>{if(init.method==='POST'){if(failure===0)throw new Error('offline');return res(failure,{});}return res(200,url.endsWith('revision=2')?previous(c):row(c));});
  await panel.open(c);await action(panel.element,'lookup-previous').fire('click');
  const voice=inputs(panel.element).find(n=>n.tagName==='select');voice.value='wav1';await voice.fire('change');
  for(const value of [409,0]){failure=value;await action(panel.element,'import-previous').fire('click');assert.equal(inputs(panel.element).find(n=>n.tagName==='select').value,'wav1');assert.equal(panel.isDirty(),true);assert.match(panel.element.textContent,/이전 버전 2 · 계획 4/);assert.equal(panel.isBusy(),false);}
});

test('이전 버전 선택 변경은 미리보기를 무효화하고 소유자·버전·계획 없는 응답은 거부한다',async()=>{
  const c=content();let old=previous(c);
  const {panel}=setup(async(url)=>res(200,url.endsWith('revision=3')?row(c):old));
  await panel.open(c);await action(panel.element,'lookup-previous').fire('click');
  let input=by(panel.element,'data-media-plan-field','source-revision')[0];input.value='1';await input.fire('input');
  assert.equal(action(panel.element,'import-previous').disabled,true);
  for(const bad of [{owner_account_id:'other'},{content_revision:1},{plan_revision:0},{manifest_hash:'not-a-hash'}]){
    input=by(panel.element,'data-media-plan-field','source-revision')[0];input.value='2';await input.fire('input');old=previous(c,bad);await action(panel.element,'lookup-previous').fire('click');
    assert.equal(action(panel.element,'import-previous').disabled,true);assert.match(panel.element.textContent,/확인할 수 없습니다/);
  }
});

test('이전 계획 읽기 전용·잘못된 버전은 요청하지 않고 늦은 조회가 새 원고를 침범하지 않는다',async()=>{
  const c=content(),calls=[];const gate=deferred();
  const {panel}=setup((url,init)=>{calls.push([url,init]);return url.endsWith('revision=2')?gate.promise:Promise.resolve(res(200,row(c)));});
  await panel.open(c,{writable:false});await action(panel.element,'lookup-previous').fire('click');assert.equal(calls.length,1);
  panel.refreshControls({writable:true});
  let input=by(panel.element,'data-media-plan-field','source-revision')[0];input.value='3';await input.fire('input');await action(panel.element,'lookup-previous').fire('click');assert.equal(calls.length,1);
  input.value='2';await input.fire('input');const loading=action(panel.element,'lookup-previous').fire('click');assert.equal(panel.isBusy(),true);
  await panel.open(null);gate.resolve(res(200,previous(c)));await loading;
  assert.equal(inputs(panel.element).length,0);assert.equal(panel.isBusy(),false);
});


test('같은 이전 버전 재조회가 실패해도 확인해 둔 계획과 선택은 보존한다',async()=>{
  const c=content();let fail=false;
  const {panel}=setup(async(url)=>{if(url.endsWith('revision=2')){if(fail)throw new Error('offline');return res(200,previous(c));}return res(200,row(c));});
  await panel.open(c);await action(panel.element,'lookup-previous').fire('click');fail=true;
  await action(panel.element,'lookup-previous').fire('click');
  assert.match(panel.element.textContent,/이전 버전 2 · 계획 4/);assert.match(panel.element.textContent,/연결하지 못했습니다/);
  assert.equal(action(panel.element,'import-previous').disabled,false);
  assert.equal(by(panel.element,'data-media-plan-field','source-revision')[0].value,'2');
});
