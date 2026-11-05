import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createVideoTaskPanel} from '../ax-console/app/web/video_task_panel.js';

const CAPS_URL='/api/v2/video/capabilities';
const PLAN_URL='/api/v2/contents/c%2F1/media-plan?revision=3';
const LIST_URL='/api/v2/contents/c%2F1/video-tasks?revision=3';
const content=(over={})=>({id:'c/1',revision:3,manifest_hash:'h'.repeat(64),owner_account_id:'personal',title:'원고',...over});
const cap=(over={})=>({provider_id:'remotion-local',service_available:true,execution_enabled:true,review_status:'not_checked',...over});
const planRow=(c,over={})=>({content_id:c.id,content_revision:c.revision,manifest_hash:c.manifest_hash,owner_account_id:c.owner_account_id,plan_revision:2,plan:{exam:'',field:'',source:'',footer:'',disclosure:'',voice_asset_id:'v1',scenes:[{asset_id:'i1',kind:'diorama',seconds:5,title:'',caption:''}]},inputs_ready:true,blockers:[],execution_enabled:false,review_status:'not_checked',...over});
const task=(c,over={})=>({task_id:'t1',state:'queued',reason_code:null,content_id:c.id,input_revision:c.revision,plan_revision:2,output_revision:null,asset_id:null,review_status:'not_checked',...over});
const done=(c,over={})=>task(c,{state:'completed',output_revision:c.revision+1,asset_id:'a1',...over});
const res=(status,body)=>({ok:status<400,status,json:async()=>body});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const by=(root,attr,value)=>all(root).filter(n=>n.getAttribute(attr)===value);
const btn=(p,name)=>by(p.element,'data-video-action',name)[0];
const rows=p=>all(p.element).filter(n=>n.getAttribute('data-video-task')!==null);
const resumeBtn=(p,id)=>by(p.element,'data-video-resume',id)[0];
const posts=calls=>calls.filter(([,i])=>i.method==='POST');
// disabled 속성을 우회해 handler 내부 guard만 시험한다.
const force=(n,type='click')=>[...n.listeners.get(type)][0]({target:n,preventDefault(){}});
const server=(c,over={})=>{
  const st={caps:()=>res(200,cap()),plan:()=>res(200,planRow(c)),list:()=>res(200,{items:[]}),create:()=>res(404,{}),resume:()=>res(404,{}),...over};const calls=[];
  const fetcher=(url,init={})=>{
    calls.push([url,init]);
    const pick=url===CAPS_URL?st.caps:url.includes('/media-plan?')?st.plan:url.includes('/video-tasks?revision=')?st.list:/\/resume$/.test(url)?st.resume:st.create;
    return Promise.resolve().then(()=>pick(url,init));
  };
  return {fetcher,calls,st};
};
const setup=(c,over,{timeout}={})=>{
  const {document}=harness();const s=server(c,over);const changes=[];const completed=[];
  const panel=createVideoTaskPanel({document,fetcher:s.fetcher,onChange:()=>changes.push(1),onCompleted:r=>completed.push(r),...(timeout?{requestTimeoutMs:timeout}:{})});
  return {panel,changes,completed,...s};
};

test('열기는 caps·계획·작업 목록 GET 세 번만 하고 POST가 없으며 원고 정보와 규격을 표시한다',async()=>{
  const c=content();const gate=deferred();
  const {panel,calls}=setup(c,{list:()=>gate.promise});
  const opening=panel.open(c);
  assert.equal(panel.isBusy(),true);
  gate.resolve(res(200,{items:[task(c)]}));await opening;
  assert.deepEqual(calls.map(([u])=>u).sort(),[CAPS_URL,LIST_URL,PLAN_URL].sort());
  assert.ok(calls.every(([,i])=>i.method==='GET'&&i.body===undefined));
  assert.equal(posts(calls).length,0);
  assert.equal(panel.element.tagName,'details');
  assert.equal(all(panel.element).find(n=>n.tagName==='summary').textContent,'영상 제작');
  assert.equal(panel.isDirty(),false);assert.equal(panel.isBusy(),false);
  const text=panel.element.textContent;
  assert.match(text,/소유 계정 개인/);assert.match(text,/원고 버전 3/);assert.match(text,/저장된 계획 버전 2/);
  assert.match(text,/1080×1920/);assert.match(text,/20초 이하/);assert.match(text,/WAV/);assert.match(text,/품질 검토를 마쳤다는 뜻이 아닙니다/);
  panel.discardChanges();assert.equal(panel.isDirty(),false);
});

