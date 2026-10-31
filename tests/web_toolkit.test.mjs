import test from 'node:test';
import assert from 'node:assert/strict';
import {loadWebModule} from './helpers/staged_web.mjs';
const {createToolkitApi}=await loadWebModule('toolkit_api.js');
const {createToolkitController}=await loadWebModule('toolkit_controller.js');
const {createToolkitPanel}=await loadWebModule('toolkit_panel.js');
class Node {constructor(tag){this.tagName=tag;this.children=[];this.listeners={};this.value='';}set textContent(v){this.text=String(v);this.children=[];}get textContent(){return (this.text||'')+this.children.map(n=>n.textContent).join('');}append(...n){this.children.push(...n);}replaceChildren(...n){this.children=n;this.text='';}addEventListener(k,f){this.listeners[k]=f;}setAttribute(k,v){this[k]=v;}async fire(k){if(!this.disabled)return this.listeners[k]?.({preventDefault(){}});}}
const document={createElement:t=>new Node(t)};
const ctx={account:'personal',contentId:'c',revision:1,connectionId:'x',inputHash:'h',editorDirty:false};
const nodes=n=>[n,...n.children.flatMap(nodes)];
test('test_render_and_scope_change_never_submit',()=>{let calls=0;const controller=createToolkitController({api:new Proxy({},{get:()=>()=>calls++})});const panel=createToolkitPanel({controller,document});panel.render({section:'accounts',context:ctx,writable:true});panel.render({section:'accounts',context:{...ctx,account:'dept'},writable:true});assert.equal(calls,0);});
test('test_late_response_cannot_overwrite_other_account_or_revision',async()=>{let finish;const c=createToolkitController({api:{researchPreview:()=>new Promise(r=>finish=r)}});c.setContext(ctx);const p=c.preview('research',{});c.setContext({...ctx,revision:2});finish({items:['old']});await p;assert.equal(c.getState().reports.research,undefined);});
test('test_preview_then_dirty_edit_blocks_candidate_apply',async()=>{const c=createToolkitController({api:{packagingPreview:async()=>({candidates:[{id:'one',title:'Title',variants:[{text:'draft'}]}]})}});c.setContext(ctx);await c.preview('packaging',{keywords:[]});assert.deepEqual(c.stageCandidate('one',ctx),{title:'Title'});c.setContext({...ctx,editorDirty:true});assert.throws(()=>c.stageCandidate('one',ctx),/변경/);});
for(const status of [401,409,503])test(`test_csv_${status}_preserves_text_and_request_key`,async()=>{const sent=[];const c=createToolkitController({api:{csvPreview:async()=>({preview_digest:'digest'}),csvImport:async b=>{sent.push(b);throw Object.assign(new Error('secret'),{status});}}});c.setContext(ctx);c.updateInput('csv_text','original');await c.preview('csv',{});await c.preview('csvImport',{});await c.preview('csvImport',{});assert.equal(c.getState().inputs.csv_text,'original');assert.equal(c.isDirty(),true);assert.equal(sent[0].request_key,sent[1].request_key);assert.equal(sent[0].preview_digest,'digest');});
test('test_untrusted_titles_are_text_and_no_ctr_score',async()=>{const c=createToolkitController({api:{packagingPreview:async()=>({candidates:[{id:'a',title:'<img onerror=x>',ctr:99}]})}});c.setContext(ctx);await c.preview('packaging',{});const p=createToolkitPanel({controller:c,document});assert.match(p.render({context:ctx,writable:true}).textContent,/<img onerror=x>/);assert.doesNotMatch(p.element.textContent,/99/);assert.equal(nodes(p.element).some(n=>n.innerHTML),false);});
test('exact API paths and field whitelist',async()=>{const calls=[];const api=createToolkitApi({fetcher:async(u,o)=>{calls.push([u,o]);return {ok:true,json:async()=>({})};}});await api.packagingPreview({content_id:'c',revision:1,connection_id:'x',keywords:[]});assert.equal(calls[0][0],'/api/v2/tools/packaging-preview');assert.equal(calls[0][1].credentials,'same-origin');await assert.rejects(api.packagingPreview({command:'x'}));});
test('duplicate preview and changed CSV invalidate digest',async()=>{let finish,calls=0;const c=createToolkitController({api:{csvPreview:()=>{calls++;return new Promise(r=>finish=r);}}});c.setContext(ctx);c.updateInput('csv_text','a');const p=c.preview('csv',{});await c.preview('csv',{});assert.equal(calls,1);c.updateInput('csv_text','b');finish({preview_digest:'old'});await p;assert.equal(c.getState().reports.csv,undefined);});
test('input focus node survives typing and explicit click has busy guard',async()=>{let done,calls=0;const c=createToolkitController({api:{packagingPreview:()=>{calls++;return new Promise(r=>done=r);}}});const p=createToolkitPanel({controller:c,document});const root=p.render({context:ctx,writable:true});const field=nodes(root).find(n=>n.name==='toolkit_keywords');field.value='test';await field.fire('input');assert.equal(nodes(root).find(n=>n.name==='toolkit_keywords'),field);const button=nodes(root).find(n=>n.textContent==='제목·태그 후보 미리보기');const first=button.fire('click');await button.fire('click');assert.equal(calls,1);assert.equal(p.isBusy(),true);done({candidates:[]});await first;assert.equal(p.isBusy(),false);assert.equal(p.isDirty(),true);});
test('changed keywords invalidates prior candidate and per account drafts persist',async()=>{const c=createToolkitController({api:{packagingPreview:async()=>({candidates:[{id:'a',title:'A'}]})}});c.setContext(ctx);await c.preview('packaging',{});c.updateInput('keywords','changed');assert.throws(()=>c.stageCandidate('a',ctx));c.updateInput('csv_text','personal original');c.setContext({...ctx,account:'dept'});c.updateInput('csv_text','dept original');c.setContext(ctx);assert.equal(c.getState().inputs.csv_text,'personal original');});
test('actual hashtags require explicit matching variant and preserve body source',async()=>{
 const context={...ctx,variants:[{destination_account_id:'personal',platform:'youtube',text:'기존 변환문'},{destination_account_id:'dept',platform:'youtube',text:'다른 변환문'}]};
 const c=createToolkitController({api:{packagingPreview:async()=>({destination_account_id:'personal',platform:'youtube',candidates:[{id:'a',title:'A',hashtags:['#현장']}]})}});
 c.setContext(context);await c.preview('packaging',{});
 assert.throws(()=>c.stageCandidate('a',{contentId:'c',revision:1}));
 assert.throws(()=>c.stageCandidate('a',{...context,variantIndex:1}));
 assert.deepEqual(c.stageCandidate('a',{...context,variantIndex:0}),{title:'A',variant:{index:0,destination_account_id:'personal',platform:'youtube',text:'기존 변환문\n\n#현장'}});
});
test('all exact endpoints, GET no automatic calls, and unavailable statuses stay typed',async()=>{const calls=[];const api=createToolkitApi({fetcher:async(u,o)=>{calls.push([u,o]);return {ok:true,json:async()=>({status:'unavailable'})};}});assert.equal(calls.length,0);const requests=[['researchPreview',{account_id:'dept'},'research-preview'],['thumbnailInspect',{content_id:'c',revision:1,asset_id:'a'},'thumbnail-inspect'],['thumbnailRender',{content_id:'c',revision:1,asset_id:null,preset_id:'p',title:'t'},'thumbnail-render'],['csvPreview',{account_id:'dept',csv_text:'a'},'metrics-csv-preview'],['csvImport',{account_id:'dept',csv_text:'a',preview_digest:'d',request_key:'k'},'metrics-csv-import'],['scheduleInspect',{delivery_id:'d'},'schedule-inspect']];for(const [name,body,path] of requests){assert.equal((await api[name](body)).status,'unavailable');assert.equal(calls.at(-1)[0],`/api/v2/tools/${path}`);assert.deepEqual(JSON.parse(calls.at(-1)[1].body),body);}await api.capabilities('all');assert.equal(calls.at(-1)[0],'/api/v2/tools/capabilities?account=all');assert.equal(calls.at(-1)[1].method,'GET');});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
for(const order of ['old-first','latest-first'])test(`CSV latest selection wins both file completion orders: ${order}`,async()=>{
 const c=createToolkitController({api:{}});const p=createToolkitPanel({controller:c,document});p.render({context:ctx});
 const file=nodes(p.element).find(n=>n.name==='toolkit_csv_file');const old=deferred(),latest=deferred();
 file.files=[{text:()=>old.promise}];const first=file.fire('change');file.files=[{text:()=>latest.promise}];const second=file.fire('change');
 if(order==='old-first'){old.resolve('OLD FILE');await first;latest.resolve('LATEST FILE');await second;}else{latest.resolve('LATEST FILE');await second;old.resolve('OLD FILE');await first;}
 assert.equal(c.getState().inputs.csv_text,'LATEST FILE');
});
for(const change of ['account','revision','text'])test(`pending file read cannot overwrite ${change} change`,async()=>{
 const c=createToolkitController({api:{}});const p=createToolkitPanel({controller:c,document});p.render({context:ctx});c.updateInput('csv_text','preserved');const file=nodes(p.element).find(n=>n.name==='toolkit_csv_file'),read=deferred();file.files=[{text:()=>read.promise}];const pending=file.fire('change');
 if(change==='text')c.updateInput('csv_text','typed');else p.render({context:{...ctx,...(change==='account'?{account:'dept'}:{revision:2})}});
 read.resolve('STALE FILE');await pending;assert.equal(c.getState().inputs.csv_text,change==='text'?'typed':change==='account'?'':'preserved');
});
test('schedule inspection displays safe root fields and unknown reason without action',async()=>{
 let calls=0;const c=createToolkitController({api:{scheduleInspect:async()=>{calls++;return {delivery_id:'delivery-x',state:'unknown',target_id:'target-x',remote_id:null,scheduled_at:'2026-11-01T00:00:00Z',execution_enabled:false,reason_codes:['사람 확인 필요','<img onerror=x>'],credential_ref:'SECRET'};}}});c.setContext(ctx);await c.preview('schedule',{delivery_id:'delivery-x'});const p=createToolkitPanel({controller:c,document});p.render({context:ctx});
 for(const value of ['delivery-x','미확인','target-x','2026-11-01T00:00:00Z','비활성','사람 확인 필요','<img onerror=x>','미확인'])assert.ok(p.element.textContent.includes(value),value);
 assert.doesNotMatch(p.element.textContent,/SECRET|게시 성공/);assert.equal(calls,1);
});
test('CSV read rejection preserves draft and displays sanitized error',async()=>{const c=createToolkitController({api:{}});const p=createToolkitPanel({controller:c,document});p.render({context:ctx});c.updateInput('csv_text','original');const file=nodes(p.element).find(n=>n.name==='toolkit_csv_file');file.files=[{text:async()=>{throw new Error('SECRET');}}];await file.fire('change');assert.equal(c.getState().inputs.csv_text,'original');assert.match(p.element.textContent,/CSV 파일을 읽지 못했습니다.*보존/);assert.doesNotMatch(p.element.textContent,/SECRET/);});

