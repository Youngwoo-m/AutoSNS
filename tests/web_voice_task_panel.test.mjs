import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createVoiceTaskPanel} from '../ax-console/app/web/voice_task_panel.js';

const CAPS_URL='/api/v2/voicebox/capabilities';
const content=(over={})=>({id:'c/1',revision:3,manifest_hash:'h'.repeat(64),owner_account_id:'acct-a',title:'원고',...over});
const cap=(over={})=>({provider_id:'voicebox-local',service_available:true,execution_enabled:true,readiness:'not_checked',external_fallback:false,...over});
const task=(c,over={})=>({task_id:'t1',state:'completed',reason_code:null,content_id:c.id,input_revision:c.revision,output_revision:null,asset_id:null,seconds:null,review_status:'not_checked',voice_label:null,generation_id:null,...over});
const res=(status,body)=>({ok:status<400,status,json:async()=>body});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const by=(root,attr,value)=>all(root).filter(n=>n.getAttribute(attr)===value);
const btn=(p,name)=>by(p.element,'data-voice-action',name)[0];
const fieldOf=(p,name)=>by(p.element,'data-voice-field',name)[0];
const rows=p=>all(p.element).filter(n=>n.getAttribute('data-voice-task')!==null);
const posts=calls=>calls.filter(([,i])=>i.method==='POST');
// disabled 속성을 우회해 handler 내부 guard만 시험한다.
const force=(n,type='click')=>[...n.listeners.get(type)][0]({target:n,preventDefault(){}});
const server=(c,over={})=>{
  const st={caps:()=>res(200,cap()),list:()=>res(200,{items:[]}),create:()=>res(404,{}),resume:()=>res(404,{}),...over};const calls=[];
  const fetcher=(url,init={})=>{
    calls.push([url,init]);
    const pick=url===CAPS_URL?st.caps:url.includes('/voice-tasks?revision=')?st.list:/\/resume$/.test(url)?st.resume:st.create;
    return Promise.resolve().then(()=>pick(url,init));
  };
  return {fetcher,calls,st};
};
const setup=(c,over,{onCompleted}={})=>{
  const {document}=harness();const s=server(c,over);const changes=[];const done=[];
  const panel=createVoiceTaskPanel({document,fetcher:s.fetcher,onChange:()=>changes.push(1),onCompleted:onCompleted||(r=>done.push(r))});
  return {panel,changes,done,...s};
};
const typeScript=async(p,value)=>{const n=fieldOf(p,'script');n.value=value;await n.fire('input');};
const recoveryField=p=>by(p.element,'data-voice-recovery-input','t1')[0];
const recoveryProof=(over={})=>({task_id:'t1',generation_id:'existing1',recovery_fingerprint:'a'.repeat(64),task_state:'unknown',can_confirm:true,review_status:'not_checked',...over});

test('불명확한 작업은 새 합성을 막고 대조와 연결을 서로 다른 명시 요청으로 처리한다',async()=>{
  const c=content(),{panel,calls}=setup(c,{list:()=>res(200,{items:[task(c,{state:'unknown'})]}),create:(url,init)=>{
    if(url.endsWith('/recovery-preview')){assert.deepEqual(JSON.parse(init.body),{generation_id:'existing1'});return res(200,recoveryProof());}
    assert.ok(url.endsWith('/recover'));assert.deepEqual(JSON.parse(init.body),{generation_id:'existing1',recovery_fingerprint:'a'.repeat(64)});
    return res(200,task(c,{state:'pending',generation_id:'existing1'}));
  }});
  await panel.open(c);await typeScript(panel,'다른 대본');assert.equal(btn(panel,'create').disabled,true);await force(btn(panel,'create'));assert.equal(posts(calls).length,0);
  const field=recoveryField(panel);field.value='existing1';await field.fire('input');assert.equal(panel.isDirty(),true);
  await force(btn(panel,'confirm-recovery'));assert.equal(posts(calls).length,0);
  await btn(panel,'inspect-recovery').fire('click');assert.equal(posts(calls).length,1);assert.equal(btn(panel,'confirm-recovery').disabled,false);
  await btn(panel,'confirm-recovery').fire('click');assert.equal(posts(calls).length,2);assert.match(panel.element.textContent,/기존 음성을 연결/);assert.equal(btn(panel,'resume').disabled,false);
});

