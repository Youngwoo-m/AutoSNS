import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createVideoTaskPanel} from '../ax-console/app/web/video_task_panel.js';

const CAPS_URL='/api/v2/video/capabilities';
const REVIEW_URL='/api/v2/video-tasks/t1/review';
const content=(over={})=>({id:'c/1',revision:3,manifest_hash:'h'.repeat(64),owner_account_id:'personal',title:'원고',...over});
const cap=()=>({provider_id:'remotion-local',service_available:true,execution_enabled:true,review_status:'not_checked'});
const planRow=c=>({content_id:c.id,content_revision:c.revision,manifest_hash:c.manifest_hash,owner_account_id:c.owner_account_id,plan_revision:2,plan:{exam:'',field:'',source:'',footer:'',disclosure:'',voice_asset_id:'v1',scenes:[{asset_id:'i1',kind:'diorama',seconds:5,title:'',caption:''}]},inputs_ready:true,blockers:[],execution_enabled:false,review_status:'not_checked'});
const task=(c,over={})=>({task_id:'t1',state:'queued',reason_code:null,content_id:c.id,input_revision:c.revision,plan_revision:2,output_revision:null,asset_id:null,review_status:'not_checked',...over});
const waiting=(c,over={})=>task(c,{state:'awaiting_review',reason_code:'video_review_required',...over});
const done=(c,over={})=>task(c,{state:'completed',output_revision:c.revision+1,asset_id:'a1',...over});
const media=(over={})=>({filename:'short.mp4',media_type:'video/mp4',size:12345,sha256:'b'.repeat(64),seconds:12.5,width:1080,height:1920,has_audio:true,...over});
const manifest=(over={})=>({exam:'기술사',field:'방재',source:'소방청 자료',footer:'하단문구',disclosure:'AI 합성 음성 고지',scenes:[{index:1,kind:'diorama',seconds:5,title:'첫 장면',caption:'첫 자막'},{index:2,kind:'diagram',seconds:7,title:'둘째 장면',caption:'둘째 자막'}],scene_count:2,...over});
const reviewBody=(c,over={})=>({task_id:'t1',state:'awaiting_review',content_id:c.id,input_revision:c.revision,plan_revision:2,context_fingerprint:'a'.repeat(64),scene_count:2,media:media(),manifest:manifest(),review_status:'not_checked',...over});
const res=(status,body)=>({ok:status<400,status,json:async()=>body});
const deferred=()=>{let resolve;const promise=new Promise(r=>{resolve=r;});return {promise,resolve};};
const by=(root,attr,value)=>all(root).filter(n=>n.getAttribute(attr)===value);
const btn=(p,name)=>by(p.element,'data-video-action',name)[0];
const fld=(p,name)=>by(p.element,'data-video-field',name)[0];
const rows=p=>all(p.element).filter(n=>n.getAttribute('data-video-task')!==null);
const hasForm=p=>by(p.element,'data-video-review','t1').length>0;
const posts=calls=>calls.filter(([,i])=>i.method==='POST');
const force=(n,type='click')=>[...n.listeners.get(type)][0]({target:n,preventDefault(){}});
const KEYS=['audio_checked','font_checked','disclosure_checked','scenes_checked'];
const server=(c,over={})=>{
  const st={caps:()=>res(200,cap()),plan:()=>res(200,planRow(c)),list:()=>res(200,{items:[waiting(c)]}),review:()=>res(200,reviewBody(c)),submit:()=>res(200,done(c)),resume:()=>res(404,{}),create:()=>res(404,{}),...over};const calls=[];
  const fetcher=(url,init={})=>{
    calls.push([url,init]);
    const pick=url===CAPS_URL?st.caps:url.includes('/media-plan?')?st.plan:url.includes('/video-tasks?revision=')?st.list:/\/review$/.test(url)?(init.method==='POST'?st.submit:st.review):/\/resume$/.test(url)?st.resume:st.create;
    return Promise.resolve().then(()=>pick(url,init));
  };
  return {fetcher,calls,st};
};
const setup=(c,over,{timeout}={})=>{
  const {document}=harness();const s=server(c,over);const changes=[];const completed=[];
  const panel=createVideoTaskPanel({document,fetcher:s.fetcher,onChange:()=>changes.push(1),onCompleted:r=>completed.push(r),...(timeout?{requestTimeoutMs:timeout}:{})});
  return {panel,document,changes,completed,...s};
};
const opened=async(over,opts)=>{const c=content();const s=setup(c,over,opts);await s.panel.open(c);await btn(s.panel,'review-open').fire('click');return {c,...s};};
const check=async(p,key,value=true)=>{const b=fld(p,'check:'+key);b.checked=value;await b.fire('change');};
const checkAll=async p=>{for(const k of KEYS)await check(p,k);};

