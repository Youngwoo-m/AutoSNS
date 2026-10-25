from pathlib import Path
import json,re,urllib.request,urllib.parse,concurrent.futures
P=Path(__file__).resolve().parent
old=Path('/Volumes/USB256/devAPP/AutoSNS/GeoAI_NA/reference-posts/2026-10-09-five-years')
info=json.loads((old/'출처와검산.json').read_text())
def fetch(pair):
 rnd,url=pair;s=urllib.request.urlopen(url,timeout=45).read().decode('utf-8','replace');(P/f'{rnd}-source.html').write_text(s)
 m=re.search(r"fileDown\('([^']+)',\s*'([^']+)',\s*'([^']+)'\s*,\s*'([^']+)'",s);assert m,(rnd,'no attachment')
 fp,fn,fs,art=m.groups();assert '측량' in fn and '지형공간정보' in fn,fn
 u='https://www.q-net.or.kr/cst006.do?'+urllib.parse.urlencode(dict(id='cst00602s01',gSite='Q',gId='',fileCode='R001',filePath=fp,fileName=fn,fileSeq=fs,artlSeq=art,href=0))
 b=urllib.request.urlopen(u,timeout=60).read();assert b.startswith(b'%PDF'),(rnd,b[:30]);(P/f'{rnd}.pdf').write_bytes(b)
 return dict(round=int(rnd),year=int(info['dates'][rnd][:4]),date=info['dates'][rnd],url=url,file_name=fn,bytes=len(b),download_url=u)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as e:rows=list(e.map(fetch,info['urls'].items()))
(P/'sources.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print([(r['round'],r['bytes']) for r in rows])