test('기존 생성 ID 편집은 대조 증명을 무효화하고 실패 시 입력을 유지한다',async()=>{
  const c=content();let fail=false;
  const {panel,calls}=setup(c,{list:()=>res(200,{items:[task(c,{state:'unknown'})]}),create:()=>fail?res(409,{}):res(200,recoveryProof())});
  await panel.open(c);let field=recoveryField(panel);field.value='existing1';await field.fire('input');await btn(panel,'inspect-recovery').fire('click');
  field=recoveryField(panel);field.value='existing2';await field.fire('input');assert.equal(btn(panel,'confirm-recovery').disabled,true);await force(btn(panel,'confirm-recovery'));assert.equal(posts(calls).length,1);
  fail=true;await btn(panel,'inspect-recovery').fire('click');assert.equal(recoveryField(panel).value,'existing2');assert.equal(panel.isDirty(),true);assert.equal(panel.isBusy(),false);assert.match(panel.element.textContent,/연결하지 않았습니다/);
  panel.discardChanges();assert.equal(panel.isDirty(),false);assert.equal(recoveryField(panel).value,'');
});

test('다른 작업·생성 ID 또는 비공개 필드가 섞인 대조 응답은 연결에 쓰지 않는다',async()=>{
  const c=content();
  for(const proof of [recoveryProof({task_id:'other'}),recoveryProof({generation_id:'other'}),recoveryProof({profile_id:'PRIVATE'}),recoveryProof({recovery_fingerprint:'invalid'})]){
    const {panel,calls}=setup(c,{list:()=>res(200,{items:[task(c,{state:'unknown'})]}),create:()=>res(200,proof)});await panel.open(c);
    const field=recoveryField(panel);field.value='existing1';await field.fire('input');await btn(panel,'inspect-recovery').fire('click');
    assert.equal(btn(panel,'confirm-recovery').disabled,true);await force(btn(panel,'confirm-recovery'));assert.equal(posts(calls).length,1);assert.doesNotMatch(panel.element.textContent,/PRIVATE/);
  }
});

test('요청 시간 초과는 busy를 풀고 입력을 보존하며 자동 POST를 반복하지 않는다',async()=>{
  const c=content(),{document}=harness();let count=0,signal;
  const panel=createVoiceTaskPanel({document,requestTimeoutMs:5,fetcher:async(url,options)=>{
    if(options.method==='POST'){count++;signal=options.signal;return new Promise(()=>{});}
    return res(200,url===CAPS_URL?cap():{items:[]});
  }});
  await panel.open(c);await typeScript(panel,'시간 초과에도 남길 대본');
  await btn(panel,'create').fire('click');
  assert.equal(panel.isBusy(),false);assert.equal(panel.isDirty(),true);assert.equal(count,1);assert.equal(signal.aborted,true);
  assert.equal(fieldOf(panel,'script').value,'시간 초과에도 남길 대본');assert.match(panel.element.textContent,/다시 합성하지 마세요/);
});

test('서버와 동일한 시드 상한을 넘기면 POST 전에 거부한다',async()=>{
  const c=content(),{panel,calls}=setup(c);await panel.open(c);await typeScript(panel,'대본');
  const seed=fieldOf(panel,'seed');seed.value='2147483648';await seed.fire('input');await btn(panel,'create').fire('click');
  assert.equal(posts(calls).length,0);assert.match(panel.element.textContent,/2147483647/);
});

test('열기는 capability와 작업 목록 GET 두 번만 하고 POST·native 요청이 없다',async()=>{
  const c=content();const gate=deferred();
  const {panel,calls}=setup(c,{list:()=>gate.promise});
  const opening=panel.open(c);
  assert.equal(panel.isBusy(),true);
  gate.resolve(res(200,{items:[task(c)]}));await opening;
  assert.deepEqual(calls.map(([u])=>u),[CAPS_URL,'/api/v2/contents/c%2F1/voice-tasks?revision=3']);
  assert.ok(calls.every(([,i])=>i.method==='GET'&&i.body===undefined));
  assert.equal(posts(calls).length,0);
  assert.equal(panel.element.tagName,'details');
  assert.equal(all(panel.element).find(n=>n.tagName==='summary').textContent,'음성 제작');
  assert.equal(fieldOf(panel,'script').value,'');assert.equal(fieldOf(panel,'seed').value,'14005');
  assert.equal(fieldOf(panel,'script').getAttribute('maxlength'),'2000');
  assert.equal(panel.isDirty(),false);assert.equal(panel.isBusy(),false);
  assert.match(panel.element.textContent,/원고 c\/1 · 버전 3 · 소유 계정 acct-a/);
  assert.match(panel.element.textContent,/AI 합성 음성/);assert.match(panel.element.textContent,/본인 목소리 복제/);
  assert.match(panel.element.textContent,/최대 20초/);assert.match(panel.element.textContent,/검토 전/);
});