test('제작 요청 버튼은 writable·caps·준비된 계획·계획 버전 1 이상·idle일 때만 열리고 handler guard도 막는다',async()=>{
  const c=content();
  const variants=[
    ['service꺼짐',{caps:()=>res(200,cap({service_available:false}))}],
    ['execution꺼짐',{caps:()=>res(200,cap({execution_enabled:false}))}],
    ['caps실패',{caps:()=>res(500,{})}],
    ['입력 미준비',{plan:()=>res(200,planRow(c,{inputs_ready:false,blockers:['voice_required']}))}],
    ['계획 없음',{plan:()=>res(200,planRow(c,{plan_revision:0,inputs_ready:true}))}],
    ['계획 실패',{plan:()=>{throw new Error('offline');}}],
  ];
  for(const [name,over] of variants){
    const {panel,calls}=setup(c,over);await panel.open(c);
    assert.equal(btn(panel,'enqueue').disabled,true,name);
    await force(btn(panel,'enqueue'));await btn(panel,'enqueue').fire('click');
    assert.equal(posts(calls).length,0,name);
  }
  const ready=setup(c);await ready.panel.open(c);
  assert.equal(btn(ready.panel,'enqueue').disabled,false);
  const notReady=setup(c,{plan:()=>res(200,planRow(c,{inputs_ready:false,blockers:['voice_required']}))});await notReady.panel.open(c);
  assert.match(notReady.panel.element.textContent,/WAV 음성이 필요합니다/);
});

test('제작 요청 POST는 정확한 경로·body이고 대기열 등록이지 완료가 아니며 자동 재요청이 없다',async()=>{
  const c=content();
  const {panel,calls}=setup(c,{create:()=>res(200,task(c,{task_id:'t9'}))});
  await panel.open(c);
  await btn(panel,'enqueue').fire('click');
  const sent=posts(calls);assert.equal(sent.length,1);
  assert.equal(sent[0][0],'/api/v2/contents/c%2F1/video-tasks');
  assert.deepEqual(Object.keys(JSON.parse(sent[0][1].body)),['expected_revision','expected_plan_revision']);
  assert.deepEqual(JSON.parse(sent[0][1].body),{expected_revision:3,expected_plan_revision:2});
  assert.equal(rows(panel).length,1);
  assert.match(panel.element.textContent,/대기열에 등록/);assert.match(panel.element.textContent,/렌더링이 끝났다는 뜻이 아닙니다/);
  assert.equal(btn(panel,'enqueue').disabled,true);
  await Promise.resolve();assert.equal(posts(calls).length,1);
});

test('queued·preparing·rendering·unknown 작업이 있으면 새 제작 요청을 막고 완료·실패 작업만 있으면 허용한다',async()=>{
  const c=content();
  for(const state of ['queued','preparing','rendering','unknown']){
    const {panel,calls}=setup(c,{list:()=>res(200,{items:[task(c,{state})]})});await panel.open(c);
    assert.equal(btn(panel,'enqueue').disabled,true,state);await force(btn(panel,'enqueue'));assert.equal(posts(calls).length,0,state);
  }
  const ok=setup(c,{list:()=>res(200,{items:[done(c),task(c,{task_id:'t2',state:'failed',reason_code:'remotion_render_failed'})]})});await ok.panel.open(c);
  assert.equal(btn(ok.panel,'enqueue').disabled,false);
});

