import test from 'node:test';
import assert from 'node:assert/strict';
import * as editor from '../ax-console/app/web/content_editor.js';
import {relatedContents,statusLabel} from '../ax-console/app/web/view_helpers.js';
import * as apiModule from '../ax-console/app/web/api.js';
const createContentApi=(...args)=>apiModule.createContentApi(...args);
const doc={id:'managed_x',source:'managed',owner_account_id:'personal',revision:3,manifest_hash:'abc',title:'<제목>',kind:'article',series:'연습',status:'drafting',original:'원문',variants:[{destination_account_id:'dept',platform:'tiktok',text:'학과 변환'}],sources:[{url:'https://example.org',note:'근거'}],assets:[{id:'a'}],reviews:[]};
test('새 원본은 조회 필터와 별도로 소유자를 명시해야 한다',()=>{
 assert.throws(()=>editor.toContentPayload({...editor.emptyDraft(),title:'제목'}),/소유/);
 const payload=editor.toContentPayload({...editor.emptyDraft(),owner_account_id:'personal',title:'제목'});
 assert.equal(payload.owner_account_id,'personal');
});
test('전체 편집 필드와 대상 계정을 보존하고 서버 전용 필드는 PUT에서 제외한다',()=>{
 const payload=editor.toContentPayload(editor.draftFromContent(doc),doc);
 assert.equal(payload.expected_revision,3);assert.equal(payload.owner_account_id,undefined);assert.equal(payload.assets,undefined);
 assert.deepEqual(payload.variants,doc.variants);assert.deepEqual(payload.sources,doc.sources);
});
test('409 및 인증 실패는 입력 초안과 원래 revision을 유지한다',async()=>{
 const session=editor.createEditSession(doc);session.draft.original='미저장 수정';
 await session.save(async()=>{throw Object.assign(new Error('conflict'),{status:409});});
 assert.equal(session.draft.original,'미저장 수정');assert.equal(session.content.revision,3);assert.equal(session.phase,'conflict');assert.equal(session.dirty(),true);
 await session.save(async()=>{throw Object.assign(new Error('login'),{status:401});});assert.equal(session.phase,'unauthorized');assert.equal(session.draft.original,'미저장 수정');
});
test('수동 검토는 선택한 버전과 해시에만 귀속되고 최신 검토로 승격하지 않는다',()=>{
 assert.deepEqual(editor.reviewPayload(doc,'source','pass','확인'),{revision:3,manifest_hash:'abc',kind:'source',decision:'pass',notes:'확인'});
 assert.match(editor.reviewLabel({...doc,revision:2,method:'manual',decision:'pass'}),/버전 2.*수동/);
});
test('legacy 복사는 전체 원문으로 속이지 않고 소유자 선택을 비운다',()=>{
 const draft=editor.copyLegacySummary({title:'기존',summary:'수집 요약',owner_account_id:'dept',kind:'short'});
 assert.equal(draft.owner_account_id,'');assert.equal(draft.original,'수집 요약');assert.equal(draft.status,'idea');
});
test('managed 목표 계정은 배포 기록 없이 관련 계정 조회에 포함된다',()=>{
 const snapshot={contents:[{...doc,target_accounts:['dept']}],deliveries:[],crossposts:[]};
 assert.equal(relatedContents(snapshot,'dept').length,1);assert.equal(statusLabel('production'),'제작');assert.equal(statusLabel('archived'),'보관');
});
test('API는 CAS JSON 및 raw 자산 헤더, 과거 버전 경로와 인증 오류를 전달한다',async()=>{
 const calls=[];const api=createContentApi({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>doc};}});
 await api.updateContent(doc.id,{expected_revision:3,title:'새 제목'});
 assert.equal(calls[0].options.method,'PUT');assert.equal(JSON.parse(calls[0].options.body).expected_revision,3);
 await api.uploadAsset(doc.id,3,{name:'한글.png',type:'image/png'});
 assert.equal(calls[1].options.headers['X-AX-Filename'],encodeURIComponent('한글.png'));assert.equal(calls[1].options.headers['X-AX-Expected-Revision'],'3');
 await api.getContent(doc.id,2);assert.match(calls[2].url,/revision=2$/);
 const fail=createContentApi({fetcher:async()=>({ok:false,status:401,json:async()=>({})})});await assert.rejects(fail.createContent({}),e=>e.status===401);
});

test('계정 이동을 취소하면 설정 초안·dirty·조회 범위를 유지하고 승인하면 초기화한다',async()=>{
 const {createIntegrationDraftState,confirmSettingsNavigation}=await import('../ax-console/app/web/integration_settings.js');
 const state=createIntegrationDraftState();
 state.account='personal';state.draft={account_id:'personal',provider_id:'local',connection_id:'main',platform:'youtube',target_label:'미저장 개인 채널',enabled_preference:true,notes:'취소 시 보존',revision:4};state.dirty=true;
 const before=JSON.stringify(state.draft);
 function navigate(account,confirmed){if(!confirmSettingsNavigation(state,()=>confirmed))return false;state.account=account;return true;}
 assert.equal(navigate('dept',false),false);assert.equal(state.account,'personal');assert.equal(JSON.stringify(state.draft),before);assert.equal(state.hasUnsavedChanges(),true);
 assert.equal(navigate('dept',true),true);assert.equal(state.account,'dept');assert.equal(state.draft.account_id,'');assert.equal(state.draft.notes,'');assert.equal(state.draft.revision,0);assert.equal(state.hasUnsavedChanges(),false);
});
test('저장 완료한 설정은 확인 없이 이동하며 성공 응답 초안을 초기화하지 않는다',async()=>{
 const {createIntegrationDraftState,confirmSettingsNavigation}=await import('../ax-console/app/web/integration_settings.js');
 const state=createIntegrationDraftState();state.draft={account_id:'personal',revision:5,notes:'저장 완료'};
 assert.equal(confirmSettingsNavigation(state,()=>{throw new Error('저장 완료 상태는 확인하지 않음');}),true);
 assert.equal(state.draft.revision,5);assert.equal(state.draft.notes,'저장 완료');
});
