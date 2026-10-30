const scopes = new Set(['all','dept','personal']);
const lists=['warnings','accounts','contents','deliveries','channels','schedule','incidents','crossposts','proposals'];
export async function fetchSnapshot(account='all',{signal,fetcher=globalThis.fetch}={}) {
  if(!scopes.has(account)) throw new Error('계정 조회 범위가 올바르지 않습니다.');
  const response=await fetcher(`/api/v2/snapshot?account=${account}`,{method:'GET',credentials:'same-origin',cache:'no-store',signal,headers:{Accept:'application/json'}});
  if(!response.ok) { const error=new Error(response.status===401?'로그인이 필요합니다.':'조회하지 못했습니다. 잠시 후 다시 갱신해 주세요.');error.status=response.status;throw error; }
  const result=await response.json();
  if(result?.schema_version!==1||result.read_only!==true||!lists.every(k=>Array.isArray(result[k]))||!result.metrics||typeof result.generated_at!=='string') throw new Error('조회 데이터 형식을 확인할 수 없습니다.');
  if(result.scope!==account) throw new Error('조회 계정 범위가 일치하지 않습니다.');
  return result;
}
export function createSnapshotLoader(onChange,{request=fetchSnapshot}={}) {
  let state={account:'all',snapshot:null,phase:'idle',error:null},generation=0,controller;
  const emit=()=>onChange({...state});
  async function select(account) {
    if(!scopes.has(account)) throw new Error('계정 조회 범위가 올바르지 않습니다.');
    const current=++generation;controller?.abort();controller=new AbortController();
    state={account,snapshot:state.account===account?state.snapshot:null,phase:'loading',error:null};emit();
    try {const snapshot=await request(account,{signal:controller.signal});if(current!==generation)return;state={account,snapshot,phase:'ready',error:null};}
    catch(error){if(current!==generation)return;state={...state,phase:error.status===401?'unauthorized':'error',snapshot:error.status===401?null:state.snapshot,error:error.status===401?'로그인이 필요합니다.':'최신 데이터를 불러오지 못했습니다. 다시 갱신해 주세요.'};}
    emit();
  }
  return {select,refresh:()=>select(state.account)};
}

export async function refreshWorkspace({loader,integrationSettings,account,writable,editorDirty=false,confirm}) {
  if(editorDirty&&!confirm('저장하지 않은 변경을 버리고 이동할까요?'))return false;
  // Settings.load refreshes only the list; the draft and its CAS revision stay intact.
  await Promise.all([loader.refresh(),writable?integrationSettings.load(account):undefined]);
  return true;
}

export function createContentApi({fetcher=globalThis.fetch}={}) {
  async function request(path,{method='GET',body,headers={}}={}) {
    const response=await fetcher(`/api/v2${path}`,{method,credentials:'same-origin',cache:'no-store',headers:{Accept:'application/json',...headers},...(body===undefined?{}:{body})});
    if(!response.ok) {
      const message=({401:'로그인이 필요합니다. 입력 내용은 유지됩니다.',409:'다른 창에서 새 버전을 저장했습니다. 입력을 복사한 뒤 최신 버전을 다시 열어 주세요.',413:'저장 가능한 용량을 초과했습니다.',415:'지원하지 않는 파일 형식입니다.',503:'저장하지 못했습니다. 입력 내용을 유지합니다.'})[response.status]||'요청을 처리하지 못했습니다. 입력값과 서버 상태를 확인해 주세요.';
      throw Object.assign(new Error(message),{status:response.status});
    }
    return response.json();
  }
  const json=(path,method,body)=>request(path,{method,body:JSON.stringify(body),headers:{'Content-Type':'application/json'}});
  const item=id=>`/contents/${encodeURIComponent(id)}`;
  return {
    listConnections:()=>request('/connections'),
    listDeliveries:(account='all',contentId)=>request(`/deliveries?account=${encodeURIComponent(account)}${contentId?`&content_id=${encodeURIComponent(contentId)}`:''}`),
    getDelivery:id=>request(`/deliveries/${encodeURIComponent(id)}`),
    deliveryEvents:id=>request(`/deliveries/${encodeURIComponent(id)}/events`),
    previewDelivery:body=>json('/deliveries/preview','POST',body),
    createDelivery:body=>json('/deliveries','POST',body),
    approveDelivery:(id,body)=>json(`/deliveries/${encodeURIComponent(id)}/approvals`,'POST',body),
    previewDeliverySchedule:(id,body)=>json(`/deliveries/${encodeURIComponent(id)}/schedule-preview`,'POST',body),
    rescheduleDelivery:(id,body)=>json(`/deliveries/${encodeURIComponent(id)}/schedule`,'PUT',body),
    cancelDelivery:(id,body)=>json(`/deliveries/${encodeURIComponent(id)}/cancel`,'POST',body),
    getContent:(id,revision)=>request(item(id)+(revision?`?revision=${revision}`:'')),
    createContent:body=>json('/contents','POST',body),
    updateContent:(id,body)=>json(item(id),'PUT',body),
    listRevisions:id=>request(`${item(id)}/revisions`),
    uploadAsset:(id,revision,file)=>request(`${item(id)}/assets`,{method:'POST',body:file,headers:{'Content-Type':file.type||'application/octet-stream','X-AX-Filename':encodeURIComponent(file.name),'X-AX-Expected-Revision':String(revision)}}),
    recordReview:(id,body)=>json(`${item(id)}/reviews`,'POST',body),
    listIntegrationSettings:account=>request(`/integrations/settings?account=${encodeURIComponent(account)}`),
    putIntegrationSettings:body=>json('/integrations/settings','PUT',body)
  };
}
export const contentApi=createContentApi();
