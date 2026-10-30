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
