import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createTikTokPreparationPanel} from '../ax-console/app/web/tiktok_preparation_panel.js';
const H='a'.repeat(64),B='b'.repeat(64);
const plan=(over={})=>({id:'plan-1',platform:'tiktok',owner_account_id:'personal',destination_account_id:'dept',connection_id:'dept.tiktok',content_id:'content-1',revision:2,manifest_hash:H,options:{tiktok:{asset_ids:['asset-1']}},...over});
const row=(over={})=>({plan_id:'plan-1',owner_account_id:'personal',destination_account_id:'dept',connection_id:'dept.tiktok',content_id:'content-1',content_revision:2,manifest_hash:H,caption:' 원문 <script> 그대로\n',caption_sha256:H,asset:{id:'asset-1',sha256:B,size:200,media_type:'video/mp4'},asset_url:'/api/v2/contents/content-1/revisions/2/assets/asset-1',preparation_hash:B,status:'local_preparation_only',publication_enabled:false,technical_check_available:true,technical_check:null,...over});
const technical={width:1080,height:1920,fps:30,duration_ms:15000,video_codec:'h264',audio_codec:'aac',checked_at:'2026-11-04T01:00:00Z'};
const setup=(api,options={})=>createTikTokPreparationPanel({document:harness().document,api,...options});
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const action=(p,name)=>all(p.element).find(n=>n.getAttribute('data-tiktok-preparation-action')===name);

test('저장 계획을 펼칠 때만 조회하고 정확한 캡션과 인증 상대 다운로드 링크를 표시한다',async()=>{
 const calls=[],p=setup({getTikTokPreparation:async id=>(calls.push(id),row())});await p.open(plan(),{writable:true});assert.equal(calls.length,0);await expand(p);assert.deepEqual(calls,['plan-1']);assert.match(p.element.textContent,/ 원문 <script> 그대로\n/);assert.match(p.element.textContent,/실제 업로드·게시 아님/);const link=all(p.element).find(n=>n.tagName==='a');assert.equal(link.getAttribute('href'),row().asset_url);assert.equal(all(p.element).some(n=>['img','iframe','video','script'].includes(n.tagName)),false);assert.equal(p.isDirty(),false);
});
test('기술 검사는 명시 클릭과 현재 해시만 사용하고 이번 결과로 표시한다',async()=>{
 const calls=[],p=setup({getTikTokPreparation:async()=>row(),checkTikTokPreparation:async(id,body)=>(calls.push([id,body]),row({technical_check:technical}))});await p.open(plan(),{writable:true});await expand(p);assert.equal(calls.length,0);await action(p,'check').fire('click');assert.deepEqual(calls,[['plan-1',{preparation_hash:B}]]);assert.match(p.element.textContent,/이번 검사 결과/);assert.match(p.element.textContent,/영구 승인/);await action(p,'reload').fire('click');assert.doesNotMatch(p.element.textContent,/이번 검사 결과/);
});
test('미등록 검사기나 부모 편집 중에는 검사를 허용하지 않는다',async()=>{
 let writes=0;const p=setup({getTikTokPreparation:async()=>row({technical_check_available:false}),checkTikTokPreparation:async()=>{writes++;}});await p.open(plan(),{writable:true});await expand(p);assert.equal(action(p,'check').disabled,true);await action(p,'check').fire('click');assert.equal(writes,0);
 const q=setup({getTikTokPreparation:async()=>row(),checkTikTokPreparation:async()=>{writes++;}});await q.open(plan(),{writable:false});await expand(q);assert.equal(action(q,'check').disabled,true);await action(q,'check').fire('click');assert.equal(writes,0);
});
test('다른 대상·원본·자산·절대 URL 및 잘못된 응답은 링크 없이 차단한다',async()=>{
 for(const changed of [{destination_account_id:'personal'},{content_revision:3},{asset_url:'https://evil.example.com/a'},{publication_enabled:true},{extra:'secret'},{asset:{...row().asset,id:'other'}},{technical_check:technical}]){const p=setup({getTikTokPreparation:async()=>row(changed)});await p.open(plan());await expand(p);assert.match(p.element.textContent,/확인하지 못했습니다/);assert.equal(all(p.element).some(n=>n.tagName==='a'),false);}
});
test('늦은 응답은 전환한 계획에 섞이지 않고 처리 중 상태를 부모에게 알린다',async()=>{
 let finish;const events=[],p=setup({getTikTokPreparation:()=>new Promise(r=>finish=r)},{onChange:()=>events.push('changed')});await p.open(plan(),{writable:true});const pending=expand(p);await Promise.resolve();assert.equal(p.isBusy(),true);await p.open(plan({id:'other-plan'}));finish(row());await pending;assert.equal(p.isBusy(),false);assert.doesNotMatch(p.element.textContent,/원문 <script>/);assert.ok(events.length>=2);
});
test('검사 응답 해시 변경·오류·시간 초과는 비밀 원문을 표시하지 않는다',async()=>{
 const p=setup({getTikTokPreparation:async()=>row(),checkTikTokPreparation:async()=>row({technical_check:technical,preparation_hash:H})});await p.open(plan(),{writable:true});await expand(p);await action(p,'check').fire('click');assert.match(p.element.textContent,/확인하지 못했습니다/);
 const q=setup({getTikTokPreparation:async()=>{throw new Error('PRIVATE-SECRET');}});await q.open(plan());await expand(q);assert.doesNotMatch(q.element.textContent,/PRIVATE-SECRET/);
 const t=setup({getTikTokPreparation:()=>new Promise(()=>{})},{requestTimeoutMs:5});await t.open(plan());await expand(t);assert.equal(t.isBusy(),false);assert.match(t.element.textContent,/다시 조회/);
});

test('선택 자산 없는 이전 TikTok 계획은 자동 조회나 원고 수정 없이 새 계획 안내를 표시한다',async()=>{
 let calls=0;const p=setup({getTikTokPreparation:async()=>{calls++;return row();}}),old=plan({options:{}}),before=structuredClone(old);await p.open(old);await expand(p);assert.equal(calls,0);assert.match(p.element.textContent,/이 계획에는 준비할 영상이 선택되지 않았습니다. 영상을 선택한 새 계획을 저장하세요./);assert.deepEqual(old,before);assert.equal(action(p,'reload').disabled,true);await p.open(null);assert.doesNotMatch(p.element.textContent,/이 계획에는/);await p.open(plan({platform:'youtube',options:{}}));assert.doesNotMatch(p.element.textContent,/이 계획에는/);
});

test('실제 준비 API facade는 인증된 상대 경로 GET과 해시만 담은 POST를 사용한다',async()=>{
 const {createContentApi}=await import('../ax-console/app/web/api.js');const calls=[];const api=createContentApi({fetcher:async(url,options)=>(calls.push([url,options]),{ok:true,json:async()=>row()})});
 await api.getTikTokPreparation('plan/id');await api.checkTikTokPreparation('plan/id',{preparation_hash:B});
 assert.equal(calls[0][0],'/api/v2/deliveries/plan%2Fid/tiktok-preparation');assert.equal(calls[0][1].method,'GET');assert.equal(calls[0][1].body,undefined);
 assert.equal(calls[1][0],'/api/v2/deliveries/plan%2Fid/tiktok-preparation/check');assert.equal(calls[1][1].method,'POST');assert.deepEqual(JSON.parse(calls[1][1].body),{preparation_hash:B});assert.equal(calls[1][1].headers['Content-Type'],'application/json');for(const [,options]of calls){assert.equal(options.credentials,'same-origin');assert.equal(options.cache,'no-store');}
});