test('capability가 꺼짐·실패·형식 불일치이면 합성 버튼이 닫힌 채 요청하지 않는다',async()=>{
  const c=content();
  const variants=[
    {caps:()=>res(200,cap({execution_enabled:false}))},
    {caps:()=>res(500,{})},
    {caps:()=>{throw new Error('offline');}},
    {caps:()=>res(200,cap({provider_id:'other'}))},
    {caps:()=>res(200,cap({readiness:'ready'}))},
    {caps:()=>res(200,cap({external_fallback:true}))},
    {caps:()=>res(200,cap({service_available:'yes'}))},
    {caps:()=>res(200,{...cap(),extra:1})},
  ];
  for(const over of variants){
    const {panel,calls}=setup(c,over);await panel.open(c);
    await typeScript(panel,'대본');
    assert.equal(btn(panel,'create').disabled,true);
    await btn(panel,'create').fire('click');await force(btn(panel,'create'));
    assert.equal(posts(calls).length,0);
    assert.equal(fieldOf(panel,'script').value,'대본');
  }
});

test('입력은 dirty만 바꾸고 repaint하지 않으며 discard와 같은 값 refreshControls도 안전하다',async()=>{
  const c=content();const {panel,changes}=setup(c);await panel.open(c);
  const area=fieldOf(panel,'script'),seed=fieldOf(panel,'seed');
  const before=changes.length;
  area.focus();await typeScript(panel,'새 대본');
  assert.equal(panel.isDirty(),true);assert.equal(changes.length,before+1);
  assert.equal(fieldOf(panel,'script'),area);assert.equal(document_active(area),true);
  seed.value='7';await seed.fire('input');assert.equal(panel.isDirty(),true);
  panel.refreshControls({writable:true});
  assert.equal(fieldOf(panel,'script'),area);assert.equal(fieldOf(panel,'seed'),seed);
  panel.discardChanges();
  assert.equal(panel.isDirty(),false);assert.equal(fieldOf(panel,'script').value,'');assert.equal(fieldOf(panel,'seed').value,'14005');
  seed.value='14005';
});
const document_active=n=>n.ownerDocument.activeElement===n;

test('합성 POST는 정확한 경로와 body를 보내고 성공 뒤 baseline만 갱신하며 실패는 입력을 보존한다',async()=>{
  const c=content();let mode='ok';
  const {panel,calls}=setup(c,{create:(u,i)=>{
    if(mode==='ok')return res(200,task(c,{task_id:'t9',state:'pending'}));
    if(mode==='net')throw new Error('timeout');
    return res(Number(mode),{});
  }});
  await panel.open(c);
  await typeScript(panel,'안녕하세요');
  const seed=fieldOf(panel,'seed');seed.value='7';await seed.fire('input');
  await btn(panel,'create').fire('click');
  const sent=posts(calls);assert.equal(sent.length,1);
  assert.equal(sent[0][0],'/api/v2/contents/c%2F1/voice-tasks');
  assert.deepEqual(Object.keys(JSON.parse(sent[0][1].body)),['expected_revision','script','seed']);
  assert.deepEqual(JSON.parse(sent[0][1].body),{expected_revision:3,script:'안녕하세요',seed:7});
  assert.equal(panel.isDirty(),false);
  assert.equal(fieldOf(panel,'script').value,'안녕하세요');assert.equal(fieldOf(panel,'seed').value,'7');
  assert.equal(rows(panel).length,1);
  // 이후 실패는 입력과 dirty를 그대로 둔다.
  await typeScript(panel,'다른 대본');
  for(const [m,re] of [['409',/원고 버전이 바뀌었거나/],['401',/로그인 후 다시 시도/],['503',/접수 결과를 확인하지 못했습니다/],['net',/결과를 알 수 없습니다/],['500',/결과를 알 수 없습니다/]]){
    mode=m;const n=posts(calls).length;
    await btn(panel,'create').fire('click');
    assert.equal(posts(calls).length,n+1);
    assert.match(panel.element.textContent,re);
    assert.equal(fieldOf(panel,'script').value,'다른 대본');assert.equal(fieldOf(panel,'seed').value,'7');
    assert.equal(panel.isDirty(),true);assert.equal(panel.isBusy(),false);
  }
  assert.match(panel.element.textContent,/다시 합성하지 마세요/);
  // 불명확한 결과 뒤에도 자동 재요청은 없다.
  const n=posts(calls).length;await Promise.resolve();assert.equal(posts(calls).length,n);
  // 로컬 검증 실패는 POST하지 않는다.
  await typeScript(panel,'   ');await btn(panel,'create').fire('click');assert.equal(posts(calls).length,n);
});

