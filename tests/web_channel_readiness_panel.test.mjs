import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createChannelReadinessPanel} from '../ax-console/app/web/channel_readiness_panel.js';
const channel=(account='personal',over={})=>({account_id:account,platform:'threads',connection_id:account+'.threads',label:'Threads',planning_enabled:true,target_status:'required',authentication_status:'not_connected',publisher_status:'text_only_implemented',verification_status:'hash_implemented',metrics_status:'not_implemented',live_enabled:false,next_actions:['계정을 연결하세요.'],...over});
const response=(account='personal',channels=[channel(account)])=>({account_id:account,channels});
const result=body=>({ok:true,status:200,json:async()=>body});
const setup=fetcher=>{const {document}=harness();return createChannelReadinessPanel({document,fetcher});};
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const reload=p=>all(p.element).find(n=>n.getAttribute('data-channel-readiness-action')==='reload');
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};

test('계정 채널 상태는 펼칠 때만 GET하고 수동 재조회만 한다',async()=>{
 const calls=[];const p=setup(async(u,o)=>{calls.push([u,o]);return result(response());});await p.open('personal',{writable:true});assert.equal(calls.length,0);await expand(p);assert.equal(calls[0][0],'/api/v2/channels/readiness?account=personal');assert.equal(calls[0][1].method,'GET');assert.equal(calls[0][1].body,undefined);assert.equal(p.isDirty(),false);await p.element.fire('toggle');assert.equal(calls.length,1);await reload(p).fire('click');assert.equal(calls.length,2);assert.ok(calls.every(([,o])=>o.method==='GET'));
});
test('개발 상태와 실제 발행 꺼짐을 분리해 보여 준다',async()=>{
 const p=setup(async()=>result(response('dept',[channel('dept',{publisher_status:'browser_implemented',verification_status:'receipt_implemented',metrics_status:'implemented',target_status:'verified',authentication_status:'connected'})])));await p.open('dept');await expand(p);const text=p.element.textContent;assert.match(text,/학과/);assert.match(text,/대상 ID 확인 기록/);assert.match(text,/현재 로그인 미검증/);assert.match(text,/기존 자동 작업의 동작 여부와 별개/);assert.match(text,/브라우저 경로 개발/);assert.match(text,/업로드 영수증 검증 개발/);assert.match(text,/통계 수집기 개발/);assert.match(text,/실제 발행 꺼짐/);assert.doesNotMatch(text,/사용 가능|발행 켜짐/);
});
test('all은 두 계정 상태를 표시하고 개인 화면은 학과 응답을 거부한다',async()=>{
 const allPanel=setup(async()=>result(response('all',[channel('personal'),channel('dept')])));await allPanel.open('all');await expand(allPanel);assert.match(allPanel.element.textContent,/개인/);assert.match(allPanel.element.textContent,/학과/);
 const p=setup(async()=>result(response('personal',[channel('dept')])));await p.open('personal');await expand(p);assert.match(p.element.textContent,/확인할 수 없/);assert.doesNotMatch(p.element.textContent,/본문·자산 검증 개발/);
});
test('추가 필드·실제 발행 true·잘못된 소유자·계정 응답은 통째로 거부한다',async()=>{
 const bodies=[{...response(),unexpected:true},response('personal',[channel('personal',{unexpected:true})]),response('personal',[channel('personal',{live_enabled:true})]),response('personal',[channel('other')]),response('dept')];
 for(const body of bodies){const p=setup(async()=>result(body));await p.open('personal');await expand(p);assert.match(p.element.textContent,/확인할 수 없/);assert.doesNotMatch(p.element.textContent,/계정을 연결하세요/);}
});
test('오류는 원문을 노출하지 않고 읽기 전용에서도 조회만 한다',async()=>{
 const calls=[];const p=setup(async(u,o)=>{calls.push(o.method);throw new Error('secret-token');});await p.open('dept',{writable:false});await expand(p);assert.equal(p.isBusy(),false);assert.match(p.element.textContent,/연결하지 못/);assert.doesNotMatch(p.element.textContent,/secret-token/);assert.deepEqual(calls,['GET']);p.refreshControls({writable:true});assert.equal(p.isDirty(),false);
});
test('늦은 이전 계정 응답과 잘못된 계정 열기는 반영하지 않는다',async()=>{
 const gate=deferred(),calls=[];const p=setup(u=>{calls.push(u);return u.endsWith('personal')?gate.promise:Promise.resolve(result(response('dept')));});await p.open('personal');const old=expand(p);assert.equal(p.isBusy(),true);await p.open('dept');await expand(p);gate.resolve(result(response('personal',[channel('personal',{label:'이전 개인 표식'})])));await old;assert.doesNotMatch(p.element.textContent,/이전 개인 표식/);assert.match(p.element.textContent,/학과/);await p.open('invalid');await expand(p);assert.equal(calls.length,2);
});
test('채널명과 후속 안내는 HTML이 아닌 텍스트로 표시한다',async()=>{
 const p=setup(async()=>result(response('personal',[channel('personal',{label:'<img src=x onerror=bad()>',next_actions:['<script>bad()</script>'],publisher_status:'implemented',verification_status:'public_probe_required',metrics_status:'stored_only'})])));await p.open('personal');await expand(p);assert.match(p.element.textContent,/<img src=x/);assert.match(p.element.textContent,/<script>/);assert.match(p.element.textContent,/개발됨/);assert.match(p.element.textContent,/공개 확인 연결 필요/);assert.match(p.element.textContent,/저장 자료 조회/);assert.equal(all(p.element).filter(n=>n.tagName==='script'||n.tagName==='img').length,0);
});
