import test from 'node:test';
import assert from 'node:assert/strict';
import {settingsPayload, rebaseSettingsDraft} from '../ax-console/app/web/integration_settings.js';
const draft={account_id:'personal',provider_id:'vidiq',connection_id:'main',platform:'youtube',target_label:'<채널>',enabled_preference:true,notes:'초안',revision:1};
test('flat settings payload excludes status and extra fields',()=>{
 const body=settingsPayload({...draft,connection_status:'connected',token:'secret'});
 assert.equal(body.expected_revision,1);
 assert.equal(body.target_label,'<채널>');
 assert.equal(Object.keys(body).length,8);
 assert.equal(body.token,undefined);
});
test('conflict recovery retains edits and requires explicit latest revision',()=>{
 const rebased=rebaseSettingsDraft(draft,{...draft,notes:'다른 창',revision:2});
 assert.equal(rebased.notes,'초안');assert.equal(rebased.revision,2);
 assert.throws(()=>rebaseSettingsDraft(draft,{...draft,account_id:'dept',revision:2}));
});
