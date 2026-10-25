from pathlib import Path
import json,re
import pdfplumber
P=Path(__file__).resolve().parent;src=json.loads((P/'sources.json').read_text());qs=[]
for s in src:
 with pdfplumber.open(P/f"{s['round']}.pdf") as pdf:
  texts=[p.extract_text(x_tolerance=1) or '' for p in pdf.pages]
  assert all('지형공간정보' in re.sub(r'\s+','',t) for t in texts),(s['round'],'wrong exam')
  for pi,t in enumerate(texts):
   # Every exam period is printed in the header; some periods span pages.
   m=re.search(r'제\s*([1-4])\s*교\s*시',t);period=int(m[1]) if m else pi+1
   assert len(texts)==4
   matches=list(re.finditer(r'^\s*(\d{1,2})\s*[.．]\s*',t,re.M))
   for j,m in enumerate(matches):
    end=matches[j+1].start() if j+1<len(matches) else len(t)
    q=t[m.end():end];q=re.split(r'\n\s*[“"※]?\s*채점기준',q)[0];q=re.sub(r'\n\s*\d+\s*[-–]\s*\d+\s*$','',q);q=re.sub(r'\s+',' ',q).strip()
    qs.append(dict(id=f"{s['round']}-{period}-{m[1]}",year=s['year'],round=s['round'],period=period,number=int(m[1]),question=q,source=s['url'],pdf_page=pi))
  (P/f"{s['round']}.txt").write_text('\n\f\n'.join(texts))
assert len(qs)==310,(len(qs))
assert len({q['id'] for q in qs})==310
for s in src:
 for period in range(1,5):
  assert [q['number'] for q in qs if q['round']==s['round'] and q['period']==period]==list(range(1,14 if period==1 else 7)),(s['round'],period)
(P/'questions.json').write_text(json.dumps(qs,ensure_ascii=False,indent=2))
print('Verified',len(qs),'questions');print('\n'.join(q['id']+' '+q['question'] for q in qs))
