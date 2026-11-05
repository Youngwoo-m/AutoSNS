from pathlib import Path
import json,subprocess,os,hashlib
p=Path(__file__).resolve().parent
f=p/'final-content.json';d=json.loads(f.read_text());before_answer=d['answer_sections'];before_pdf=(p/'01일차_강관동바리_답안예시_따라쓰기.pdf').read_bytes();before_state=json.loads((p/'작성상태.json').read_text())
(p/'before-source-fix-content.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
d['intro']=['안녕하세요. 거푸집·강관 동바리 문제는 시공 전에 무엇을 검토하고, 조립·해체 단계에서 처짐과 붕괴를 어떻게 막을지 함께 묻는 문제예요.','Q-net이 2026년 8월 24일 공개한 제140회 건설안전기술사 문제지의 제2교시 5번을 법령 조문과 연결해 살펴볼게요.']
row=next(x for x in d['table']['rows'] if x[0]=='강관틀')
row[1]='제332조의2제2호 가목: 강관틀과 강관틀 사이에 교차가새 설치.\n나목: 최상단 및 5단 이내마다 동바리의 측면과 틀면의 방향 및 교차가새의 방향에서 5개 이내마다 수평연결재를 설치하고 수평연결재의 변위 방지.\n다목: 최상단 및 5단 이내마다 동바리의 틀면의 방향에서 양단 및 5개틀 이내마다 교차가새의 방향으로 띠장틀 설치.'
x=d['explanations'][0]['paragraphs'][1]
x=x.replace('여기부터는 학습상 해설입니다. ','').replace('학습상으로는 구조검토를 할 때','구조검토를 할 때').replace(' 이 항목들을 법령이 하나하나 열거한다는 뜻은 아니고, 제330조(견고한 구조)·제331조(구조검토)·제332조(침하 방지)의 취지를 바탕으로 한 해석이에요.','')
d['explanations'][0]['paragraphs'][1]=x
x=d['explanations'][1]['paragraphs'][1];assert x.startswith('학습상 해설로는 ');d['explanations'][1]['paragraphs'][1]=x.replace('학습상 해설로는 ','',1)
x=d['explanations'][2]['paragraphs'][1]
x=x.replace(' 여기서 구조안전성 확인과 해체계획에 따른 순서 관리는 법령 문구 그대로가 아니라 안전관리 차원의 학습상 해설이에요.','').replace(' 이 글에는 강도나 해체일수 같은 임의 수치를 적지 않았어요.','')
d['explanations'][2]['paragraphs'][1]=x
d['pitfalls'][2]='해체를 강도나 일수 같은 숫자로만 외우지 마세요. 설계도서상 양생기간을 먼저 확인하고, 구조안전성과 해체계획을 함께 점검해 주세요.'
d['note']='이 글은 학습용 답안 예시이며 공식 정답이나 채점기준이 아니에요. 표의 법령 직접 의무와 학습상 해설은 구분해 읽어 주세요. 하중 전달경로·부재 강성·지지층 안정성의 검토와 해체계획에 따른 순서 관리는 제330조~제334조의 취지를 풀어 설명한 부분이며, 법령이 그 항목을 하나하나 열거한다는 뜻은 아닙니다. 개별 현장의 구조설계나 작업계획을 대체하지 않습니다.'
d['tags']=[('건설안전기술사기출' if t=='하루한문제' else t) for t in d['tags']]+['기술사답안작성']
assert len(d['tags'])==9 and sum('기출' in t for t in d['tags'])==1
assert d['answer_sections']==before_answer
f.write_text(json.dumps(d,ensure_ascii=False,indent=2))
build=p/'build_outputs.py';s=build.read_text()
s=s.replace("esc=lambda s:html.escape(str(s))", "esc=lambda s:html.escape(str(s))\ndef intro_html():\n parts=[esc(s) for s in D['intro']]\n public_title='Q-net이 2026년 8월 24일 공개한 제140회 건설안전기술사 문제지'\n parts[1]=parts[1].replace(public_title,'<a href=\"'+QNET+'\">'+public_title+'</a>')\n return '\\n'.join('<p>'+x+'</p>' for x in parts)")
s=s.replace("esc(x)+f'</{tag}>'", "esc(x).replace('\\n','<br>')+f'</{tag}>'")
s=s.replace("image('banner.png','거푸집·강관 동바리 타설 전 확인사항',blogger),paras(D['intro'])", "image('banner.png','거푸집·강관 동바리 타설 전 확인사항',blogger),'<p><small>배너: AI 생성 디오라마(학습용 이미지).</small></p>',intro_html()")
build.write_text(s)
subprocess.run([str(Path('/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/claude-jobs/.venv/bin/python')),str(build)],check=True)
# 답안 예시 내용은 변경되지 않았으므로 기존 검산/렌더 PDF 바이트를 유지한다.
(p/'01일차_강관동바리_답안예시_따라쓰기.pdf').write_bytes(before_pdf)
state=json.loads((p/'작성상태.json').read_text())
for k in ('calc','review','urls','status'):
 if k in before_state:state[k]=before_state[k]
state['source_fix_round1']={'issues_resolved':4,'ai_banner_disclosure_added':True,'qnet_publication_date':'2026-08-24','qnet_exam_date_note':'시행일과게시일을구분;본문은게시일만표기','pdf_answer_unchanged':True}
(p/'작성상태.json').write_text(json.dumps(state,ensure_ascii=False,indent=2))
manifest=json.loads((p/'manifest.json').read_text())
for item in manifest['public_assets']:
 asset=p/item['name'];item['bytes']=asset.stat().st_size;item['sha256']=hashlib.sha256(asset.read_bytes()).hexdigest()
manifest['manuscripts']={name:hashlib.sha256((p/name).read_bytes()).hexdigest() for name in ['티스토리게시본문.html','Blogger게시본문.html']}
manifest['source_fix_round1']=state['source_fix_round1'];(p/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
report=json.loads((p/'report.json').read_text());report['status']='source_fixes_applied_pending_parent_rereview';report['source_fix_round1']=state['source_fix_round1'];report['notes']=[n for n in report['notes'] if '강관틀표행세부방향' not in n];report['notes'].append('강관틀제332조의2제2호나목/다목방향·개수·양단·변위방지조건전부보존');(p/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
(p/'source-fix-resolution.json').write_text(json.dumps({'source_review':'source-review.json fix4','resolved':['강관틀나목/다목전체조건','글머리주제우선+Qnet공개일2026-08-24링크','반복단서끝한문단정리','태그9개중기출1·답안1','AI생성배너고지'],'pdf_answer_changed':False,'pdf_bytes_preserved':True,'public_model_calls_this_fix':0,'publication_calls':0,'deployment_calls':0},ensure_ascii=False,indent=2))
print('source fixes applied; pdf unchanged; tags',len(d['tags']))
