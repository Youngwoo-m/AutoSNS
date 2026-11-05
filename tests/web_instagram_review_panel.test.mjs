import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createInstagramReviewPanel} from '../ax-console/app/web/instagram_review_panel.js';
const SHA='a'.repeat(64),HASH='b'.repeat(64);
const plan=(over={})=>({id:'plan-1',content_id:'content-1',revision:2,manifest_hash:SHA,owner_account_id:'personal',destination_account_id:'dept',connection_id:'dept.instagram',target_id:'123456',target_status:'verified',platform:'instagram',options:{instagram:{format:'image',asset_ids:['asset-1']}},...over});
const checks=(value=false)=>({rights_confirmed:value,visual_checked:value,caption_checked:value,composition_checked:value,audio_checked:value});
const row=(over={})=>({plan_id:'plan-1',content_id:'content-1',content_revision:2,manifest_hash:SHA,owner_account_id:'personal',destination_account_id:'dept',connection_id:'dept.instagram',target_id:'123456',media_format:'image',caption:'검토할 캡션 <script>',assets:[{id:'asset-1',sha256:HASH,size:20,media_type:'image/jpeg'}],subject_hash:HASH,review_revision:0,decision:null,checks:checks(),notes:'',review_method:'manual',status:'not_reviewed',audio_required:false,...over});
const action=(p,name)=>all(p.element).find(n=>n.getAttribute('data-instagram-review-action')===name);
const field=(p,name)=>all(p.element).find(n=>n.getAttribute('data-instagram-review-field')===name);
const setup=(api,opts={})=>{const {document}=harness();return {panel:createInstagramReviewPanel({document,api,...opts}),document};};
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
const fill=async p=>{for(const key of ['rights_confirmed','visual_checked','caption_checked','composition_checked']){const n=field(p,key);n.checked=true;await n.fire('change');}};
test('저장된 Instagram 계획을 펼칠 때만 검토 구성을 조회하며 텍스트와 자산 순서를 표시한다',async()=>{
 const calls=[];const {panel}=setup({getInstagramReview:async id=>(calls.push(['get',id]),row())});await panel.open(plan(),{writable:true});assert.equal(calls.length,0);await expand(panel);assert.deepEqual(calls,[['get','plan-1']]);assert.match(panel.element.textContent,/검토할 캡션 <script>/);assert.match(panel.element.textContent,/1.*image\/jpeg/);assert.match(panel.element.textContent,/최종 게시 승인/);assert.match(panel.element.textContent,/파일 공개/);assert.equal(all(panel.element).some(n=>['iframe','img','script','video'].includes(n.tagName)),false);assert.equal(field(panel,'audio_checked'),undefined);assert.equal(panel.isDirty(),false);
});
test('사용자가 항목을 확인한 뒤에만 정확한 subject와 CAS로 수동 기록을 저장한다',async()=>{
 const posts=[];const {panel}=setup({getInstagramReview:async()=>row(),recordInstagramReview:async(id,body)=>(posts.push([id,body]),row({review_revision:1,decision:'approved',checks:body.checks,notes:body.notes,status:'approved'}))});await panel.open(plan(),{writable:true});await expand(panel);await action(panel,'approve').fire('click');assert.equal(posts.length,0);await fill(panel);field(panel,'notes').value='수동으로 확인';await field(panel,'notes').fire('input');assert.equal(panel.isDirty(),true);await action(panel,'approve').fire('click');assert.equal(posts.length,1);assert.deepEqual(posts[0][1],{expected_review_revision:0,subject_hash:HASH,decision:'approved',checks:{...checks(true),audio_checked:false},notes:'수동으로 확인'});assert.equal(panel.isDirty(),false);
});
test('동영상이 있는 구성은 음성 확인도 명시적으로 요구하고 철회는 별도 기록한다',async()=>{
 const p=plan({options:{instagram:{format:'reels',asset_ids:['asset-1']}}}),base=row({media_format:'reels',assets:[{id:'asset-1',sha256:HASH,size:20,media_type:'video/mp4'}],audio_required:true});const posts=[];
 const {panel}=setup({getInstagramReview:async()=>base,recordInstagramReview:async(id,body)=>(posts.push(body),{...base,review_revision:1,decision:body.decision,checks:body.checks,notes:body.notes,status:body.decision})});await panel.open(p,{writable:true});await expand(panel);await fill(panel);await action(panel,'approve').fire('click');assert.equal(posts.length,0);field(panel,'audio_checked').checked=true;await field(panel,'audio_checked').fire('change');await action(panel,'approve').fire('click');assert.equal(posts[0].decision,'approved');await action(panel,'revoke').fire('click');assert.equal(posts[1].decision,'revoked');
});
test('다른 계정·버전·자산 순서·추가 필드와 대상 미확인은 검토할 수 없다',async()=>{
 for(const bad of [row({destination_account_id:'personal'}),row({content_revision:3}),row({extra:true}),row({assets:[{id:'wrong',sha256:HASH,size:20,media_type:'image/jpeg'}]}),row({audio_required:true})]){const {panel}=setup({getInstagramReview:async()=>bad});await panel.open(plan(),{writable:true});await expand(panel);assert.equal(field(panel,'rights_confirmed'),undefined);assert.match(panel.element.textContent,/확인할 수 없/);}
 let gets=0;const {panel}=setup({getInstagramReview:async()=>{gets++;return row();}});await panel.open(plan({target_id:null,target_status:'unverified'}),{writable:true});await expand(panel);assert.equal(gets,0);assert.match(panel.element.textContent,/게시 대상/);
});
test('409와 시간 초과는 초안을 보존하고 저장 재요청을 막으며 명시 조회와 버리기로 복구한다',async()=>{
 let posts=0;const {panel}=setup({getInstagramReview:async()=>row(),recordInstagramReview:async()=>{posts++;throw {status:409};}});await panel.open(plan(),{writable:true});await expand(panel);await fill(panel);field(panel,'notes').value='보존';await field(panel,'notes').fire('input');await action(panel,'approve').fire('click');assert.equal(field(panel,'notes').value,'보존');assert.equal(panel.isDirty(),true);await action(panel,'approve').fire('click');assert.equal(posts,1);assert.match(panel.element.textContent,/다시 조회/);
 panel.discardChanges();await action(panel,'reload').fire('click');assert.equal(panel.isDirty(),false);
 const timed=setup({getInstagramReview:async()=>row(),recordInstagramReview:async()=>new Promise(()=>{})},{requestTimeoutMs:5}).panel;await timed.open(plan(),{writable:true});await expand(timed);await fill(timed);await action(timed,'approve').fire('click');assert.equal(timed.isBusy(),false);assert.equal(timed.isDirty(),true);assert.match(timed.element.textContent,/다시 조회/);
});
test('같은 계획 refresh는 입력 포커스를 보존하고 늦은 이전 계획 응답은 무시한다',async()=>{
 const gate=deferred();const {panel,document}=setup({getInstagramReview:async id=>id==='plan-1'?gate.promise:row({plan_id:'plan-2'})});await panel.open(plan(),{writable:true});const old=expand(panel);await panel.open(plan({id:'plan-2'}),{writable:true});await expand(panel);const notes=field(panel,'notes');notes.focus();notes.value='새 계획';await notes.fire('input');panel.refreshControls({writable:true});await panel.open(plan({id:'plan-2'}),{writable:true});assert.equal(document.activeElement,notes);gate.resolve(row());await old;assert.equal(field(panel,'notes').value,'새 계획');
});
test('읽기 전용은 GET만 허용하고 API 오류 원문을 표시하지 않는다',async()=>{
 let posts=0;const {panel}=setup({getInstagramReview:async()=>row(),recordInstagramReview:async()=>{posts++;}});await panel.open(plan(),{writable:false});await expand(panel);assert.equal(field(panel,'rights_confirmed').disabled,true);await action(panel,'approve').fire('click');assert.equal(posts,0);
 const broken=setup({getInstagramReview:async()=>{throw new Error('PRIVATE-TOKEN');}}).panel;await broken.open(plan(),{writable:true});await expand(broken);assert.doesNotMatch(broken.element.textContent,/PRIVATE/);assert.match(broken.element.textContent,/조회하지 못/);
});