test('awaiting_review 행만 검토 열기를 두고 GET 한 번에 고정 미리보기 주소·영상 정보를 보여주며 비공개 필드 응답은 통째로 버린다',async()=>{
  const c=content();
  const items=[waiting(c),task(c,{task_id:'tq'}),task(c,{task_id:'tr',state:'rendering'}),task(c,{task_id:'tu',state:'unknown'}),task(c,{task_id:'tx',state:'rendered'}),done(c,{task_id:'td'}),task(c,{task_id:'tb',state:'blocked'})];
  const s=setup(c,{list:()=>res(200,{items})});await s.panel.open(c);
  assert.deepEqual(by(s.panel.element,'data-video-action','review-open').map(n=>n.getAttribute('data-video-review-open')),['t1']);
  assert.equal(btn(s.panel,'enqueue').disabled,true);
  const n=s.calls.length;await btn(s.panel,'review-open').fire('click');
  assert.equal(s.calls.length,n+1);assert.deepEqual([s.calls[n][0],s.calls[n][1].method,s.calls[n][1].body],[REVIEW_URL,'GET',undefined]);
  const player=all(s.panel.element).find(x=>x.tagName==='video');
  assert.equal(player.getAttribute('src'),'/api/v2/video-tasks/t1/preview');assert.notEqual(player.getAttribute('controls'),null);
  assert.equal(player.getAttribute('autoplay'),null);assert.equal(player.getAttribute('preload'),'none');
  const text=s.panel.element.textContent;
  for(const re of [/1080×1920/,/12\.5초/,/short\.mp4/,/video\/mp4/,/첫 장면/,/둘째 자막/,/소방청 자료/,/AI 합성 음성 고지/,/사람이 확인한 수동 기록입니다\. 독립 AI 검사나 최종 콘텐츠 검토 완료를 뜻하지 않습니다\./,/검토 저장·영상 등록/,/검토 확인 후 등록/,/수정 요청/])assert.match(text,re);
  assert.deepEqual(all(s.panel.element).filter(x=>x.getAttribute('data-video-field')?.startsWith('check:')).map(x=>x.getAttribute('data-video-field').slice(6)),KEYS);
  assert.equal(fld(s.panel,'notes').getAttribute('maxlength'),'2000');assert.equal(s.panel.isDirty(),false);
  assert.equal(posts(s.calls).length,0);
  const bad=[
    reviewBody(c,{preview_url:'http://evil/SECRET'}),reviewBody(c,{media:{...media(),path:'/Users/x/SECRET'}}),reviewBody(c,{manifest:{...manifest(),script:'SECRET'}}),
    reviewBody(c,{task_id:'t2'}),reviewBody(c,{content_id:'o'}),reviewBody(c,{input_revision:4}),reviewBody(c,{plan_revision:3}),reviewBody(c,{state:'completed'}),
    reviewBody(c,{context_fingerprint:'x'}),reviewBody(c,{scene_count:0}),reviewBody(c,{scene_count:3}),reviewBody(c,{review_status:'passed'}),
    reviewBody(c,{media:media({filename:'other.mp4'})}),reviewBody(c,{media:media({media_type:'video/webm'})}),reviewBody(c,{media:media({size:0})}),reviewBody(c,{media:media({sha256:'z'})}),
    reviewBody(c,{media:media({seconds:21})}),reviewBody(c,{media:media({seconds:null})}),reviewBody(c,{media:media({width:1081})}),reviewBody(c,{media:media({height:1080})}),reviewBody(c,{media:media({has_audio:false})}),
    reviewBody(c,{manifest:manifest({scene_count:1})}),reviewBody(c,{manifest:manifest({exam:5})}),
    reviewBody(c,{manifest:manifest({scenes:[{index:2,kind:'diorama',seconds:5,title:'',caption:''},{index:1,kind:'diagram',seconds:7,title:'',caption:''}]})}),
    reviewBody(c,{manifest:manifest({scenes:[{index:1,kind:'photo',seconds:5,title:'',caption:''},{index:2,kind:'diagram',seconds:7,title:'',caption:''}]})}),
    reviewBody(c,{manifest:manifest({scenes:[{index:1,kind:'diorama',seconds:0,title:'',caption:''},{index:2,kind:'diagram',seconds:7,title:'',caption:''}]})}),
    null,[],
  ];
  for(const body of bad){
    const b=setup(c,{review:()=>res(200,body)});await b.panel.open(c);await btn(b.panel,'review-open').fire('click');
    assert.equal(hasForm(b.panel),false,JSON.stringify(body));assert.equal(all(b.panel.element).some(x=>x.tagName==='video'),false);
    assert.doesNotMatch(b.panel.element.textContent,/SECRET|evil/);assert.equal(b.panel.isBusy(),false);assert.equal(posts(b.calls).length,0);
  }
});

