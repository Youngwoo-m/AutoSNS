import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createReuseApprovalPanel} from '../ax-console/app/web/reuse_approval_panel.js';

const SHA_A='a'.repeat(64),SHA_B='b'.repeat(64);
const IMAGES=['image/png','image/jpeg','image/webp'];
const content=(over={})=>({id:'c/1',revision:3,manifest_hash:'h'.repeat(64),owner_account_id:'acct-a',title:'원고',assets:[
  {id:'img1',filename:'one.png',media_type:'image/png',sha256:SHA_A},
  {id:'img2',filename:'two.webp',media_type:'image/webp',sha256:SHA_B},
  {id:'wav1',filename:'voice.wav',media_type:'audio/wav',sha256:'c'.repeat(64)}],...over});
const row=(c,id,over={})=>{const a=c.assets.find(x=>x.id===id);return {content_id:c.id,content_revision:c.revision,manifest_hash:c.manifest_hash,owner_account_id:c.owner_account_id,asset_id:id,sha256:a.sha256,approval_revision:0,approved_revision:null,rights_confirmed:false,visual_checked:false,notes:'',status:'not_approved',review_method:'manual',...over};};
const approvedRow=(c,id,over={})=>row(c,id,{approval_revision:2,approved_revision:3,rights_confirmed:true,visual_checked:true,notes:'확인함',status:'approved',...over});
const defaults=c=>c.assets.filter(a=>IMAGES.includes(a.media_type)).map(a=>row(c,a.id));
const res=(status,body)=>({ok:status<400,status,json:async()=>body});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const GET_URL='/api/v2/contents/c%2F1/reuse-approvals?revision=3';
const tick=ms=>new Promise(r=>setTimeout(r,ms));
const by=(p,attr,value)=>all(p.element).filter(n=>n.getAttribute(attr)===value);
const field=(p,id,name)=>all(p.element).find(n=>n.getAttribute('data-reuse-for')===id&&n.getAttribute('data-reuse-field')===name);
const action=(p,name,id)=>all(p.element).find(n=>n.getAttribute('data-reuse-action')===name&&(id===undefined||n.getAttribute('data-reuse-for')===id));
const posts=calls=>calls.filter(([,i])=>i.method==='POST');
const gets=calls=>calls.filter(([,i])=>i.method==='GET');
// disabled 속성을 우회해 handler 내부 guard만 시험한다.
const force=(n,type='click')=>[...n.listeners.get(type)][0]({target:n,preventDefault(){}});
const check=async(n,v)=>{n.checked=v;await n.fire('change');};
const type=async(n,v)=>{n.value=v;await n.fire('input');};
const setup=(c,over={},opts={})=>{
  const {document}=harness();const calls=[],changes=[];
  const st={get:()=>res(200,{items:defaults(c)}),post:()=>res(404,{}),...over};
  const fetcher=(url,init={})=>{calls.push([url,init]);return Promise.resolve().then(()=>(init.method==='POST'?st.post:st.get)(url,init));};
  const panel=createReuseApprovalPanel({document,fetcher,onChange:()=>changes.push(1),...opts});
  return {panel,document,calls,changes,st};
};
const withConfirm=async(answer,fn)=>{
  const old=globalThis.confirm,asked=[];globalThis.confirm=m=>{asked.push(m);return answer;};
  try{await fn(asked);}finally{if(old===undefined)delete globalThis.confirm;else globalThis.confirm=old;}
};

