const rows = (value) => Array.isArray(value) ? value : [];
export const accountLabel = (id, accounts=[]) => accounts.find(a=>a.id===id)?.label || ({dept:'학과',personal:'개인',all:'전체 계정'}[id]) || '계정 미확인';
export const kindLabel = kind => ({article:'글',card:'카드뉴스',short:'숏츠',video:'영상'}[kind] || '형식 미확인');
export function statusLabel(status) {
  return ({idea:'아이디어',drafting:'조사·원고',review:'검토 필요',scheduled:'예약·대기',reported_published:'게시 기록 · 공개 미확인',failed:'실패 · 확인 필요',unknown:'상태 미확인',draft:'초안',queued:'로컬 대기열',scheduled_recorded:'예약 기록 · 현재 미확인',verified:'공개·내용 확인 완료',paused:'사용자 중지',open:'조치 필요',resolved:'해결 기록',closed:'종료 기록',pending:'대기',accepted:'채택 기록',rejected:'반려 기록'}[status] || '상태 미확인');
}
export const scheduleLabel = kind => ({local_request:'로컬 실행 요청',remote_recorded:'원격 예약 기록 · 현재 재조회 아님'}[kind] || '예약 출처 미확인');
export function safeUrl(value) {
  if(typeof value!=='string'||/[\u0000-\u0020\u007f]/.test(value)||!/^https?:\/\//i.test(value)) return null;
  try { const url=new URL(value);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password ? url.href : null; } catch { return null; }
}
export function relatedContents(snapshot,account='all') {
  const contents=rows(snapshot.contents);
  if(account==='all') return contents;
  const ids=new Set(rows(snapshot.deliveries).filter(d=>d.destination_account_id===account||d.owner_account_id===account).map(d=>d.content_id));
  const routes=rows(snapshot.crossposts).filter(r=>r.destination_account_id===account);
  return contents.filter(c=>c.owner_account_id===account||ids.has(c.id)||routes.some(r=>r.owner_account_id===c.owner_account_id&&rows(c.channels).includes(r.source_channel)));
}
export function filterContents(snapshot, {account='all',query='',kind='all',series='all',status='all',owner='all'}={}) {
  const q=query.trim().toLocaleLowerCase();
  return relatedContents(snapshot,account).filter(c=>{
    const deliveries=rows(snapshot.deliveries).filter(d=>d.content_id===c.id);
    const search=[c.title,c.summary,c.series,...rows(c.channels),...deliveries.flatMap(d=>[d.channel,d.target_label])].filter(Boolean).join(' ').toLocaleLowerCase();
    return (!q||search.includes(q))&&(kind==='all'||c.kind===kind)&&(series==='all'||(series==='__none'?!c.series:c.series===series))&&(owner==='all'||c.owner_account_id===owner)&&(status==='all'||c.status===status||deliveries.some(d=>d.status===status));
  });
}
export function aggregate(snapshot) {
  const contents=rows(snapshot.contents),deliveries=rows(snapshot.deliveries);
  return {contents:contents.length,deliveries:deliveries.length,verified:deliveries.filter(d=>d.status==='verified'&&typeof d.evidence==='string'&&d.evidence.trim()).length,pending:deliveries.filter(d=>['queued','scheduled_recorded'].includes(d.status)).length,review:contents.filter(c=>c.status==='review').length,incidents:rows(snapshot.incidents).filter(i=>!['resolved','closed'].includes(i.status)).length};
}
export function dayKey(value) {
  if(!value) return null;const date=new Date(value);if(Number.isNaN(date.getTime())) return null;
  const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).formatToParts(date);
  const get=type=>parts.find(p=>p.type===type).value;
  return `${get('year')}-${get('month')}-${get('day')}`;
}
export function formatDateTime(value) {
  if(!dayKey(value)) return '시각 미확인';
  return new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(new Date(value));
}
export function weekDays(value=new Date().toISOString(),offset=0) {
  const key=dayKey(value)||dayKey(new Date().toISOString());const date=new Date(`${key}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate()-((date.getUTCDay()+6)%7)+offset*7);
  return Array.from({length:7},(_,i)=>{const d=new Date(date);d.setUTCDate(date.getUTCDate()+i);return d.toISOString().slice(0,10);});
}