test('체크·결정·메모 입력은 다시 그리지 않아 포커스를 유지하고 부모 변경 알림과 제출 버튼만 갱신한다',async()=>{
  const {panel,document,changes}=await opened();
  const submit=btn(panel,'review-submit'),notes=fld(panel,'notes'),sel=fld(panel,'decision');
  assert.equal(submit.disabled,true);
  notes.focus();notes.value='글꼴 깨짐';const n=changes.length;await notes.fire('input');
  assert.equal(document.activeElement,notes);assert.equal(fld(panel,'notes'),notes);assert.equal(btn(panel,'review-submit'),submit);
  assert.equal(changes.length,n+1);assert.equal(panel.isDirty(),true);assert.equal(submit.disabled,true);
  notes.value='';await notes.fire('input');assert.equal(panel.isDirty(),false);
  for(const k of KEYS){const b=fld(panel,'check:'+k);b.focus();b.checked=true;await b.fire('change');assert.equal(document.activeElement,b);assert.equal(fld(panel,'check:'+k),b);}
  assert.equal(btn(panel,'review-submit'),submit);assert.equal(submit.disabled,false);assert.equal(panel.isDirty(),true);
  sel.focus();sel.value='changes_requested';await sel.fire('change');
  assert.equal(submit.disabled,true);notes.value='  ';await notes.fire('input');assert.equal(submit.disabled,true);
  notes.value='수정 필요';await notes.fire('input');assert.equal(submit.disabled,false);
  notes.value='x'.repeat(2001);await notes.fire('input');assert.equal(notes.value.length,2000);
  // 다른 이유로 다시 그려도 포커스와 입력값이 이어진다.
  notes.focus();panel.refreshControls({writable:false});panel.refreshControls({writable:true});
  assert.equal(document.activeElement,fld(panel,'notes'));assert.equal(fld(panel,'notes').value.length,2000);assert.equal(fld(panel,'decision').value,'changes_requested');assert.equal(fld(panel,'check:audio_checked').checked,true);
});