test('열기는 저장된 행을 GET 한 번으로만 보여 주고 승인을 만들지 않으며 이미지는 고정 URL을 쓴다',async()=>{
  const c=content(),{panel,calls}=setup(c);
  assert.equal(all(panel.element).find(n=>n.tagName==='summary').textContent,'이미지 재사용 확인');
  await panel.open(c);
  assert.equal(calls.length,1);assert.equal(calls[0][0],GET_URL);assert.equal(calls[0][1].method,'GET');assert.equal(calls[0][1].credentials,'same-origin');
  assert.equal(posts(calls).length,0);
  const imgs=all(panel.element).filter(n=>n.tagName==='img');
  assert.deepEqual(imgs.map(n=>n.getAttribute('src')),['/api/v2/contents/c%2F1/revisions/3/assets/img1','/api/v2/contents/c%2F1/revisions/3/assets/img2']);
  assert.ok(imgs.every(n=>n.getAttribute('loading')==='lazy'));
  assert.equal(by(panel,'data-reuse-row','wav1').length,0);
  const text=panel.element.textContent;
  assert.match(text,/one\.png/);assert.match(text,/two\.webp/);assert.match(text,/aaaaaaaaaaaa/);assert.doesNotMatch(text,/aaaaaaaaaaaaa/);
  assert.match(text,/AI 검사가 아닙니다/);assert.match(text,/승인 전/);assert.match(text,/확인 기록 없음/);
  for(const id of ['img1','img2']){assert.equal(field(panel,id,'rights').checked,false);assert.equal(field(panel,id,'visual').checked,false);assert.equal(action(panel,'save',id).disabled,true);}
  assert.equal(panel.isDirty(),false);assert.equal(panel.isBusy(),false);
});

test('저장은 정해진 다섯 필드와 현재 확인 기록 버전만 POST하고 응답으로 기준을 갱신한다',async()=>{
  const c=content();let n=0;
  const {panel,calls}=setup(c,{get:()=>res(200,{items:[row(c,'img1',{approval_revision:4,approved_revision:2}),row(c,'img2')]}),post:(url,init)=>{
    n++;const b=JSON.parse(init.body);
    return res(200,row(c,'img1',{approval_revision:4+n,approved_revision:3,rights_confirmed:b.rights_confirmed,visual_checked:b.visual_checked,notes:b.notes,status:b.rights_confirmed&&b.visual_checked?'approved':'not_approved'}));
  }});
  await panel.open(c);
  await check(field(panel,'img1','rights'),true);await check(field(panel,'img1','visual'),true);await type(field(panel,'img1','notes'),'출처 확인');
  assert.equal(panel.isDirty(),true);assert.match(by(panel,'data-reuse-hint','img1')[0].textContent,/승인으로 처리/);
  await action(panel,'save','img1').fire('click');
  assert.equal(posts(calls).length,1);
  const [url,init]=posts(calls)[0],body=JSON.parse(init.body);
  assert.equal(url,GET_URL);assert.equal(init.credentials,'same-origin');
  assert.deepEqual(Object.keys(body),['asset_id','expected_revision','rights_confirmed','visual_checked','notes']);
  assert.deepEqual(body,{asset_id:'img1',expected_revision:4,rights_confirmed:true,visual_checked:true,notes:'출처 확인'});
  assert.equal(panel.isDirty(),false);assert.match(panel.element.textContent,/승인됨/);assert.match(panel.element.textContent,/확인 기록 버전 5/);
  assert.equal(field(panel,'img1','notes').value,'출처 확인');
  await type(field(panel,'img1','notes'),'수정');await action(panel,'save','img1').fire('click');
  assert.equal(JSON.parse(posts(calls)[1][1].body).expected_revision,5);
  assert.equal(gets(calls).length,1);
});

test('체크를 풀고 저장하면 철회 기록이며 기존 승인을 지우지 않는다',async()=>{
  const c=content();
  const {panel,calls}=setup(c,{get:()=>res(200,{items:[approvedRow(c,'img1'),row(c,'img2')]}),post:()=>res(200,row(c,'img1',{approval_revision:3,approved_revision:3,rights_confirmed:false,visual_checked:true,notes:'확인함',status:'not_approved'}))});
  await panel.open(c);
  assert.match(by(panel,'data-reuse-status','img1')[0].textContent,/승인됨/);
  await check(field(panel,'img1','rights'),false);
  assert.match(by(panel,'data-reuse-hint','img1')[0].textContent,/철회/);
  await action(panel,'save','img1').fire('click');
  assert.deepEqual(JSON.parse(posts(calls)[0][1].body),{asset_id:'img1',expected_revision:2,rights_confirmed:false,visual_checked:true,notes:'확인함'});
  assert.match(by(panel,'data-reuse-status','img1')[0].textContent,/승인 전/);assert.match(panel.element.textContent,/철회 기록을 저장/);
  assert.equal(panel.isDirty(),false);assert.equal(gets(calls).length,1);
});