test('전송 중에는 중복 합성을 막고 입력을 잠근다',async()=>{
  const c=content();const gate=deferred();
  const {panel,calls}=setup(c,{create:()=>gate.promise});
  await panel.open(c);await typeScript(panel,'대본');
  const button=btn(panel,'create');
  const first=button.fire('click');
  assert.equal(panel.isBusy(),true);
  await button.fire('click');await force(button);await force(btn(panel,'create'));
  assert.equal(posts(calls).length,1);
  assert.equal(fieldOf(panel,'script').disabled,true);assert.equal(btn(panel,'create').disabled,true);assert.equal(btn(panel,'reload').disabled,true);
  gate.resolve(res(200,task(c,{state:'started'})));await first;
  assert.equal(posts(calls).length,1);assert.equal(panel.isBusy(),false);
});

test('started·unknown 작업에는 재합성·결과 확인 버튼이 없고 pending만 명시 클릭으로 resume한다',async()=>{
  const c=content();
  const items=[task(c,{task_id:'ts',state:'started'}),task(c,{task_id:'tu',state:'unknown'}),task(c,{task_id:'tp',state:'pending'}),task(c,{task_id:'ta',state:'audio_ready'}),task(c,{task_id:'tf',state:'failed',reason_code:'voicebox_generation_failed'})];
  const {panel,calls}=setup(c,{list:()=>res(200,{items}),resume:(u)=>res(200,task(c,{task_id:u.split('/')[4],state:'completed'}))});
  await panel.open(c);
  for(const id of ['ts','tu','tf'])assert.equal(rows(panel).find(n=>n.getAttribute('data-voice-task')===id).children.some(k=>k.getAttribute('data-voice-action')==='resume'),false,id);
  assert.equal(by(panel.element,'data-voice-resume','ts').length+by(panel.element,'data-voice-resume','tu').length,0);
  assert.match(panel.element.textContent,/생성 결과를 확인하기 전 다시 합성하지 마세요/);
  assert.equal(posts(calls).length,0);
  await by(panel.element,'data-voice-resume','tp')[0].fire('click');
  assert.equal(posts(calls).length,1);
  assert.equal(posts(calls)[0][0],'/api/v2/voice-tasks/tp/resume');assert.equal(posts(calls)[0][1].body,'{}');
  assert.equal(by(panel.element,'data-voice-resume','tp').length,0);
  assert.equal(by(panel.element,'data-voice-resume','ta').length,1);
});

test('다시 조회는 작업 목록 GET만 보내고 dirty 입력과 자동 resume 없이 유지한다',async()=>{
  const c=content();let items=[task(c,{task_id:'tp',state:'pending'})];
  const {panel,calls}=setup(c,{list:()=>res(200,{items})});
  await panel.open(c);await typeScript(panel,'보존할 대본');
  const seed=fieldOf(panel,'seed');seed.value='99';await seed.fire('input');
  const n=calls.length;items=[task(c,{task_id:'tp',state:'audio_ready'})];
  await btn(panel,'reload').fire('click');
  assert.equal(calls.length,n+1);
  assert.equal(calls[n][0],'/api/v2/contents/c%2F1/voice-tasks?revision=3');assert.equal(calls[n][1].method,'GET');
  assert.equal(posts(calls).length,0);
  assert.equal(fieldOf(panel,'script').value,'보존할 대본');assert.equal(fieldOf(panel,'seed').value,'99');assert.equal(panel.isDirty(),true);
  assert.match(panel.element.textContent,/자산 등록 확인이 남았습니다/);
  await Promise.resolve();assert.equal(calls.length,n+1);
});