test('rendered에만 결과 등록 재개 버튼이 있고 preparing·rendering·unknown은 안내와 조회만 제공한다',async()=>{
  const c=content();
  const items=[task(c,{task_id:'tp',state:'preparing'}),task(c,{task_id:'tr',state:'rendering'}),task(c,{task_id:'tu',state:'unknown'}),task(c,{task_id:'tq',state:'queued'}),task(c,{task_id:'td',state:'blocked',reason_code:'media_inputs_required'}),task(c,{task_id:'tx',state:'rendered'})];
  const {panel,calls}=setup(c,{list:()=>res(200,{items}),resume:()=>res(200,done(c,{task_id:'tx'}))});
  await panel.open(c);
  for(const id of ['tp','tr','tu','tq','td'])assert.equal(resumeBtn(panel,id),undefined,id);
  assert.match(panel.element.textContent,/자동으로 다시 시작할 수 없습니다/);
  await force(btn(panel,'reload'));
  assert.equal(posts(calls).length,0);
  assert.equal(resumeBtn(panel,'tx').disabled,false);
  await resumeBtn(panel,'tx').fire('click');
  assert.equal(posts(calls).length,1);
  assert.equal(posts(calls)[0][0],'/api/v2/video-tasks/tx/resume');assert.equal(posts(calls)[0][1].body,'{}');
  assert.equal(resumeBtn(panel,'tx'),undefined);
  assert.match(panel.element.textContent,/영상 생성과 자산 등록이 끝났습니다 · 검토 전/);
});

test('전송 중 중복 제작 요청은 버튼·handler guard 모두 막고 응답 뒤 busy가 풀린다',async()=>{
  const c=content();const gate=deferred();
  const {panel,calls}=setup(c,{create:()=>gate.promise});
  await panel.open(c);
  const button=btn(panel,'enqueue');
  const first=button.fire('click');
  assert.equal(panel.isBusy(),true);
  await button.fire('click');await force(button);await force(btn(panel,'enqueue'));
  assert.equal(posts(calls).length,1);
  assert.equal(btn(panel,'enqueue').disabled,true);assert.equal(btn(panel,'reload').disabled,true);
  gate.resolve(res(200,task(c)));await first;
  assert.equal(posts(calls).length,1);assert.equal(panel.isBusy(),false);
});

test('409는 접수되지 않은 것으로 안내하되 기존 작업 목록을 보존하고 재조회로 갱신한다',async()=>{
  const c=content();let items=[done(c,{task_id:'old'})];
  const {panel,calls}=setup(c,{list:()=>res(200,{items}),create:()=>res(409,{})});
  await panel.open(c);
  await btn(panel,'enqueue').fire('click');
  assert.equal(posts(calls).length,1);
  assert.deepEqual(rows(panel).map(n=>n.getAttribute('data-video-task')),['old']);
  assert.match(panel.element.textContent,/접수되지 않았습니다/);assert.equal(panel.isBusy(),false);
  items=[done(c,{task_id:'old'}),task(c,{task_id:'new'})];
  await btn(panel,'reload').fire('click');
  assert.equal(rows(panel).length,2);assert.equal(posts(calls).length,1);
});

test('다른 원고의 늦은 응답과 재open·open(null) 뒤 POST 응답은 화면과 콜백에 반영되지 않는다',async()=>{
  const a=content({id:'a',owner_account_id:'personal'}),b=content({id:'b',owner_account_id:'dept'});
  const gateA=deferred();const completed=[];
  const {document}=harness();
  const fetcher=url=>{
    if(url===CAPS_URL)return Promise.resolve(res(200,cap()));
    if(url.includes('/a/'))return url.includes('/media-plan?')?Promise.resolve(res(200,planRow(a))):gateA.promise;
    if(url.includes('/media-plan?'))return Promise.resolve(res(200,planRow(b)));
    return Promise.resolve(res(200,{items:[done(b,{task_id:'tb'})]}));
  };
  const panel=createVideoTaskPanel({document,fetcher,onCompleted:r=>completed.push(r)});
  const openA=panel.open(a);await panel.open(b);
  gateA.resolve(res(200,{items:[done(a,{task_id:'ta'})]}));await openA;
  assert.deepEqual(rows(panel).map(n=>n.getAttribute('data-video-task')),['tb']);
  assert.match(panel.element.textContent,/소유 계정 학과/);assert.deepEqual(completed.map(r=>r.task_id),['tb']);
  const c=content();const post=deferred();const s=setup(c,{create:()=>post.promise});
  await s.panel.open(c);
  const sending=btn(s.panel,'enqueue').fire('click');
  await s.panel.open(null);
  post.resolve(res(200,done(c,{task_id:'late'})));await sending;
  assert.equal(s.panel.isBusy(),false);assert.equal(rows(s.panel).length,0);assert.equal(s.completed.length,0);
});