test('입력 중에는 다시 그리지 않아 포커스·선택이 유지되고 dirty와 onChange만 갱신한다',async()=>{
  const c=content(),{panel,document,changes}=setup(c);await panel.open(c);
  const notes=field(panel,'img1','notes');notes.focus();const before=changes.length;
  await type(notes,'메모');
  assert.equal(field(panel,'img1','notes'),notes);assert.equal(document.activeElement,notes);assert.equal(notes.value,'메모');
  assert.ok(changes.length>before);assert.equal(panel.isDirty(),true);assert.equal(action(panel,'save','img1').disabled,false);
  await type(notes,'');assert.equal(panel.isDirty(),false);assert.equal(action(panel,'save','img1').disabled,true);
  await type(notes,'다시');
  // 다시 그려야 하는 경우(입력 버리기)에도 같은 입력칸으로 포커스가 돌아온다.
  await withConfirm(true,async()=>{await action(panel,'discard').fire('click');});
  const again=field(panel,'img1','notes');assert.notEqual(again,notes);assert.equal(again.value,'');assert.equal(document.activeElement,again);
});

test('한 행을 저장해도 다른 행의 입력과 저장 중 중복 요청 보호가 유지된다',async()=>{
  const c=content(),gate=deferred();
  const {panel,calls}=setup(c,{post:()=>gate.promise});
  await panel.open(c);
  await check(field(panel,'img1','rights'),true);await type(field(panel,'img2','notes'),'둘째 메모');await check(field(panel,'img2','visual'),true);
  const saving=action(panel,'save','img1').fire('click');
  assert.equal(panel.isBusy(),true);assert.equal(field(panel,'img2','notes').disabled,true);assert.equal(action(panel,'save','img2').disabled,true);
  await force(action(panel,'save','img1'));await force(action(panel,'save','img2'));await force(action(panel,'reload'));
  assert.equal(posts(calls).length,1);assert.equal(gets(calls).length,1);
  const locked=field(panel,'img2','notes');locked.value='저장 중 입력';await force(locked,'input');assert.equal(locked.value,'둘째 메모');
  gate.resolve(res(200,row(c,'img1',{approval_revision:1,approved_revision:3,rights_confirmed:true,visual_checked:false})));await saving;
  assert.equal(panel.isBusy(),false);
  assert.equal(field(panel,'img1','rights').checked,true);assert.match(panel.element.textContent,/확인 기록 버전 1/);
  assert.equal(field(panel,'img2','notes').value,'둘째 메모');assert.equal(field(panel,'img2','visual').checked,true);
  assert.equal(panel.isDirty(),true);assert.equal(action(panel,'save','img2').disabled,false);assert.equal(action(panel,'save','img1').disabled,true);
});

test('저장 401·409·503은 모든 입력을 보존하고 자동으로 다시 요청하지 않는다',async()=>{
  const c=content();
  for(const status of [401,409,503]){
    const {panel,calls}=setup(c,{post:()=>res(status,{})});await panel.open(c);
    await check(field(panel,'img1','rights'),true);await type(field(panel,'img1','notes'),'보존');await type(field(panel,'img2','notes'),'둘째');
    await action(panel,'save','img1').fire('click');await tick(10);
    assert.equal(posts(calls).length,1,String(status));assert.equal(gets(calls).length,1);assert.equal(panel.isBusy(),false);assert.equal(panel.isDirty(),true);
    assert.equal(field(panel,'img1','rights').checked,true);assert.equal(field(panel,'img1','notes').value,'보존');assert.equal(field(panel,'img2','notes').value,'둘째');
    assert.match(by(panel,'role','status')[0].textContent,status===401?/로그인/:status===409?/다시 조회/:/자동으로 다시 요청하지 않습니다/);
    assert.equal(action(panel,'save','img1').disabled,false);
  }
});

