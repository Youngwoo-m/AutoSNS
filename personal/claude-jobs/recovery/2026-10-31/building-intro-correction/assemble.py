from pathlib import Path
import re,json,html,hashlib,difflib,collections
OUT=Path(__file__).resolve().parent
ROOT=Path('/Volumes/USB256/devAPP/AutoSNS')
source=ROOT/'GeoAI_NA/building-engineer-writing/첫글_준비하기/수정본_새문체.html'
s=source.read_text();body=(ROOT/'GeoAI_NA/claude-jobs/recovery/2026-10-31/building-corrected-pending-banner.html').read_text()
model=json.loads((OUT/'humanizer-pass2.json').read_text())
future=re.findall(r'<p>앞으로 .*?</p>',body,re.S);assert len(future)==1
future_text=html.escape(model['future_paragraph'],quote=False)
topic='‘한중콘크리트의 시공과 양생관리’';assert topic in future_text
future_text=future_text.replace(topic,'<strong>'+topic+'</strong>')
body=body.replace(future[0],'<p>'+future_text+'</p>')
request=re.findall(r'<p>문제를 요청하시면.*?</p>',body,re.S);assert len(request)==1
body=body.replace(request[0],'<p>'+html.escape(model['request_sentence'],quote=False)+'</p>')
banner='<p style="text-align:center"><img src="{{BANNER_URL}}" alt="건축시공기술사 준비하기 — 재난안전과 GeoAI" style="max-width:100%;height:auto"></p>\n'
body=banner+body
assert '공정·원가·계약' not in body
assert 'data-ax-attach' not in body
assert '세명대학교' not in body
# Verify every existing source link is unchanged, and all numeric tokens are preserved
# except the specifically removed inaccurate statistics row.
rows=re.findall(r'<tr>.*?</tr>',s,re.S);removed=[x for x in rows if '공정·원가·계약' in x];assert len(removed)==1
baseline=s.replace(removed[0],'')
def links(t):return collections.Counter(re.findall(r'href="([^"]+)"',t))
def numbers(t):
 t=re.sub(r'<[^>]+>','',t)
 return collections.Counter(re.findall(r'\d+(?:\.\d+)?',html.unescape(t)))
assert links(baseline)==links(body)
assert numbers(baseline)==numbers(body),(numbers(baseline)-numbers(body),numbers(body)-numbers(baseline))
source_tables=re.findall(r'<table.*?</table>',baseline,re.S);final_tables=re.findall(r'<table.*?</table>',body,re.S)
assert source_tables==final_tables
assert body.rfind('답안지 요청')>body.find('자료 확인일')
(OUT/'local-before-correction.html').write_text(s)
(OUT/'removed-inaccurate-row.html').write_text(removed[0])
(OUT/'edit-ready.html').write_text(body)
(OUT/'Blogger-ready.html').write_text(body)
(OUT/'제목.txt').write_text('[건축시공기술사] 건축시공기술사 준비하기\n')
(OUT/'태그.txt').write_text('건축시공기술사,건축시공,기술사,콘크리트,철골,건축기사,기출분석\n')
local=body.replace('{{BANNER_URL}}',(OUT/'banner.png').as_uri())
css='body{font-family:"Apple SD Gothic Neo",sans-serif;max-width:900px;margin:30px auto;padding:0 18px;font-size:18px;line-height:1.8;color:#182532}h1,h2,h3{line-height:1.5}table{font-size:16px}td,th{padding:9px}img{max-width:100%}blockquote{border-left:4px solid #a6bfcd;margin:20px 0;padding:8px 16px;background:#f3f7fa}a{color:#16719c}'
preview='<!doctype html><html lang="ko"><meta charset="utf-8"><title>건축 입문글 보완 미리보기</title><style>'+css+'</style><body><h1>[건축시공기술사] 건축시공기술사 준비하기</h1>'+local+'</body></html>'
(OUT/'preview.html').write_text(preview)
(OUT/'diff-from-local-before.patch').write_text(''.join(difflib.unified_diff(s.splitlines(keepends=True),body.splitlines(keepends=True),fromfile='local-before-correction.html',tofile='edit-ready.html')))
checks={'removed_rows':1,'replacement_count_claims_added':0,'other_numeric_tokens_unchanged':True,'href_multiset_unchanged':True,'remaining_tables_identical_to_source':True,'table_count':len(final_tables),'request_at_bottom':True,'banner_placeholder':'{{BANNER_URL}}','native_attach_placeholder_count':0,'personal_brand_only':True,'independent_calc_review':'pending root','independent_source_review':'pending root','publication_calls':0,'original_files_modified':False}
(OUT/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
files={f.name:{'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()} for f in OUT.iterdir() if f.is_file() and f.name not in ('manifest.json','report.json')}
(OUT/'manifest.json').write_text(json.dumps({'source':str(source),'files':files},ensure_ascii=False,indent=2))
print(json.dumps(checks,ensure_ascii=False))
