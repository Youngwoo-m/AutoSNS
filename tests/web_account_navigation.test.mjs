import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {ROUTES,normalizeRoute,routeForView,publishingViews,visibleSnapshot} from '../ax-console/app/web/account_navigation.js';
const source=readFileSync(new URL('../ax-console/app/web/app.js',import.meta.url),'utf8');
const navigate=source.slice(source.indexOf('function navigate(target) {'),source.indexOf('// 기존 내부 링크'));
test('계정과 작업 영역을 정확히 네 메뉴로 분리한다',()=>{
 assert.deepEqual(ROUTES.map(r=>r.label),['개인 계정 연결','학과 계정 연결','개인 콘텐츠 발행','학과 콘텐츠 발행']);
 assert.equal(new Set(ROUTES.map(r=>r.account+':'+r.area)).size,4);
 assert.equal(routeForView('dept','accounts').area,'accounts');
 assert.equal(routeForView('dept','engineer').view,'planning');
 assert.ok(publishingViews('personal').some(r=>r.id==='engineer'));
 assert.equal(visibleSnapshot('dept',{account:'personal',snapshot:{secret:true}}),null);
});
function host(allow=true){
 const calls=[];let finish;
 const dialog={open:false};
 const ctx={normalizeRoute,confirmLeave:()=>allow,$:selector=>selector==='#detail-dialog'?dialog:{focus(){}},closeDetail:()=>true,toolkitSurfaces:new Map(),operations:{load:a=>calls.push('operations:'+a)},metrics:{load:a=>calls.push('metrics:'+a)},loader:{select:a=>calls.push('select:'+a),refresh:()=>calls.push('refresh')},render:()=>calls.push('render'),oauthPanel:{close:()=>new Promise(r=>{finish=r;})}};
 const api=vm.runInNewContext(`let route={account:'personal',area:'publishing'},view='planning',detailMode='legacy';${navigate};({navigate,get:()=>({...route,view}),oauth:()=>detailMode='oauth',closed:()=>detailMode='legacy'})`,ctx);
 return {api,calls,finish:()=>finish(true)};
}
test('미저장 가드가 거절하면 계정과 요청을 바꾸지 않는다',()=>{const h=host(false);h.api.navigate({account:'dept',area:'accounts'});assert.equal(h.api.get().account,'personal');assert.equal(h.calls.length,0);});
test('계정 전환 시 계정별 제어기와 snapshot을 함께 전환한다',()=>{const h=host();h.api.navigate({account:'dept',area:'accounts'});assert.equal(h.api.get().account,'dept');assert.deepEqual(h.calls.slice(0,3),['operations:dept','metrics:dept','select:dept']);});
test('OAuth 닫기가 완료되기 전에는 계정을 바꾸지 않는다',async()=>{const h=host();h.api.oauth();h.api.navigate({account:'dept',area:'accounts'});assert.equal(h.api.get().account,'personal');h.api.closed();h.finish();await Promise.resolve();assert.equal(h.api.get().account,'dept');});
