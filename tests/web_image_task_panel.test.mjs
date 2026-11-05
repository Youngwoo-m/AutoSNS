import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createImageTaskPanel} from '../ax-console/app/web/image_task_panel.js';
const content=(over={})=>({id:'c/1',revision:3,manifest_hash:'a'.repeat(64),owner_account_id:'personal',title:'안전 수칙',...over});
const cap=(over={})=>({provider_id:'local-card',service_available:true,execution_enabled:true,review_status:'not_checked',...over});
const task=(c,over={})=>({task_id:'image_1',state:'completed',reason_code:null,content_id:c.id,input_revision:c.revision,output_revision:4,asset_id:'asset1',review_status:'not_checked',...over});
const res=(status,body)=>({ok:status<400,status,json:async()=>body});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const node=(p,attr,value)=>all(p.element).find(n=>n.getAttribute(attr)===value);
const btn=(p,name)=>node(p,'data-image-action',name),field=(p,name)=>node(p,'data-image-field',name);
const force=n=>[...n.listeners.get('click')][0]({target:n});
const setup=(c,options={})=>{const {document}=harness(),calls=[],done=[];const state={caps:()=>res(200,cap()),list:()=>res(200,{items:[]}),create:()=>res(200,task(c)),resume:()=>res(200,task(c)),...options};const panel=createImageTaskPanel({document,onCompleted:r=>done.push(r),fetcher:async(url,init)=>{calls.push([url,init]);return url.includes('capabilities')?state.caps():init.method==='GET'?state.list():url.endsWith('/resume')?state.resume():state.create();}});return {panel,calls,done,state};};
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const type=async(p,name,value)=>{const n=field(p,name);n.value=value;await n.fire('input');};

test('접힌 패널은 GET하지 않고 펼칠 때 capability·현재버전 작업만 조회한다',async()=>{
 const c=content(),{panel,calls}=setup(c);await panel.open(c);assert.equal(calls.length,0);assert.equal(panel.isDirty(),false);
 await expand(panel);assert.deepEqual(calls.map(([u])=>u),['/api/v2/capabilities/image-production','/api/v2/contents/c%2F1/image-tasks?revision=3']);
 assert.ok(calls.every(([,i])=>i.method==='GET'));assert.equal(field(panel,'title').value,c.title);assert.equal(panel.isDirty(),false);
 await panel.element.fire('toggle');assert.equal(calls.length,2);
});

test('명시 생성 한 번은 정확한 spec 한 번만 보내고 완료 통지는 중복하지 않는다',async()=>{
 const c=content(),{panel,calls,done,state}=setup(c);await panel.open(c);await expand(panel);await type(panel,'body','첫 번째 문장\n두 번째 문장');await type(panel,'footer','출처 확인 전');
 await btn(panel,'create').fire('click');const post=calls.filter(([,i])=>i.method==='POST');assert.equal(post.length,1);
 assert.deepEqual(JSON.parse(post[0][1].body),{expected_revision:3,spec:{template:'card',title:'안전 수칙',body:['첫 번째 문장','두 번째 문장'],footer:'출처 확인 전'}});
 assert.equal(done.length,1);assert.equal(panel.isDirty(),false);state.list=()=>res(200,{items:[task(c)]});await btn(panel,'reload').fire('click');assert.equal(done.length,1);
 assert.match(panel.element.textContent,/검토 전/);
});

test('서버 오류와 불명확한 응답은 입력을 보존하고 자동 재요청하지 않는다',async()=>{
 const c=content();for(const fail of [()=>res(409,{}),()=>res(503,{}),()=>{throw new Error('offline');},()=>res(200,task(c,{content_id:'other'}))]){
 const {panel,calls}=setup(c,{create:fail});await panel.open(c);await expand(panel);await type(panel,'body','남길 문장');await btn(panel,'create').fire('click');
 assert.equal(field(panel,'body').value,'남길 문장');assert.equal(panel.isDirty(),true);assert.equal(panel.isBusy(),false);assert.equal(calls.filter(([,i])=>i.method==='POST').length,1);}
});

test('disabled·readonly·불명확한 작업은 handler guard에서도 생성을 막는다',async()=>{
 const c=content();for(const options of [{caps:()=>res(200,cap({execution_enabled:false}))},{list:()=>res(200,{items:[task(c,{state:'unknown',output_revision:null,asset_id:null})]})},{list:()=>res(200,{items:[task(c,{state:'started',output_revision:null,asset_id:null})]})}]){
 const {panel,calls}=setup(c,options);await panel.open(c);await expand(panel);await type(panel,'body','문장');assert.equal(btn(panel,'create').disabled,true);await force(btn(panel,'create'));assert.equal(calls.filter(([,i])=>i.method==='POST').length,0);}
 const {panel,calls}=setup(c);await panel.open(c,{writable:false});await expand(panel);await force(btn(panel,'create'));assert.equal(calls.filter(([,i])=>i.method==='POST').length,0);
});

