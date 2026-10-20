'use strict';
const form = document.getElementById('question-form');
const question = document.getElementById('question');
question.addEventListener('input', () => { document.getElementById('count').textContent = `${question.value.length.toLocaleString()} / 5,000`; });
form.addEventListener('submit', async event => {
  event.preventDefault();
  if (!form.reportValidity()) return;
  if (document.getElementById('title').value.trim().length < 1 || question.value.trim().length < 10) {
    const status = document.getElementById('form-status'); status.textContent = '제목과 10자 이상의 문제 내용을 입력해주세요.'; status.className = 'error'; return;
  }
  const button = form.querySelector('[type=submit]'), status = document.getElementById('form-status');
  button.disabled = true; status.className = ''; status.textContent = '문제를 접수하고 있습니다…';
  try {
    const response = await fetch('/', { method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body: new URLSearchParams(new FormData(form)).toString() });
    if (!response.ok) throw new Error('submission failed');
    location.assign('/questions/thanks/');
  } catch (error) {
    status.className = 'error'; status.textContent = '접수 결과를 확인하지 못했습니다. 입력 내용은 남아 있습니다. 잠시 후 다시 시도해주세요.'; button.disabled = false;
  }
});
let answers = [], kind = 'all';
const search = document.getElementById('search'), list = document.getElementById('answer-list');
function render() {
  const term = search.value.trim().toLocaleLowerCase();
  const matched = answers.filter(item => (kind === 'all' || item.kind === kind) && `${item.title} ${(item.tags || []).join(' ')}`.toLocaleLowerCase().includes(term));
  list.replaceChildren();
  document.getElementById('total').textContent = `${matched.length}문제`;
  for (const item of matched) {
    let url; try { url = new URL(item.url); } catch { continue; }
    if (url.protocol !== 'https:' || url.hostname !== 'na-geoai.tistory.com') continue;
    const link = document.createElement('a'); link.className = 'answer'; link.href = url.href; link.target = '_blank'; link.rel = 'noopener';
    const meta = document.createElement('div'); meta.className = 'answer-meta';
    const badge = document.createElement('span'); badge.className = `badge${item.kind === 'request' ? ' request-badge' : ''}`; badge.textContent = item.kind === 'request' ? '친구 요청' : `하루 한 문제${item.day ? ` · ${item.day}일차` : ''}`;
    const date = document.createElement('time'); date.dateTime = item.date; date.textContent = item.date.replaceAll('-', '.'); meta.append(badge, date);
    const title = document.createElement('h3'); title.textContent = item.title + ' ↗';
    const tags = document.createElement('p'); tags.textContent = (item.tags || []).join(' · ');
    link.append(meta, title, tags);
    if (item.tracingPdf) { const pdf = document.createElement('span'); pdf.className = 'pdf'; pdf.textContent = '모범답안 + 따라쓰기 PDF'; link.append(pdf); }
    list.append(link);
  }
  if (!matched.length) { const empty = document.createElement('p'); empty.className = 'empty'; empty.textContent = kind === 'request' && !term ? '친구 요청 답안이 발행되면 이곳에 추가됩니다.' : '조건에 맞는 문제가 없습니다.'; list.append(empty); }
}
search.addEventListener('input', render);
for (const button of document.querySelectorAll('.filter')) button.addEventListener('click', () => {
  kind = button.dataset.kind;
  for (const sibling of document.querySelectorAll('.filter')) { sibling.classList.toggle('active', sibling === button); sibling.setAttribute('aria-pressed', String(sibling === button)); }
  render();
});
(async () => {
  try {
    const response = await fetch('/questions/published.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('list unavailable');
    const data = await response.json(); answers = data.items; render();
    document.getElementById('list-status').textContent = '발행이 완료된 글만 목록에 표시합니다.';
  } catch {
    document.getElementById('list-status').textContent = '최신 목록을 불러오지 못했습니다. 티스토리에서 전체 글을 확인해주세요.';
  }
})();
