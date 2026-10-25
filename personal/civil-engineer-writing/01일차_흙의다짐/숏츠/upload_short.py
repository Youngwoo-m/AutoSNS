import argparse,json,sys,time
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT=Path(__file__).resolve().parent
AUTO=ROOT.parents[2]/'youtube-shorts-auto'
sys.path.insert(0,str(AUTO))
from youtube_upload import _creds

p=argparse.ArgumentParser();p.add_argument('phase',choices=['upload','publish','check']);args=p.parse_args()
y=build('youtube','v3',credentials=_creds(str(AUTO/'token_youtube_geoai.json')),cache_discovery=False)
channel=y.channels().list(part='snippet,contentDetails',mine=True).execute()['items'][0]
assert channel['id']=='UCbHDlxMFIackeJRwW2iTYew'
result=ROOT/'youtube-result.json'
if args.phase=='upload':
 qa=json.loads((ROOT/'verification.json').read_text())
 assert qa['duration']<=20 and qa['visual_qa_verified'] and qa['audio_qa_verified'] and qa['complete_decode_verified']
 if not result.exists():
  assert not (ROOT/'upload-session.json').exists(),'Uncertain upload: inspect channel before retry'
  meta=json.loads((ROOT/'youtube-metadata.json').read_text())
  recent=y.playlistItems().list(part='snippet',playlistId=channel['contentDetails']['relatedPlaylists']['uploads'],maxResults=30).execute().get('items',[])
  assert not any(x['snippet']['title']==meta['snippet']['title'] for x in recent),'Duplicate title exists; inspect channel'
  req=y.videos().insert(part='snippet,status',body=meta,media_body=MediaFileUpload(str(ROOT/'civil-day01-short.mp4'),chunksize=8*1024*1024,resumable=True))
  response=None
  while response is None:
   progress,response=req.next_chunk()
   if req.resumable_uri:(ROOT/'upload-session.json').write_text(json.dumps({'uri':req.resumable_uri}))
  result.write_text(json.dumps(response,ensure_ascii=False,indent=2)+'\n')
 data=json.loads(result.read_text());print('uploaded_private',data['id'],flush=True)
else:
 vid=json.loads(result.read_text())['id']
 data=y.videos().list(part='snippet,status,contentDetails,processingDetails',id=vid).execute()['items'][0]
 assert data['snippet']['channelId']==channel['id']
 if args.phase=='publish':
  assert data['processingDetails']['processingStatus']=='succeeded',data['processingDetails']
  status=data['status'];status.update(privacyStatus='public',selfDeclaredMadeForKids=False,containsSyntheticMedia=True)
  y.videos().update(part='status',body={'id':vid,'status':{k:status[k] for k in ['privacyStatus','selfDeclaredMadeForKids','containsSyntheticMedia']}}).execute()
  data=y.videos().list(part='snippet,status,contentDetails',id=vid).execute()['items'][0]
  assert data['status']['privacyStatus']=='public'
 (ROOT/'youtube-verified.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'id':vid,'url':'https://www.youtube.com/shorts/'+vid,'title':data['snippet']['title'],'privacy':data['status']['privacyStatus'],'duration':data['contentDetails']['duration'],'processing':data.get('processingDetails',{}).get('processingStatus')},ensure_ascii=False),flush=True)
