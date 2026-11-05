import test from 'node:test';
import assert from 'node:assert/strict';
import {createContentApi} from '../ax-console/app/web/api.js';

test('Instagram 구성 검토는 계획 ID와 CAS 본문만 전송한다',async()=>{
 const calls=[];const api=createContentApi({fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>({status:'approved'})};}});
 const body={expected_review_revision:2,subject_hash:'subject',decision:'approved',checks:{caption_checked:true},notes:'사람이 확인'};
 await api.getInstagramReview('delivery_id');await api.recordInstagramReview('delivery_id',body);
 assert.equal(calls[0].url,'/api/v2/deliveries/delivery_id/instagram-review');assert.equal(calls[0].options.method,'GET');
 assert.equal(calls[1].options.method,'POST');assert.equal(calls[1].options.credentials,'same-origin');assert.deepEqual(JSON.parse(calls[1].options.body),body);
});
