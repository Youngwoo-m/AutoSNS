import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createMediaLeasesPanel} from '../ax-console/app/web/media_leases_panel.js';
const row=(account='personal',over={})=>({lease_id:'a'.repeat(64),owner_account_id:account,destination_account_id:account,connection_id:account+'.instagram',content_id:'content',content_revision:1,asset_id:'asset',asset_sha256:'b'.repeat(64),asset_size:123,media_type:'image/jpeg',expires_at:'2030-01-01T00:00:00Z',status:'active',...over});
const response=(account='personal',items=[row(account)])=>({account_id:account,items});
const result=body=>({ok:true,status:200,json:async()=>body});
const setup=fetcher=>{const {document}=harness();return createMediaLeasesPanel({document,fetcher});};
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const action=(p,name)=>all(p.element).find(n=>n.getAttribute('data-media-leases-action')===name);
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('접힌 현황은 요청하지 않고 펼치기와 재조회만 GET한다',async()=>{
 const calls=[],p=setup(async(u,o)=>{calls.push([u,o]);return result(response());});
 await p.open('personal');assert.equal(p.element.open,false);assert.equal(calls.length,0);assert.equal(p.isDirty(),false);
 await expand(p);assert.equal(calls[0][0],'/api/v2/media-leases?account=personal');assert.equal(calls[0][1].method,'GET');assert.equal(calls[0][1].credentials,'same-origin');assert.equal(calls[0][1].body,undefined);
 await p.element.fire('toggle');assert.equal(calls.length,1);await action(p,'reload').fire('click');assert.equal(calls.length,2);
 assert.match(p.element.textContent,/이후 다운로드/);assert.match(p.element.textContent,/원격 복사본/);assert.doesNotMatch(p.element.textContent,/https?:\/\/|영수증/);
});
test('대상 계정에서 원본 계정을 구분하고 활성 행만 명시적으로 중지한다',async()=>{
 const calls=[],p=setup(async(u,o)=>{calls.push([u,o]);return result(response('dept',[row('dept',{owner_account_id:'personal',status:o.method==='POST'?'revoked':'active'})]));});
 await p.open('dept');await expand(p);assert.match(p.element.textContent,/원본 계정개인/);assert.match(p.element.textContent,/전달 대상 계정학과/);
 await action(p,'revoke').fire('click');assert.equal(calls.length,2);assert.equal(calls[1][0],`/api/v2/media-leases/${'a'.repeat(64)}/revoke`);
 assert.equal(calls[1][1].method,'POST');assert.equal(calls[1][1].credentials,'same-origin');assert.equal(calls[1][1].headers['Content-Type'],'application/json');assert.deepEqual(JSON.parse(calls[1][1].body),{account_id:'dept'});
 assert.equal(action(p,'revoke'),undefined);assert.match(p.element.textContent,/전달 중지/);assert.equal(p.isDirty(),false);
});
test('비활성 상태는 중지 버튼이 없고 all 또는 잘못된 계정은 조회하지 않는다',async()=>{
 let calls=0;const p=setup(async()=>{calls++;return result(response('personal',['expired','revoked','purged'].map((status,i)=>row('personal',{status,lease_id:String(i+1).repeat(64)}))));});
 await p.open('all');await expand(p);await p.open('invalid');await expand(p);assert.equal(calls,0);
 await p.open('personal');await expand(p);assert.equal(action(p,'revoke'),undefined);assert.match(p.element.textContent,/기간 만료/);assert.match(p.element.textContent,/로컬 자료 정리됨/);
});
test('개인정보 추가 필드와 계정 불일치 및 잘못된 DTO는 전체 거부한다',async()=>{
 const bodies=[{...response(),url:'https://secret'},response('personal',[row('personal',{token:'secret'})]),response('personal',[row('personal',{receipt:{}})]),response('dept'),response('personal',[row('dept')]),response('personal',[row('personal',{owner_account_id:'other'})]),response('personal',[row('personal',{lease_id:'A'.repeat(64)})]),response('personal',[row('personal',{asset_sha256:'bad'})]),response('personal',[row('personal',{content_revision:'1'})]),response('personal',[row('personal',{asset_size:0})]),response('personal',[row('personal',{status:'unknown'})]),response('personal',[row('personal',{expires_at:'tomorrow'})]),response('personal',[row(),row()])];
 for(const body of bodies){const p=setup(async()=>result(body));await p.open('personal');await expand(p);assert.match(p.element.textContent,/確認|확인할 수 없/);assert.equal(action(p,'revoke'),undefined);assert.doesNotMatch(p.element.textContent,/secret/);}
});
test('계정 교체 후 도착한 조회와 중지 응답은 현재 화면에 반영하지 않는다',async()=>{
 for(const revoke of [false,true]){
  const gate=deferred();let calls=0;
  const p=setup((u,o)=>{calls++;if(u.endsWith('account=dept'))return Promise.resolve(result(response('dept',[row('dept',{asset_id:'현재 학과'})])));if(revoke&&o.method==='GET')return Promise.resolve(result(response()));return gate.promise;});
  await p.open('personal');let old;
  if(revoke){await expand(p);old=action(p,'revoke').fire('click');}else old=expand(p);
  assert.equal(p.isBusy(),true);await p.open('dept');assert.equal(p.isBusy(),false);await expand(p);
  gate.resolve(result(response('personal',[row('personal',{asset_id:'이전 개인'})])));await old;
  assert.match(p.element.textContent,/현재 학과/);assert.doesNotMatch(p.element.textContent,/이전 개인/);assert.equal(p.isBusy(),false);
 }
});
test('중지 처리 중 중복 요청을 막고 오류 원문을 표시하지 않는다',async()=>{
 const gate=deferred();let calls=0;
 const p=setup((u,o)=>{calls++;return o.method==='GET'?Promise.resolve(result(response())):gate.promise;});await p.open('personal');await expand(p);
 const old=action(p,'revoke'),pending=old.fire('click');await old.fire('click');await action(p,'reload').fire('click');assert.equal(calls,2);
 gate.resolve({ok:false,status:403,json:async()=>({token:'secret'})});await pending;assert.equal(p.isBusy(),false);assert.doesNotMatch(p.element.textContent,/secret/);assert.match(p.element.textContent,/처리하지 못/);
 const failed=setup(async()=>{throw new Error('private-token');});await failed.open('personal');await expand(failed);assert.doesNotMatch(failed.element.textContent,/private-token/);
});
test('자산 이름은 HTML이 아니라 텍스트로 표시한다',async()=>{
 const p=setup(async()=>result(response('personal',[row('personal',{asset_id:'<img src=x onerror=bad()>'})])));await p.open('personal');await expand(p);
 assert.match(p.element.textContent,/<img src=x/);assert.equal(all(p.element).filter(n=>n.tagName==='img'||n.tagName==='script').length,0);
});