test('저장 응답이 사용자가 보내지 않은 확인 항목이나 메모로 바뀌면 초안을 유지한다',async()=>{
 for(const change of ['checks','notes']){
  const {panel}=setup({getInstagramReview:async()=>row(),recordInstagramReview:async(id,body)=>row({review_revision:1,decision:'approved',status:'approved',checks:change==='checks'?{...body.checks,audio_checked:true}:body.checks,notes:change==='notes'?'다른 메모':body.notes})});await panel.open(plan(),{writable:true});await expand(panel);await fill(panel);field(panel,'notes').value='내 메모';await field(panel,'notes').fire('input');await action(panel,'approve').fire('click');assert.equal(panel.isDirty(),true);assert.equal(field(panel,'notes').value,'내 메모');assert.match(panel.element.textContent,/확인할 수 없/);
 }
});

test('항목 변경 없는 철회 응답이 불확실해도 부모 보호를 유지하고 명시 버리기만 해제한다',async()=>{
 const approved=row({review_revision:1,decision:'approved',status:'approved',checks:{...checks(true),audio_checked:false}});const {panel}=setup({getInstagramReview:async()=>approved,recordInstagramReview:async()=>{throw {status:409};}});await panel.open(plan(),{writable:true});await expand(panel);assert.equal(panel.isDirty(),false);await action(panel,'revoke').fire('click');assert.equal(panel.isDirty(),true);panel.discardChanges();assert.equal(panel.isDirty(),false);assert.equal(action(panel,'approve').disabled,true);await action(panel,'reload').fire('click');assert.equal(action(panel,'approve').disabled,false);
});