test('조회 503·401·네트워크 오류는 이미 표시한 행과 입력을 지우지 않는다',async()=>{
  const c=content();let mode='ok';
  const {panel,calls}=setup(c,{get:()=>mode==='ok'?res(200,{items:defaults(c)}):mode==='net'?Promise.reject(new Error('x')):res(Number(mode),{})});
  await panel.open(c);await type(field(panel,'img1','notes'),'남길 입력');await check(field(panel,'img2','rights'),true);
  await withConfirm(true,async()=>{
    for(const m of ['503','401','net']){
      mode=m;await action(panel,'reload').fire('click');
      assert.equal(panel.isBusy(),false);assert.equal(field(panel,'img1','notes').value,'남길 입력');assert.equal(field(panel,'img2','rights').checked,true);assert.equal(panel.isDirty(),true);
    }
  });
  assert.equal(gets(calls).length,4);assert.equal(posts(calls).length,0);
});

test('읽기 전용에서는 입력·저장 handler가 모두 막히고 writable이 바뀔 때만 다시 그린다',async()=>{
  const c=content(),{panel,calls}=setup(c);await panel.open(c,{writable:false});
  assert.match(panel.element.textContent,/읽기 전용/);
  for(const id of ['img1','img2'])for(const f of ['rights','visual','notes'])assert.equal(field(panel,id,f).disabled,true);
  const box=field(panel,'img1','rights'),notes=field(panel,'img1','notes');
  box.checked=true;await force(box,'change');notes.value='x';await force(notes,'input');
  assert.equal(panel.isDirty(),false);assert.equal(box.checked,false);assert.equal(notes.value,'');
  await force(action(panel,'save','img1'));assert.equal(posts(calls).length,0);
  const snapshot=field(panel,'img1','rights');
  panel.refreshControls({writable:false});panel.refreshControls();panel.refreshControls({});
  assert.equal(field(panel,'img1','rights'),snapshot);
  panel.refreshControls({writable:true});
  assert.notEqual(field(panel,'img1','rights'),snapshot);assert.equal(field(panel,'img1','rights').disabled,false);
  const again=field(panel,'img1','rights');panel.refreshControls({writable:true});assert.equal(field(panel,'img1','rights'),again);
});

test('알 수 없는 필드·비공개 키·원고/이미지 불일치·모순된 상태 응답은 통째로 거부한다',async()=>{
  const c=content(),d=id=>row(c,id);
  const cases={
    extraKey:[{...d('img1'),local_path:'/PRIVATE/x.png'},d('img2')],
    missingKey:(()=>{const r=d('img1');delete r.notes;return [r];})(),
    actorLeak:[{...d('img1'),actor:'PRIVATE'}],
    owner:[d('img1')].map(r=>({...r,owner_account_id:'acct-b'})),
    contentId:[{...d('img1'),content_id:'other'}],
    contentRevision:[{...d('img1'),content_revision:2}],
    manifest:[{...d('img1'),manifest_hash:'z'.repeat(64)}],
    audioAsset:[row(c,'wav1',{})],
    unknownAsset:[{...d('img1'),asset_id:'ghost'}],
    sha:[{...d('img1'),sha256:SHA_B}],
    negativeRevision:[{...d('img1'),approval_revision:-1}],
    fractional:[{...d('img1'),approval_revision:1.5}],
    zeroApproved:[approvedRow(c,'img1',{approved_revision:0})],
    nullWithRevision:[approvedRow(c,'img1',{approved_revision:null})],
    approvedFlagsFalse:[row(c,'img1',{approval_revision:1,approved_revision:3,status:'approved'})],
    notApprovedFlagsTrue:[approvedRow(c,'img1',{status:'not_approved'})],
    method:[approvedRow(c,'img1',{review_method:'ai'})],
    longNotes:[row(c,'img1',{notes:'가'.repeat(2001)})],
    notesType:[{...d('img1'),notes:null}],
    flagType:[{...d('img1'),rights_confirmed:'true'}],
    duplicate:[d('img1'),d('img1')],
    topLevel:{items:[d('img1')],cursor:'PRIVATE'}
  };
  for(const [name,items] of Object.entries(cases)){
    const body=Array.isArray(items)?{items}:items;
    const {panel,calls}=setup(c,{get:()=>res(200,body)});await panel.open(c);
    assert.equal(by(panel,'data-reuse-row','img1').length,0,name);assert.equal(panel.isDirty(),false,name);assert.equal(panel.isBusy(),false,name);
    assert.match(panel.element.textContent,/확인할 수 없어/,name);assert.doesNotMatch(panel.element.textContent,/PRIVATE/,name);assert.equal(calls.length,1,name);
  }
  for(const body of [null,[],{items:'x'}]){const {panel}=setup(c,{get:()=>res(200,body)});await panel.open(c);assert.equal(all(panel.element).filter(n=>n.tagName==='img').length,0);assert.match(panel.element.textContent,/확인할 수 없어/);}
});