test('늦은 이전 원고 응답과 open(null) 뒤 POST 응답은 화면·콜백에 반영되지 않는다',async()=>{
  const a=content({id:'a',owner_account_id:'acct-a'}),b=content({id:'b',owner_account_id:'acct-b'});
  const gateA=deferred();const done=[];
  const {document}=harness();
  const fetcher=(url)=>{
    if(url===CAPS_URL)return Promise.resolve(res(200,cap()));
    if(url.includes('/a/'))return gateA.promise;
    return Promise.resolve(res(200,{items:[task(b,{task_id:'tb'})]}));
  };
  const panel=createVoiceTaskPanel({document,fetcher,onCompleted:r=>done.push(r)});
  const openA=panel.open(a);await panel.open(b);
  gateA.resolve(res(200,{items:[task(a,{task_id:'ta'})]}));await openA;
  assert.deepEqual(rows(panel).map(n=>n.getAttribute('data-voice-task')),['tb']);
  assert.match(panel.element.textContent,/소유 계정 acct-b/);assert.equal(done.length,1);assert.equal(done[0].task_id,'tb');
  // 합성 중 open(null)
  const c=content();const post=deferred();const s=setup(c,{create:()=>post.promise});
  await s.panel.open(c);await typeScript(s.panel,'대본');
  const saving=btn(s.panel,'create').fire('click');
  await s.panel.open(null);
  post.resolve(res(200,task(c,{task_id:'late'})));await saving;
  assert.equal(s.panel.isBusy(),false);assert.equal(s.panel.isDirty(),false);
  assert.equal(all(s.panel.element).filter(n=>n.tagName==='textarea').length,0);assert.equal(rows(s.panel).length,0);assert.equal(s.done.length,0);
});

test('읽기 전용은 입력·합성·결과 확인을 잠그고 handler guard도 POST하지 않으며 refreshControls로만 풀린다',async()=>{
  const c=content();
  const {panel,calls}=setup(c,{list:()=>res(200,{items:[task(c,{task_id:'tp',state:'pending'})]})});
  await panel.open(c,{writable:false});
  assert.equal(fieldOf(panel,'script').disabled,true);assert.equal(fieldOf(panel,'seed').disabled,true);
  assert.equal(btn(panel,'create').disabled,true);assert.equal(by(panel.element,'data-voice-resume','tp')[0].disabled,true);
  await typeScript(panel,'막힌 입력');assert.equal(panel.isDirty(),false);
  await force(btn(panel,'create'));await force(by(panel.element,'data-voice-resume','tp')[0]);
  assert.equal(posts(calls).length,0);
  assert.equal(btn(panel,'reload').disabled,false);
  panel.refreshControls({writable:true});
  assert.equal(fieldOf(panel,'script').disabled,false);assert.equal(btn(panel,'create').disabled,false);
  assert.equal(by(panel.element,'data-voice-resume','tp')[0].disabled,false);
});

test('형식이 어긋나거나 모르는 필드가 있는 작업 응답은 통째로 거부하고 내용을 노출하지 않는다',async()=>{
  const c=content();
  const long='a'.repeat(101);
  const bad=[
    {...task(c),script:'SECRET'},{...task(c),profile_path:'/Users/x/SECRET'},
    (()=>{const r=task(c);delete r.generation_id;return r;})(),
    task(c,{review_status:'passed'}),task(c,{task_id:'a/b'}),task(c,{task_id:''}),task(c,{task_id:long}),
    task(c,{state:'running'}),task(c,{seconds:'3'}),task(c,{seconds:Infinity}),task(c,{output_revision:-1}),task(c,{output_revision:1.5}),
    task(c,{asset_id:5}),task(c,{voice_label:{}}),task(c,{reason_code:3}),task(c,{input_revision:'3'}),
  ];
  for(const row of bad){
    const {panel}=setup(c,{list:()=>res(200,{items:[task(c,{task_id:'ok'}),row]})});
    await panel.open(c);
    assert.equal(rows(panel).length,0,JSON.stringify(row));
    assert.match(panel.element.textContent,/확인할 수 없어/);
    assert.doesNotMatch(panel.element.textContent,/SECRET/);
  }
  for(const body of [{items:'x'},{items:[],extra:1},null,[]]){
    const {panel}=setup(c,{list:()=>res(200,body)});await panel.open(c);
    assert.equal(rows(panel).length,0);assert.match(panel.element.textContent,/확인할 수 없어/);
  }
  const dup=setup(c,{list:()=>res(200,{items:[task(c),task(c)]})});await dup.panel.open(c);assert.equal(rows(dup.panel).length,0);
});