test('통과 저장은 정확한 필드만 POST하고 성공하면 초안을 지우고 완료 콜백을 부르며 수정 요청은 blocked로 기록한다',async()=>{
  const a=await opened();
  await checkAll(a.panel);await btn(a.panel,'review-submit').fire('click');
  const sent=posts(a.calls);assert.equal(sent.length,1);assert.equal(sent[0][0],REVIEW_URL);
  const body=JSON.parse(sent[0][1].body);
  assert.deepEqual(Object.keys(body),['context_fingerprint','decision','checks','notes']);
  assert.deepEqual(body,{context_fingerprint:'a'.repeat(64),decision:'pass',checks:{audio_checked:true,font_checked:true,disclosure_checked:true,scenes_checked:true},notes:''});
  assert.equal(hasForm(a.panel),false);assert.equal(a.panel.isDirty(),false);assert.equal(a.panel.isBusy(),false);
  assert.deepEqual(rows(a.panel).map(n=>n.getAttribute('data-video-task')),['t1']);assert.match(a.panel.element.textContent,/영상 생성과 자산 등록이 끝났습니다 · 검토 전/);
  assert.deepEqual(a.completed.map(r=>r.task_id),['t1']);assert.equal(a.completed[0].review_status,'not_checked');assert.equal(btn(a.panel,'review-open'),undefined);
  // pass 응답이 rendered여도 받아들이고 재개 버튼이 나온다.
  const r=await opened({submit:()=>res(200,task(content(),{state:'rendered'}))});
  await checkAll(r.panel);await btn(r.panel,'review-submit').fire('click');
  assert.equal(hasForm(r.panel),false);assert.equal(r.completed.length,0);assert.equal(btn(r.panel,'review-submit'),undefined);
  assert.equal(by(r.panel.element,'data-video-resume','t1').length,1);
  const c=content();
  const x=await opened({submit:()=>res(200,task(c,{state:'blocked',reason_code:'video_review_changes_requested'}))});
  const sel=fld(x.panel,'decision');sel.value='changes_requested';await sel.fire('change');
  const notes=fld(x.panel,'notes');notes.value=' 글꼴이 깨집니다 ';await notes.fire('input');
  await btn(x.panel,'review-submit').fire('click');
  assert.deepEqual(JSON.parse(posts(x.calls)[0][1].body),{context_fingerprint:'a'.repeat(64),decision:'changes_requested',checks:{audio_checked:false,font_checked:false,disclosure_checked:false,scenes_checked:false},notes:' 글꼴이 깨집니다 '});
  assert.equal(hasForm(x.panel),false);assert.match(x.panel.element.textContent,/수정 요청이 기록되어 영상을 등록하지 않았습니다/);assert.match(x.panel.element.textContent,/제작 조건이 맞지 않아/);
  assert.equal(x.completed.length,0);assert.equal(by(x.panel.element,'data-video-resume','t1').length,0);
  // 통과 요청에 blocked, 수정 요청에 completed가 오면 형식 오류로 보고 초안을 보존한다.
  const m=await opened({submit:()=>res(200,task(c,{state:'blocked'}))});
  await checkAll(m.panel);await btn(m.panel,'review-submit').fire('click');
  assert.equal(hasForm(m.panel),true);assert.equal(m.panel.isDirty(),true);assert.equal(m.completed.length,0);
});

test('체크가 모자란 통과·메모 없는 수정 요청은 버튼과 handler 모두 POST를 보내지 않는다',async()=>{
  const {panel,calls}=await opened();
  for(const k of KEYS.slice(0,3))await check(panel,k);
  assert.equal(btn(panel,'review-submit').disabled,true);await force(btn(panel,'review-submit'));await btn(panel,'review-submit').fire('click');
  assert.equal(posts(calls).length,0);
  const sel=fld(panel,'decision');sel.value='changes_requested';await sel.fire('change');
  const notes=fld(panel,'notes');notes.value=' \n ';await notes.fire('input');
  await force(btn(panel,'review-submit'));assert.equal(posts(calls).length,0);
  // 알 수 없는 결정 값은 초안에 반영되지 않는다.
  sel.value='bogus';await sel.fire('change');
  notes.value='메모';await notes.fire('input');await force(btn(panel,'review-submit'));
  assert.equal(JSON.parse(posts(calls)[0][1].body).decision,'changes_requested');
});

test('전송 중 중복 저장은 막고 입력 handler도 잠기며 503 응답에도 초안을 보존하고 목록 확인 전 재전송하지 않는다',async()=>{
  const gate=deferred();const {panel,calls}=await opened({submit:()=>gate.promise});
  await checkAll(panel);
  const submit=btn(panel,'review-submit');const first=submit.fire('click');
  assert.equal(panel.isBusy(),true);await submit.fire('click');await force(submit);await force(btn(panel,'review-submit'));
  assert.equal(posts(calls).length,1);
  const box=fld(panel,'check:audio_checked'),notes=fld(panel,'notes');
  assert.equal(box.disabled,true);assert.equal(notes.disabled,true);assert.equal(fld(panel,'decision').disabled,true);
  assert.equal(btn(panel,'review-discard').disabled,true);assert.equal(btn(panel,'reload').disabled,true);
  box.checked=false;await force(box,'change');notes.value='끼어든 입력';await force(notes,'input');
  await force(btn(panel,'review-discard'));assert.equal(hasForm(panel),true);
  gate.resolve(res(503,{}));await first;
  assert.equal(posts(calls).length,1);assert.equal(panel.isBusy(),false);assert.equal(hasForm(panel),true);
  assert.deepEqual(KEYS.map(k=>fld(panel,'check:'+k).checked),[true,true,true,true]);assert.equal(fld(panel,'notes').value,'');
  assert.match(panel.element.textContent,/다시 조회해 확인하기 전에는 다시 보내지 마세요/);
  assert.equal(btn(panel,'review-submit').disabled,true);await force(btn(panel,'review-submit'));assert.equal(posts(calls).length,1);
  await btn(panel,'reload').fire('click');
  assert.equal(hasForm(panel),true);assert.equal(btn(panel,'review-submit').disabled,false);assert.equal(posts(calls).length,1);
});