test('이전 원고의 늦은 조회·저장 응답과 열기 취소는 현재 화면을 바꾸지 못한다',async()=>{
  const c1=content(),c2=content({id:'c/2',assets:[{id:'imgX',filename:'x.png',media_type:'image/png',sha256:SHA_A}]});
  const gate=deferred();
  const {panel}=setup(c1,{get:url=>url.includes('c%2F1')?gate.promise:res(200,{items:[row(c2,'imgX')]})});
  const first=panel.open(c1);await panel.open(c2);
  gate.resolve(res(200,{items:defaults(c1)}));await first;
  assert.deepEqual(all(panel.element).filter(n=>n.getAttribute('data-reuse-row')!==null).map(n=>n.getAttribute('data-reuse-row')),['imgX']);assert.equal(panel.isBusy(),false);
  // 저장 중 원고 전환
  const post=deferred(),s=setup(c1,{post:()=>post.promise});
  await s.panel.open(c1);await check(field(s.panel,'img1','rights'),true);
  const saving=action(s.panel,'save','img1').fire('click');
  await s.panel.open(c2).catch(()=>{});
  post.resolve(res(200,row(c1,'img1',{approval_revision:1,approved_revision:3,rights_confirmed:true})));await saving;
  assert.equal(by(s.panel,'data-reuse-row','img1').length,0);assert.doesNotMatch(s.panel.element.textContent,/확인 기록을 저장했습니다/);assert.equal(s.panel.isBusy(),false);
  // open(null)은 세대를 바꿔 진행 중 응답을 버린다
  const g2=deferred(),t=setup(c1,{get:()=>g2.promise});
  const opening=t.panel.open(c1);await t.panel.open(null);g2.resolve(res(200,{items:defaults(c1)}));await opening;
  assert.equal(all(t.panel.element).filter(n=>n.getAttribute('data-reuse-row')!==null).length,0);assert.equal(t.panel.isBusy(),false);assert.match(t.panel.element.textContent,/원고를 열면/);
});

test('다시 조회는 입력이 있으면 확인 후에만 GET하고 거절하면 GET 없이 입력을 유지한다',async()=>{
  const c=content();let served=0;
  const {panel,calls}=setup(c,{get:()=>{served++;return res(200,{items:[served>1?approvedRow(c,'img1'):row(c,'img1'),row(c,'img2')]});}});
  await panel.open(c);
  await action(panel,'reload').fire('click');assert.equal(gets(calls).length,2,'입력 변경 전에는 확인 없이 조회');
  await type(field(panel,'img1','notes'),'보존할 메모');
  await withConfirm(false,async asked=>{
    await action(panel,'reload').fire('click');await force(action(panel,'reload'));
    assert.ok(asked.length>=1);assert.equal(gets(calls).length,2);assert.equal(field(panel,'img1','notes').value,'보존할 메모');assert.equal(panel.isDirty(),true);
  });
  await withConfirm(true,async asked=>{
    await action(panel,'reload').fire('click');
    assert.equal(asked.length,1);assert.equal(gets(calls).length,3);assert.equal(panel.isDirty(),false);assert.equal(field(panel,'img1','notes').value,'확인함');assert.match(by(panel,'data-reuse-status','img1')[0].textContent,/승인됨/);
  });
  assert.equal(posts(calls).length,0);
});

