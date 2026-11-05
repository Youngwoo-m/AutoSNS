from pathlib import Path
import json,re,html,hashlib
OUT=Path(__file__).resolve().parent
d=json.loads((OUT/'final-content.json').read_text())
assert '방향이 좋아요' in d['intent'][1], 'already fixed or unexpected source'
(OUT/'before-source-fix-content.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
v=json.loads(json.dumps(d))
v['intent'][0]=v['intent'][0].replace(' 채점 경험이 아니라 문제 문구를 바탕으로 한 학습용 해석이에요.','')
v['intent'][1]=v['intent'][1].replace('쓰고,','기술하고,',1).replace('구분해 보충하는 방향이 좋아요.','구분하여 보충한다.').replace('연결로 쓰고,','연결로 서술하고,').replace('덧붙이면 돼요.','덧붙인다.')
v['explanations'][0]['paragraphs'][1]=v['explanations'][0]['paragraphs'][1].replace(' 조문 순서를 풀어 쓴 학습용 정의이니, 답안에서는 조문 취지가 드러나게 쓰면 돼요.','')
v['explanations'][2]['paragraphs'][1]=v['explanations'][2]['paragraphs'][1].replace(' 세부 참여 방법은 이번 글에서 다루지 않아요.','')
v['note']=v['note'].replace('출제의도와 답안 방향은 채점 경험이 아닌 학습용 해석이며,','정의는 조문 취지를 풀어 쓴 학습용 설명이고, 출제의도와 답안 방향은 채점 경험이 아닌 학습용 해석이며,')
assert v['answer_sections']==d['answer_sections']
assert re.findall(r'\d+',json.dumps(v,ensure_ascii=False))==re.findall(r'\d+',json.dumps(d,ensure_ascii=False))
changes=[(d['intent'][0],v['intent'][0]),(d['intent'][1],v['intent'][1]),(d['explanations'][0]['paragraphs'][1],v['explanations'][0]['paragraphs'][1]),(d['explanations'][2]['paragraphs'][1],v['explanations'][2]['paragraphs'][1]),(d['note'],v['note'])]
for n in ['티스토리게시본문.html','Blogger게시본문.html']:
 p=OUT/n;before=p.read_text();s=before
 for a,b in changes:
  a=html.escape(a);b=html.escape(b);assert s.count(a)==1,(n,a[:80],s.count(a));s=s.replace(a,b,1)
 assert re.findall(r'\d+',s)==re.findall(r'\d+',before)
 p.write_text(s)
(OUT/'final-content.json').write_text(json.dumps(v,ensure_ascii=False,indent=2))
pdf=OUT/'02일차_위험성평가_답안예시_따라쓰기.pdf'
assert hashlib.sha256(pdf.read_bytes()).hexdigest()=='f538bf21a1aef2cd1822b5ba244240ad8f49fc909db68b0e83c229c4110c5c2a'
resolution={'source_verdict':'fix','fixed_issues':2,'method':'루트 지시에 따라 출처검토 비수치지적을 로컬 최소편집. Max한정편집 호출은 실행 시작전 대기상태에서 취소했으며 응답파일없음.','changes':[{'before':a,'after':b} for a,b in changes],'numeric_tokens_unchanged':True,'answer_sections_unchanged':True,'pdf_regenerated':False,'pdf_sha256':'f538bf21a1aef2cd1822b5ba244240ad8f49fc909db68b0e83c229c4110c5c2a'}
(OUT/'source-fix-resolution.json').write_text(json.dumps(resolution,ensure_ascii=False,indent=2))
print('source fixes applied; numeric tokens/answer/PDF unchanged')