test('요청 시간 초과는 신호를 취소하고 busy를 풀며 재제작을 목록 확인 전까지 막고 자동 POST가 없다',async()=>{
  const c=content(),{document}=harness();let count=0,signal;
  const panel=createVideoTaskPanel({document,requestTimeoutMs:5,fetcher:async(url,options)=>{
    if(options.method==='POST'){count++;signal=options.signal;return new Promise(()=>{});}
    return res(200,url===CAPS_URL?cap():url.includes('/media-plan?')?planRow(c):{items:[]});
  }});
  await panel.open(c);
  await btn(panel,'enqueue').fire('click');
  assert.equal(panel.isBusy(),false);assert.equal(count,1);assert.equal(signal.aborted,true);
  assert.match(panel.element.textContent,/다시 조회해 확인하기 전에는 제작을 다시 요청하지 마세요/);
  assert.equal(btn(panel,'enqueue').disabled,true);await force(btn(panel,'enqueue'));assert.equal(count,1);
  await btn(panel,'reload').fire('click');
  assert.equal(btn(panel,'enqueue').disabled,false);
  // 본문 JSON 읽기가 멈춰도 deadline에 포함된다.
  const hang=createVideoTaskPanel({document:harness().document,requestTimeoutMs:5,fetcher:async()=>({ok:true,status:200,json:()=>new Promise(()=>{})})});
  await hang.open(c);assert.equal(hang.isBusy(),false);assert.match(hang.element.textContent,/확인하지 못해/);
});

test('조회 실패는 이전 작업 목록을 보존하고 제작·재개를 닫으며 형식 오류 응답의 비공개 값은 렌더링하지 않는다',async()=>{
  const c=content();let fail=false;
  const {panel,calls}=setup(c,{list:()=>fail?res(500,{}):res(200,{items:[task(c,{task_id:'tx',state:'rendered'})]})});
  await panel.open(c);assert.equal(resumeBtn(panel,'tx').disabled,false);
  fail=true;await btn(panel,'reload').fire('click');
  assert.deepEqual(rows(panel).map(n=>n.getAttribute('data-video-task')),['tx']);
  assert.equal(resumeBtn(panel,'tx').disabled,true);assert.equal(btn(panel,'enqueue').disabled,true);
  await force(resumeBtn(panel,'tx'));await force(btn(panel,'enqueue'));assert.equal(posts(calls).length,0);
  const bad=[
    {...task(c),script:'SECRET'},{...task(c),output_path:'/Users/x/SECRET'},
    (()=>{const r=task(c);delete r.plan_revision;return r;})(),
    task(c,{review_status:'passed'}),task(c,{task_id:'a/b'}),task(c,{task_id:'a'.repeat(101)}),task(c,{state:'running'}),
    task(c,{plan_revision:0}),task(c,{plan_revision:1.5}),task(c,{content_id:'other'}),task(c,{input_revision:4}),task(c,{output_revision:-1}),task(c,{asset_id:5}),
    done(c,{output_revision:c.revision}),done(c,{output_revision:null}),done(c,{asset_id:null}),done(c,{asset_id:''}),
  ];
  for(const row of bad){
    const s=setup(c,{list:()=>res(200,{items:[task(c,{task_id:'ok'}),row]})});await s.panel.open(c);
    assert.equal(rows(s.panel).length,0,JSON.stringify(row));assert.doesNotMatch(s.panel.element.textContent,/SECRET/);
    assert.equal(btn(s.panel,'enqueue').disabled,true);assert.equal(s.completed.length,0);
  }
  for(const body of [{items:'x'},{items:[],extra:1},null,[]]){const s=setup(c,{list:()=>res(200,body)});await s.panel.open(c);assert.equal(rows(s.panel).length,0);}
  for(const caps of [cap({extra:1}),cap({provider_id:'other'}),cap({review_status:'passed'}),cap({service_available:'yes'})]){const s=setup(c,{caps:()=>res(200,caps)});await s.panel.open(c);assert.equal(btn(s.panel,'enqueue').disabled,true);}
  for(const row of [planRow(c,{execution_enabled:true}),planRow(c,{content_revision:4}),planRow(c,{owner_account_id:'dept'}),planRow(c,{manifest_hash:'x'}),planRow(c,{plan_revision:-1}),planRow(c,{inputs_ready:'yes'}),planRow(c,{review_status:'passed'}),{...planRow(c),extra:1}]){const s=setup(c,{plan:()=>res(200,row)});await s.panel.open(c);assert.equal(btn(s.panel,'enqueue').disabled,true);}
  const unknownReason=setup(c,{list:()=>res(200,{items:[task(c,{state:'failed',reason_code:'Traceback /Users/x/SECRET'})]})});await unknownReason.panel.open(c);
  assert.doesNotMatch(unknownReason.panel.element.textContent,/SECRET|Traceback/);assert.match(unknownReason.panel.element.textContent,/자세한 사유는 표시하지 않습니다/);
});