test('요청 시간 초과는 abort하고 busy를 풀며 입력을 보존하고 재시도하지 않는다',async()=>{
  const c=content();let postCount=0,postSignal,getSignal;
  const {document}=harness();const calls=[];
  const panel=createReuseApprovalPanel({document,requestTimeoutMs:5,fetcher:(url,init)=>{
    calls.push([url,init]);
    if(init.method==='POST'){postCount++;postSignal=init.signal;return new Promise(()=>{});}
    if(calls.length===1)return Promise.resolve(res(200,{items:defaults(c)}));
    getSignal=init.signal;return new Promise(()=>{});
  }});
  await panel.open(c);await check(field(panel,'img1','rights'),true);await type(field(panel,'img1','notes'),'시간 초과');
  await action(panel,'save','img1').fire('click');await tick(30);
  assert.equal(panel.isBusy(),false);assert.equal(postCount,1);assert.equal(postSignal.aborted,true);assert.equal(panel.isDirty(),true);
  assert.equal(field(panel,'img1','notes').value,'시간 초과');assert.match(panel.element.textContent,/저장 결과를 알 수 없습니다/);
  await withConfirm(true,async()=>{await action(panel,'reload').fire('click');});await tick(30);
  assert.equal(getSignal.aborted,true);assert.equal(panel.isBusy(),false);assert.equal(field(panel,'img1','notes').value,'시간 초과');assert.equal(field(panel,'img1','rights').checked,true);
  assert.equal(calls.length,3);assert.match(by(panel,'role','status')[0].textContent,/자동으로 다시 요청하지 않습니다/);
});

test('입력 변경 버리기는 확인 후 편집값만 되돌리고 네트워크·저장된 기록은 건드리지 않는다',async()=>{
  const c=content(),{panel,calls,changes}=setup(c,{get:()=>res(200,{items:[approvedRow(c,'img1'),row(c,'img2')]})});
  await panel.open(c);
  assert.equal(action(panel,'discard').disabled,true);
  await check(field(panel,'img1','visual'),false);await type(field(panel,'img2','notes'),'임시');
  assert.equal(action(panel,'discard').disabled,false);assert.equal(action(panel,'discard').textContent,'입력 변경 버리기');
  await withConfirm(false,async()=>{await action(panel,'discard').fire('click');assert.equal(panel.isDirty(),true);});
  await withConfirm(true,async()=>{await action(panel,'discard').fire('click');});
  assert.equal(panel.isDirty(),false);assert.equal(field(panel,'img1','visual').checked,true);assert.equal(field(panel,'img2','notes').value,'');
  assert.match(by(panel,'data-reuse-status','img1')[0].textContent,/승인됨/);assert.equal(calls.length,1);
  await type(field(panel,'img2','notes'),'또 임시');const before=changes.length;panel.discardChanges();
  assert.equal(panel.isDirty(),false);assert.equal(field(panel,'img2','notes').value,'');assert.ok(changes.length>before);assert.equal(calls.length,1);
});

test('이미지가 없으면 안내하고, 과거 원고 버전의 승인은 적용 문구를 보이며 실패한 조회는 빈 상태로 오인하지 않는다',async()=>{
  const c=content({assets:[{id:'wav1',filename:'v.wav',media_type:'audio/wav',sha256:'c'.repeat(64)}]});
  const empty=setup(c,{get:()=>res(200,{items:[]})});await empty.panel.open(c);
  assert.match(empty.panel.element.textContent,/등록된 이미지 없음/);assert.equal(empty.calls.length,1);
  const c3=content();
  const carried=setup(c3,{get:()=>res(200,{items:[approvedRow(c3,'img1',{approved_revision:1}),approvedRow(c3,'img2',{approved_revision:3})]})});await carried.panel.open(c3);
  assert.match(carried.panel.element.textContent,/같은 이미지의 과거 확인 기록을 적용/);
  assert.equal(all(carried.panel.element).filter(n=>n.getAttribute('data-reuse-info')==='carried').length,1);
  const failed=setup(c3,{get:()=>res(503,{})});await failed.panel.open(c3);
  assert.doesNotMatch(failed.panel.element.textContent,/등록된 이미지 없음/);assert.equal(failed.calls.length,1);
});

 test('과거 원고에서도 같은 이미지의 이후 최신 확인 기록을 표시한다',async()=>{
  const c=content();const {panel}=setup(c,{get:()=>res(200,{items:[approvedRow(c,'img1',{approved_revision:4}),row(c,'img2')]})});
  await panel.open(c,{writable:false});assert.match(panel.element.textContent,/이후 버전에서 남긴 최신 확인 상태/);assert.match(panel.element.textContent,/승인됨/);
 });
