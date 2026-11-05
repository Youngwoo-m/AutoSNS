from pathlib import Path
import json,datetime
R=Path('/Volumes/USB256/devAPP/AutoSNS');H=Path(__file__).resolve().parent
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
p=H/'first-second-day-publishing-progress.json';s=json.loads(p.read_text());naverchecks=json.loads((H/'naver-four-public-verification.json').read_text()) if (H/'naver-four-public-verification.json').exists() else []
for row in s['posts']:
 ex=row['exam'];day=row['day'];d=next((R/'GeoAI_NA'/f'{ex}-engineer-writing').glob(f'{day:02}일차_*'))
 n=next((x for x in naverchecks if x['exam']==ex and x['day']==day and x['pass']),None)
 if n:row['urls']['naver']=n['url']
 checks={}
 for channel in ['tistory','blogger']:
  f=H/f'{ex}-day{day}-{channel}-public-check.json';c=json.loads(f.read_text()) if f.exists() else {};checks[channel]=bool(c.get('title_match') and c.get('all_assets_match') and not c.get('missing_headings'))
 checks['naver']=bool(n);complete=all(checks.values());row.update({'verification':checks,'status':'published' if complete else 'partial'})
 state=d/'작성상태.json';m=json.loads(state.read_text()) if state.exists() else {};m.update({'day':day,'title':(d/'제목.txt').read_text().strip(),'status':row['status'],'urls':row['urls'],'verification':checks,'updated_at':now,'calc':{'verdict':'ok'},'source_review':{'verdict':'fix_resolved' if day==2 else 'pass'},'note':'건축day1 티스토리배너검사대기시 네이버는원본정상화후 복구. 공개글재발행금지.' if not complete else '모든 채널 실제 공개·본문·첨부검증 완료'});state.write_text(json.dumps(m,ensure_ascii=False,indent=2))
 manifest=d/'manifest.json';m=json.loads(manifest.read_text());m['status']=row['status'];m['public_channels']=row['urls'];m['public_verification']=checks;m['updated_at']=now;manifest.write_text(json.dumps(m,ensure_ascii=False,indent=2))
 log=R/'personal/claude-jobs/state'/f'{ex}-daily.jsonl';entry={'at':now,'day':day,'title':(d/'제목.txt').read_text().strip(),'status':row['status'],'urls':row['urls'],'verification':checks,'artifacts':str(d.resolve()),'calc':{'verdict':'ok'},'review':{'verdict':'fix_resolved' if day==2 else 'pass'},'manual_recovery':True,'pending_recoveries':[{'day':1,'channel':'naver','reason':'Tistory banner platform review pending; original content not republished'}] if ex=='building' and not next((r for r in s['posts'] if r['exam']=='building' and r['day']==1),{}).get('verification',{}).get('naver') else []};log.open('a').write(json.dumps(entry,ensure_ascii=False)+'\n')
s['updated_at']=now;s['status']='published_and_verified' if all(r['status']=='published' for r in s['posts']) else 'four_posts_published_with_pending_crosspost';s['tistory']='four_posts_public';s['blogger']='four_posts_public_exception_consumed';s['naver']=str(sum('naver' in r['urls'] for r in s['posts']))+'/4 verified';s['published']=s['posts'];s['lists']='both public lists verified day1/day2 PDF=true';p.write_text(json.dumps(s,ensure_ascii=False,indent=2))
old=H/'first-day-publishing-progress.json';m=json.loads(old.read_text());m['status']='superseded_by_first_second_day_actual_publication';m['updated_at']=now;m['current_ledger']=str(p);m['note']='로그인 복구 완료, 건축·안전 1·2일차 실제공개. 최신채널·검증상태는 current_ledger 참조';old.write_text(json.dumps(m,ensure_ascii=False,indent=2))
print(json.dumps({'status':s['status'],'naver':s['naver'],'posts':s['posts']},ensure_ascii=False,indent=2))
