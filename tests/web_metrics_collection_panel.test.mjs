import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,all} from './helpers/execution_dom.mjs';
import {createMetricsCollectionPanel} from '../ax-console/app/web/metrics_collection_panel.js';
const target=(over={})=>({delivery_id:'delivery-1',content_id:'content-1',content_revision:2,owner_account_id:'personal',destination_account_id:'dept',platform:'youtube',connection_id:'connection-1',target_id:'channel-1',remote_id:'video-1',verified_at:'2026-11-02T03:00:00Z',title:'공개 영상',...over});
const list=(account='all',over={})=>({account_id:account,execution_enabled:true,items:[target(account==='personal'?{destination_account_id:'personal'}:{})],...over});
const observation=(over={})=>({id:'metric-1',source_kind:'verified_delivery',owner_account_id:'personal',destination_account_id:'dept',platform:'youtube',connection_id:'connection-1',target_id:'channel-1',remote_id:'video-1',delivery_id:'delivery-1',content_id:'content-1',status:'ok',observed_at:'2026-11-02T04:00:00Z',values:{views:25},...over});
const response=(body,status=200)=>({ok:status<400,status,json:async()=>body});
const setup=(fetcher,opts={})=>{const {document}=harness();const collected=[];const panel=createMetricsCollectionPanel({document,fetcher,onCollected:o=>collected.push(o),...opts});return {panel,collected,document};};
const action=(p,name)=>all(p.element).find(n=>n.getAttribute('data-metrics-collection-action')===name);
const select=p=>all(p.element).find(n=>n.getAttribute('data-metrics-collection-field')==='delivery');
const expand=async p=>{p.element.open=true;await p.element.fire('toggle');};
const choose=async(p,id='delivery-1')=>{select(p).value=id;await select(p).fire('change');};
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
test('패널 펼치기는 대상 GET만 하고 명시 클릭만 단일 성과 POST한다',async()=>{
 const calls=[];const {panel,collected}=setup(async(u,o)=>{calls.push([u,o]);return response(o.method==='GET'?list():{observation:observation()});});
 await panel.open('all',{writable:true});assert.equal(calls.length,0);await expand(panel);assert.equal(calls.length,1);assert.equal(calls[0][0],'/api/v2/metrics/collection-targets?account=all');assert.equal(calls[0][1].method,'GET');
 await choose(panel);assert.equal(panel.isDirty(),true);await action(panel,'collect').fire('click');assert.equal(calls.length,2);assert.equal(calls[1][0],'/api/v2/metrics/collect');assert.deepEqual(JSON.parse(calls[1][1].body),{delivery_id:'delivery-1'});assert.equal(collected.length,1);assert.match(panel.element.textContent,/25/);assert.equal(panel.isDirty(),false);
});
test('조회 비활성·읽기 전용·미등록 선택은 수집을 실행하지 않는다',async()=>{
 let calls=0;const {panel}=setup(async()=>{calls++;return response(list('personal',{execution_enabled:false}));});await panel.open('personal',{writable:true});await expand(panel);await choose(panel);await action(panel,'collect').fire('click');assert.equal(calls,1);
 panel.refreshControls({writable:false});assert.equal(select(panel).disabled,true);await panel.open('invalid',{writable:true});await expand(panel);assert.equal(calls,1);
});
test('401·409·503·네트워크 오류는 선택을 보존하고 자동 재요청하지 않는다',async()=>{
 for(const code of [401,409,503,'network']){const calls=[];const {panel}=setup(async(u,o)=>{calls.push(o.method);if(o.method==='GET')return response(list());if(code==='network')throw new Error('secret');return response({},code);});await panel.open('all',{writable:true});await expand(panel);await choose(panel);await action(panel,'collect').fire('click');assert.equal(select(panel).value,'delivery-1');assert.equal(panel.isDirty(),true);assert.deepEqual(calls,['GET','POST']);assert.doesNotMatch(panel.element.textContent,/secret/);}
});
test('대기 중 중복 클릭은 한 번만 전송하고 응답 계정·대상 불일치는 거부한다',async()=>{
 const gate=deferred();const calls=[];const {panel,collected}=setup(async(u,o)=>{calls.push(o.method);return o.method==='GET'?response(list()):gate.promise;});await panel.open('all',{writable:true});await expand(panel);await choose(panel);const pending=action(panel,'collect').fire('click');assert.equal(panel.isBusy(),true);await action(panel,'collect').fire('click');assert.equal(calls.length,2);gate.resolve(response({observation:observation({target_id:'wrong'})}));await pending;assert.equal(collected.length,0);assert.equal(select(panel).value,'delivery-1');assert.match(panel.element.textContent,/확인할 수 없/);
});
test('추가 대상 필드·소유자·중복 항목·잘못된 수치 응답은 반영하지 않는다',async()=>{
 for(const bad of [list('dept',{extra:true}),list('dept',{items:[target({owner_account_id:'other'})]}),list('dept',{items:[target(),target()]})]){const {panel}=setup(async()=>response(bad));await panel.open('dept',{writable:true});await expand(panel);assert.equal(select(panel),undefined);assert.match(panel.element.textContent,/확인할 수 없/);}
 const {panel,collected}=setup(async(u,o)=>response(o.method==='GET'?list():{observation:observation({values:{views:'<script>'}})}));await panel.open('all',{writable:true});await expand(panel);await choose(panel);await action(panel,'collect').fire('click');assert.equal(collected.length,0);assert.doesNotMatch(panel.element.textContent,/<script>/);
});
test('늦은 이전 계정 응답은 새 계정을 침범하지 않고 같은 계정 refresh는 선택 포커스를 보존한다',async()=>{
 const gate=deferred();const {panel,document}=setup(u=>u.endsWith('personal')?gate.promise:Promise.resolve(response(list('dept'))));await panel.open('personal',{writable:true});const old=expand(panel);await panel.open('dept',{writable:true});await expand(panel);await choose(panel);const s=select(panel);s.focus();panel.refreshControls({writable:true});await panel.open('dept',{writable:true});assert.equal(document.activeElement,s);gate.resolve(response(list('personal')));await old;assert.equal(select(panel).value,'delivery-1');assert.match(panel.element.textContent,/학과/);panel.discardChanges();assert.equal(panel.isDirty(),false);
});
test('수집 응답 대기 제한 후에는 선택을 유지하고 목록 재조회 전 자동 재수집하지 않는다',async()=>{
 let posts=0;const {panel}=setup(async(u,o)=>o.method==='GET'?response(list()):(posts++,new Promise(()=>{})),{requestTimeoutMs:5});await panel.open('all',{writable:true});await expand(panel);await choose(panel);await action(panel,'collect').fire('click');assert.equal(panel.isBusy(),false);assert.equal(select(panel).value,'delivery-1');await action(panel,'collect').fire('click');assert.equal(posts,1);assert.match(panel.element.textContent,/다시 조회/);
});

test('계정 필터는 원본 소유자가 아니라 실제 발행 대상 계정에 결속한다',async()=>{
 const {panel}=setup(async()=>response(list('personal',{items:[target()]})));
 await panel.open('personal',{writable:true});await expand(panel);assert.equal(select(panel),undefined);assert.match(panel.element.textContent,/확인할 수 없/);
 const dept=setup(async()=>response(list('dept',{items:[target()]}))).panel;
 await dept.open('dept',{writable:true});await expand(dept);assert.ok(select(dept));assert.match(dept.element.textContent,/학과 \/ youtube/);
});