test('409·401·시간 초과는 모든 입력을 보존하고 자동 재전송이 없으며 409는 재조회 뒤에만 다시 열린다',async()=>{
  let status=409;
  const {panel,calls}=await opened({submit:()=>res(status,{})});
  await checkAll(panel);const sel=fld(panel,'decision');
  const notes=fld(panel,'notes');notes.value='메모';await notes.fire('input');
  await btn(panel,'review-submit').fire('click');
  assert.equal(posts(calls).length,1);assert.equal(hasForm(panel),true);assert.equal(panel.isDirty(),true);assert.equal(fld(panel,'notes').value,'메모');
  assert.match(panel.element.textContent,/저장되지 않았습니다/);assert.equal(btn(panel,'review-submit').disabled,true);
  await force(btn(panel,'review-submit'));assert.equal(posts(calls).length,1);
  await btn(panel,'reload').fire('click');
  assert.equal(hasForm(panel),true);assert.equal(fld(panel,'notes').value,'메모');assert.equal(btn(panel,'review-submit').disabled,false);
  status=401;await btn(panel,'review-submit').fire('click');
  assert.equal(posts(calls).length,2);assert.match(panel.element.textContent,/로그인 후 다시 시도하세요/);assert.equal(fld(panel,'notes').value,'메모');
  assert.equal(btn(panel,'review-submit').disabled,false);
  const hang=await opened({submit:()=>new Promise(()=>{})},{timeout:5});
  await checkAll(hang.panel);await btn(hang.panel,'review-submit').fire('click');
  assert.equal(hang.panel.isBusy(),false);assert.equal(posts(hang.calls).length,1);assert.equal(hasForm(hang.panel),true);assert.equal(hang.panel.isDirty(),true);
  assert.equal(btn(hang.panel,'review-submit').disabled,true);await force(btn(hang.panel,'review-submit'));assert.equal(posts(hang.calls).length,1);
});

test('다른 원고로 바뀌거나 닫힌 뒤 도착한 검토 GET·POST 응답은 화면·콜백·초안에 반영되지 않는다',async()=>{
  const c=content();const gate=deferred();let slow=true;
  const a=setup(c,{review:()=>slow?gate.promise:res(200,reviewBody(c))});await a.panel.open(c);
  const loading=btn(a.panel,'review-open').fire('click');
  assert.equal(a.panel.isBusy(),true);
  await a.panel.open(null);gate.resolve(res(200,reviewBody(c)));await loading;
  assert.equal(a.panel.isBusy(),false);assert.equal(hasForm(a.panel),false);assert.equal(a.panel.isDirty(),false);
  slow=false;
  const post=deferred();const b=setup(c,{submit:()=>post.promise});await b.panel.open(c);await btn(b.panel,'review-open').fire('click');
  await checkAll(b.panel);const sending=btn(b.panel,'review-submit').fire('click');
  await b.panel.open(c);
  post.resolve(res(200,done(c)));await sending;
  assert.equal(hasForm(b.panel),false);assert.equal(b.panel.isDirty(),false);assert.equal(b.completed.length,0);assert.equal(posts(b.calls).length,1);
  assert.deepEqual(rows(b.panel).map(n=>n.getAttribute('data-video-task')),['t1']);assert.match(b.panel.element.textContent,/사람 검토 기록이 남아/);
  const d=setup(c);await d.panel.open(c);await btn(d.panel,'review-open').fire('click');await check(d.panel,'audio_checked');
  await d.panel.open(content({id:'x2'}));assert.equal(hasForm(d.panel),false);assert.equal(d.panel.isDirty(),false);
});