// Editor uses refreshControls on input notifications, not a complete render.
const {harness,all}=await import('./helpers/execution_dom.mjs');
async function selectionFixture(){
 const {document}=harness();let panel;const staged=[],inspections=[];
 const context={...ctx,assets:[{id:'img',filename:'image.png',media_type:'image/png'}],variants:[{destination_account_id:'personal',platform:'youtube',text:'첫 변환문'},{destination_account_id:'personal',platform:'youtube',text:'두번째 변환문'}]};
 const c=createToolkitController({api:{packagingPreview:async()=>({destination_account_id:'personal',platform:'youtube',candidates:[{id:'a',title:'후보',hashtags:['#현장']}]}),thumbnailInspect:async body=>{inspections.push(body);return {status:'ok',width:100,height:100,findings:[]};}},onChange:()=>panel?.refreshControls({context,writable:true})});
 panel=createToolkitPanel({controller:c,document});panel.render({section:'editor',context,writable:true});panel.element.dispatchEvent=event=>staged.push(event.detail);
 await c.preview('packaging');panel.render({section:'editor',context,writable:true});
 return {c,panel,context,staged,inspections,field:name=>all(panel.element).find(n=>n.name===`toolkit_${name}`),button:text=>all(panel.element).find(n=>n.textContent===text)};
}
test('cleared variant stays blocked after unrelated input and stale click emits no patch',async()=>{
 const f=await selectionFixture();let choice=f.field('variant_index');choice.value='0';await choice.fire('change');
 const oldButton=f.button('후보 1 제목·태그를 선택 변환문에 반영');
 choice=f.field('variant_index');choice.value='';await choice.fire('change');
 const title=f.field('title');title.value='썸네일';await title.fire('input');
 const current=f.button('후보 1 제목·태그를 선택 변환문에 반영');assert.equal(current.disabled,true);
 await current.fire('click');await oldButton.fire('click');assert.deepEqual(f.staged,[]);
});
test('explicit variant zero stages only its current text',async()=>{
 const f=await selectionFixture();const choice=f.field('variant_index');choice.value='0';await choice.fire('change');
 await f.button('후보 1 제목·태그를 선택 변환문에 반영').fire('click');
 assert.deepEqual(f.staged,[{title:'후보',variant:{index:0,destination_account_id:'personal',platform:'youtube',text:'첫 변환문\n\n#현장'}}]);
 assert.equal(f.c.getState().context.variants[1].text,'두번째 변환문');
});
test('asset selection enables inspection immediately and clearing disables it',async()=>{
 const f=await selectionFixture();assert.equal(f.button('이미지 기술 검사').disabled,true);
 const image=f.field('asset_id');image.value='img';await image.fire('change');assert.equal(f.button('이미지 기술 검사').disabled,false);
 await f.button('이미지 기술 검사').fire('click');assert.deepEqual(f.inspections,[{content_id:'c',revision:1,asset_id:'img'}]);
 const cleared=f.field('asset_id');cleared.value='';await cleared.fire('change');assert.equal(f.button('이미지 기술 검사').disabled,true);
 await f.button('이미지 기술 검사').fire('click');assert.equal(f.inspections.length,1);
});