test('길이·빈 줄 입력 검증은 POST 전에 끝내며 discard는 기본 제목으로 복원한다',async()=>{
 const c=content(),{panel,calls}=setup(c);await panel.open(c);await expand(panel);
 for(const text of ['',Array(7).fill('문장').join('\n'),'가'.repeat(121)]){await type(panel,'body',text);await btn(panel,'create').fire('click');}
 assert.equal(calls.filter(([,i])=>i.method==='POST').length,0);await type(panel,'title','바꾼 제목');panel.discardChanges();assert.equal(field(panel,'title').value,c.title);assert.equal(field(panel,'body').value,'');assert.equal(panel.isDirty(),false);
});

test('rendered 작업만 명시 결과등록 재개하고 unknown에는 resume이 없다',async()=>{
 const c=content(),{panel,calls,done}=setup(c,{list:()=>res(200,{items:[task(c,{state:'rendered',output_revision:null,asset_id:null}),task(c,{task_id:'other',state:'unknown',output_revision:null,asset_id:null})]})});await panel.open(c);await expand(panel);
 const resumes=all(panel.element).filter(n=>n.getAttribute('data-image-action')==='resume');assert.equal(resumes.length,1);await resumes[0].fire('click');assert.deepEqual(JSON.parse(calls.at(-1)[1].body),{});assert.equal(calls.at(-1)[0],'/api/v2/image-tasks/image_1/resume');assert.equal(done.length,1);
});

test('잘못된 capability·작업 응답은 비공개 필드를 표시하거나 완료 통지하지 않는다',async()=>{
 const c=content();for(const bad of [{content_id:'other'},{input_revision:4},{extra:'PRIVATE'},{review_status:'passed'}]){const {panel,done}=setup(c,{list:()=>res(200,{items:[task(c,bad)]})});await panel.open(c);await expand(panel);assert.equal(done.length,0);assert.equal(btn(panel,'create').disabled,true);assert.doesNotMatch(panel.element.textContent,/PRIVATE/);}
});

test('요청 중 새 원고로 전환하면 늦은 결과를 무시한다',async()=>{
 const c=content(),gate=deferred(),{panel,done}=setup(c,{create:()=>gate.promise});await panel.open(c);await expand(panel);await type(panel,'body','문장');const creating=btn(panel,'create').fire('click');assert.equal(panel.isBusy(),true);await panel.open(null);gate.resolve(res(200,task(c)));await creating;assert.equal(panel.isBusy(),false);assert.equal(done.length,0);assert.equal(field(panel,'body'),undefined);
});

test('시간 초과는 busy를 풀고 자동 재제작을 막으며 입력을 보존한다',async()=>{
 const c=content(),{document}=harness();let posts=0,signal;
 const panel=createImageTaskPanel({document,requestTimeoutMs:5,fetcher:async(url,init)=>{if(init.method==='POST'){posts++;signal=init.signal;return new Promise(()=>{});}return res(200,url.includes('capabilities')?cap():{items:[]});}});
 await panel.open(c);await expand(panel);await type(panel,'body','보존할 문장');await btn(panel,'create').fire('click');
 assert.equal(posts,1);assert.equal(signal.aborted,true);assert.equal(panel.isBusy(),false);assert.equal(panel.isDirty(),true);assert.equal(field(panel,'body').value,'보존할 문장');assert.equal(btn(panel,'create').disabled,true);await force(btn(panel,'create'));assert.equal(posts,1);
});

test('기능 응답의 추가 권한·검토 플래그와 중복 작업은 생성을 차단한다',async()=>{
 const c=content();for(const options of [{caps:()=>res(200,cap({review_status:'passed'}))},{caps:()=>res(200,cap({external_fallback:true}))},{list:()=>res(200,{items:[task(c),task(c)]})}]){
 const {panel,calls}=setup(c,options);await panel.open(c);await expand(panel);await type(panel,'body','문장');await force(btn(panel,'create'));assert.equal(calls.filter(([,i])=>i.method==='POST').length,0);assert.equal(btn(panel,'create').disabled,true);}
});