test('목록 재조회로 작업이 완료돼도 입력이 남은 초안은 제출만 막은 채 유지되고 버리기 확인 뒤 풀리며 파일·작업은 지우지 않는다',async()=>{
  const c=content();let items=[waiting(c)];
  const s=setup(c,{list:()=>res(200,{items})});await s.panel.open(c);await btn(s.panel,'review-open').fire('click');
  // 깨끗한 초안은 재조회하면 닫힌다.
  await btn(s.panel,'reload').fire('click');assert.equal(hasForm(s.panel),false);
  await btn(s.panel,'review-open').fire('click');
  await check(s.panel,'font_checked');
  // 입력이 남은 동안 다시 여는 GET은 덮어쓰지 않고 거부한다.
  const n=s.calls.length;assert.equal(btn(s.panel,'review-open').disabled,true);await force(btn(s.panel,'review-open'));await btn(s.panel,'review-open').fire('click');
  assert.equal(s.calls.length,n);
  items=[done(c)];await btn(s.panel,'reload').fire('click');
  assert.deepEqual(s.completed.map(r=>r.task_id),['t1']);
  assert.equal(hasForm(s.panel),true);assert.equal(s.panel.isDirty(),true);assert.equal(btn(s.panel,'review-submit').disabled,true);
  assert.match(s.panel.element.textContent,/더 이상 검토 대기 상태가 아니라/);
  await checkAll(s.panel);assert.equal(btn(s.panel,'review-submit').disabled,true);await force(btn(s.panel,'review-submit'));assert.equal(posts(s.calls).length,0);
  const saved=globalThis.confirm;const asked=[];
  try{
    globalThis.confirm=m=>{asked.push(m);return false;};
    const before=s.changes.length;await btn(s.panel,'review-discard').fire('click');
    assert.equal(asked.length,1);assert.equal(hasForm(s.panel),true);assert.equal(s.panel.isDirty(),true);assert.equal(s.changes.length,before);
    globalThis.confirm=m=>{asked.push(m);return true;};
    await btn(s.panel,'review-discard').fire('click');
    assert.equal(asked.length,2);assert.equal(hasForm(s.panel),false);assert.equal(s.panel.isDirty(),false);assert.ok(s.changes.length>before);
  }finally{globalThis.confirm=saved;}
  assert.ok(s.calls.every(([,i])=>i.method==='GET'));assert.deepEqual(rows(s.panel).map(r=>r.getAttribute('data-video-task')),['t1']);
  // 부모가 부르는 discardChanges도 초안만 지우고 onChange를 호출한다.
  items=[waiting(c)];await btn(s.panel,'reload').fire('click');await btn(s.panel,'review-open').fire('click');await check(s.panel,'audio_checked');
  const before=s.changes.length;s.panel.discardChanges();
  assert.equal(hasForm(s.panel),false);assert.equal(s.panel.isDirty(),false);assert.ok(s.changes.length>before);assert.equal(rows(s.panel).length,1);assert.ok(s.calls.every(([,i])=>i.method==='GET'));
});

test('읽기 전용에서는 검토 GET만 허용하고 입력·제출 handler를 잠그며 같은 값 refreshControls는 다시 그리지 않고 풀리면 이어서 쓸 수 있다',async()=>{
  const c=content();const s=setup(c);await s.panel.open(c,{writable:false});
  await btn(s.panel,'review-open').fire('click');
  assert.equal(hasForm(s.panel),true);
  for(const k of KEYS)assert.equal(fld(s.panel,'check:'+k).disabled,true);
  assert.equal(fld(s.panel,'notes').disabled,true);assert.equal(fld(s.panel,'decision').disabled,true);assert.equal(btn(s.panel,'review-submit').disabled,true);
  const box=fld(s.panel,'check:audio_checked'),notes=fld(s.panel,'notes'),sel=fld(s.panel,'decision');
  box.checked=true;await force(box,'change');notes.value='메모';await force(notes,'input');sel.value='changes_requested';await force(sel,'change');
  await force(btn(s.panel,'review-submit'));
  assert.equal(s.panel.isDirty(),false);assert.equal(posts(s.calls).length,0);
  const same=btn(s.panel,'review-submit');s.panel.refreshControls({writable:false});s.panel.refreshControls({});
  assert.equal(btn(s.panel,'review-submit'),same);
  s.panel.refreshControls({writable:true});
  assert.notEqual(btn(s.panel,'review-submit'),same);assert.equal(hasForm(s.panel),true);
  assert.equal(fld(s.panel,'notes').disabled,false);assert.equal(fld(s.panel,'check:audio_checked').checked,false);
  await check(s.panel,'audio_checked');assert.equal(s.panel.isDirty(),true);
  s.panel.refreshControls({writable:false});assert.equal(btn(s.panel,'review-submit').disabled,true);assert.equal(s.panel.isDirty(),true);
});