test('다른 원고·버전의 작업은 목록·합성·resume 응답 모두 거부하고 콜백하지 않는다',async()=>{
  const c=content();
  for(const over of [{content_id:'other'},{input_revision:4}]){
    const s=setup(c,{list:()=>res(200,{items:[task(c,over)]})});await s.panel.open(c);
    assert.equal(rows(s.panel).length,0);assert.equal(s.done.length,0);
  }
  const s=setup(c,{
    list:()=>res(200,{items:[task(c,{task_id:'tp',state:'pending'})]}),
    create:()=>res(200,task(c,{task_id:'x',content_id:'other',state:'completed'})),
    resume:()=>res(200,task(c,{task_id:'tp',input_revision:9,state:'completed'})),
  });
  await s.panel.open(c);await typeScript(s.panel,'대본');
  await btn(s.panel,'create').fire('click');
  assert.equal(rows(s.panel).length,1);assert.match(s.panel.element.textContent,/결과를 알 수 없습니다/);assert.equal(s.panel.isDirty(),true);
  await by(s.panel.element,'data-voice-resume','tp')[0].fire('click');
  assert.equal(rows(s.panel)[0].getAttribute('data-voice-task'),'tp');assert.match(rows(s.panel)[0].textContent,/합성이 진행 중/);
  assert.equal(s.done.length,0);
  // resume 응답이 다른 task_id여도 거부한다.
  const t=setup(c,{list:()=>res(200,{items:[task(c,{task_id:'tp',state:'pending'})]}),resume:()=>res(200,task(c,{task_id:'zz',state:'completed'}))});
  await t.panel.open(c);await by(t.panel.element,'data-voice-resume','tp')[0].fire('click');
  assert.equal(t.done.length,0);assert.equal(rows(t.panel).length,1);
});

test('완료 콜백은 같은 open 맥락에서 task_id마다 한 번만 호출되고 새로 열면 다시 호출된다',async()=>{
  const c=content();let items=[task(c,{task_id:'td',state:'completed'}),task(c,{task_id:'tp',state:'pending'})];
  const {panel,done,calls}=setup(c,{list:()=>res(200,{items}),resume:()=>res(200,task(c,{task_id:'tp',state:'completed'}))});
  await panel.open(c);
  assert.deepEqual(done.map(r=>r.task_id),['td']);
  assert.deepEqual(Object.keys(done[0]),['task_id','state','reason_code','content_id','input_revision','output_revision','asset_id','seconds','review_status','voice_label','generation_id']);
  await btn(panel,'reload').fire('click');await btn(panel,'reload').fire('click');
  assert.deepEqual(done.map(r=>r.task_id),['td']);
  await by(panel.element,'data-voice-resume','tp')[0].fire('click');
  assert.deepEqual(done.map(r=>r.task_id),['td','tp']);
  items=[task(c,{task_id:'td'}),task(c,{task_id:'tp'})];
  await btn(panel,'reload').fire('click');
  assert.deepEqual(done.map(r=>r.task_id),['td','tp']);
  assert.equal(posts(calls).length,1);
  await panel.open(c);
  assert.deepEqual(done.map(r=>r.task_id),['td','tp','td','tp']);
});

test('개인·학과 capability 조회는 실제 원고 소유 계정에 결속한다',async()=>{
 for(const owner of ['personal','dept']){
  const c=content({owner_account_id:owner}),calls=[];const {document}=harness();
  const panel=createVoiceTaskPanel({document,fetcher:async(url,init)=>{calls.push([url,init]);return res(200,url.startsWith(CAPS_URL)?cap():{items:[]});}});
  await panel.open(c);
  assert.equal(calls[0][0],CAPS_URL+'?account='+owner);
  assert.equal(calls.every(([,i])=>i.method==='GET'),true);
 }
});