test('완료 콜백은 같은 open 맥락에서 task_id마다 한 번만 호출되고 다시 열면 다시 호출된다',async()=>{
  const c=content();let items=[done(c,{task_id:'td'}),task(c,{task_id:'tx',state:'rendered'})];
  const {panel,completed,calls}=setup(c,{list:()=>res(200,{items}),resume:()=>res(200,done(c,{task_id:'tx'}))});
  await panel.open(c);
  assert.deepEqual(completed.map(r=>r.task_id),['td']);
  assert.deepEqual(Object.keys(completed[0]),['task_id','state','reason_code','content_id','input_revision','plan_revision','output_revision','asset_id','review_status']);
  await btn(panel,'reload').fire('click');await btn(panel,'reload').fire('click');
  assert.deepEqual(completed.map(r=>r.task_id),['td']);
  await resumeBtn(panel,'tx').fire('click');
  assert.deepEqual(completed.map(r=>r.task_id),['td','tx']);
  items=[done(c,{task_id:'td'}),done(c,{task_id:'tx'})];
  await btn(panel,'reload').fire('click');
  assert.deepEqual(completed.map(r=>r.task_id),['td','tx']);
  assert.equal(posts(calls).length,1);
  await panel.open(c);
  assert.deepEqual(completed.map(r=>r.task_id),['td','tx','td','tx']);
});

test('읽기 전용은 제작·재개를 잠그되 GET 재조회는 허용하고 같은 값 refreshControls는 다시 그리지 않는다',async()=>{
  const c=content();
  const {panel,calls}=setup(c,{list:()=>res(200,{items:[task(c,{task_id:'tx',state:'rendered'})]})});
  await panel.open(c,{writable:false});
  assert.equal(btn(panel,'enqueue').disabled,true);assert.equal(resumeBtn(panel,'tx').disabled,true);
  await force(btn(panel,'enqueue'));await force(resumeBtn(panel,'tx'));
  assert.equal(posts(calls).length,0);
  assert.match(panel.element.textContent,/저장한 뒤/);assert.match(panel.element.textContent,/저장된 계획 버전/);
  assert.equal(btn(panel,'reload').disabled,false);
  const n=calls.length;await btn(panel,'reload').fire('click');
  assert.equal(calls.length,n+3);assert.ok(calls.slice(n).every(([,i])=>i.method==='GET'));
  const same=btn(panel,'reload');panel.refreshControls({writable:false});panel.refreshControls({});
  assert.equal(btn(panel,'reload'),same);
  panel.refreshControls({writable:true});
  assert.notEqual(btn(panel,'reload'),same);
  assert.equal(btn(panel,'enqueue').disabled,true);assert.equal(resumeBtn(panel,'tx').disabled,false);
});
