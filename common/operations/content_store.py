"""불변 파일 스냅숏과 CAS 포인터로 관리하는 콘텐츠 저장소."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

from .database import initialize_database, connect_database

MAX_JSON_BYTES = 1024 * 1024
MAX_ASSET_BYTES = 100 * 1024 * 1024
MAX_CONTENT_ASSET_BYTES = 500 * 1024 * 1024
ACCOUNTS = {'personal','dept'}
PLATFORMS = {'youtube','tiktok','instagram','threads','x','facebook','tistory','naver_blog','blogger','homepage','kakao'}
EDIT_FIELDS = {'title','kind','series','status','original','variants','sources'}

class StoreError(Exception):
    def __init__(self, code, message=None):
        self.code=code
        super().__init__(message or code)

class ConflictError(StoreError):
    def __init__(self, message=None): super().__init__('conflict',message)

def _json(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def _hash(data): return hashlib.sha256(data).hexdigest()
def _now(): return datetime.now(timezone.utc).isoformat()
def _invalid(): raise StoreError('invalid')
def _string(value, limit):
    if not isinstance(value,str) or len(value)>limit: _invalid()
    try: value.encode('utf-8')
    except UnicodeError: _invalid()
    return value

def _revision(value):
    if type(value) is not int or value<1: _invalid()


def _payload(payload):
    if not isinstance(payload,dict) or set(payload)-EDIT_FIELDS or not {'title','kind'}<=set(payload): _invalid()
    try:
        if len(_json(payload).encode())>MAX_JSON_BYTES: raise StoreError('too_large')
    except (ValueError,TypeError,UnicodeError,RecursionError): _invalid()
    result={'title':_string(payload['title'],300),'kind':payload['kind'],
            'series':_string(payload.get('series',''),300), 'status':payload.get('status','idea'),
            'original':_string(payload.get('original',''),200000),
            'variants':payload.get('variants',[]),'sources':payload.get('sources',[])}
    if not result['title'].strip() or result['kind'] not in ('article','card','short','video') or result['status'] not in ('idea','drafting','production','review','archived'): _invalid()
    if not isinstance(result['variants'],list) or len(result['variants'])>30: _invalid()
    seen=set()
    for v in result['variants']:
        if not isinstance(v,dict) or set(v)!={'destination_account_id','platform','text'}: _invalid()
        if v['destination_account_id'] not in ('personal','dept') or v['platform'] not in tuple(PLATFORMS): _invalid()
        _string(v['text'],200000)
        key=(v['destination_account_id'],v['platform'])
        if key in seen: _invalid()
        seen.add(key)
    if not isinstance(result['sources'],list) or len(result['sources'])>100: _invalid()
    for source in result['sources']:
        if not isinstance(source,dict) or set(source)!={'url','note'}: _invalid()
        _string(source['url'],200000); _string(source['note'],2000)
        try: parsed=urlsplit(source['url'])
        except ValueError: _invalid()
        if parsed.scheme not in ('http','https') or not parsed.netloc or not parsed.hostname: _invalid()
    return json.loads(_json(result))


class ContentStore:
    def __init__(self,root:Path):
        self.root=Path(root).absolute()
        self._initialized=False

    def _path(self,relative):
        path=self.root / relative
        if self.root.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):
            raise StoreError('storage_error','Unsafe storage path')
        # Reject symlinks even when they currently point inside the root.
        current=path
        while current!=self.root:
            if current.is_symlink(): raise StoreError('storage_error','Symlink in storage path')
            current=current.parent
        return path

    @contextmanager
    def _db(self,writable=False):
        if writable and not self._initialized: raise StoreError('storage_error','initialize() required')
        conn=None
        try:
            conn=connect_database(self.root,writable=writable)
            yield conn
        except StoreError: raise
        except (OSError,sqlite3.Error,ValueError,UnicodeError) as exc:
            raise StoreError('storage_error') from exc
        finally:
            if conn is not None: conn.close()

    def initialize(self):
        try: initialize_database(self.root)
        except (OSError,sqlite3.Error) as exc: raise StoreError('storage_error') from exc
        self._initialized=True

    def _exists(self): return self._path('operations.sqlite3').is_file()

    def _snapshot(self,conn,content_id,revision=None):
        if revision is None:
            row=conn.execute('SELECT r.* FROM contents c JOIN revisions r ON r.content_id=c.id AND r.revision=c.current_revision WHERE c.id=?',(content_id,)).fetchone()
        else:
            row=conn.execute('SELECT * FROM revisions WHERE content_id=? AND revision=?',(content_id,revision)).fetchone()
        if row is None: return None
        try:
            raw=self._path(row['file_path']).read_bytes()
            data=json.loads(raw)
            if raw!=_json(data).encode() or _hash(raw)!=row['manifest_hash'] or _json(data)!=row['snapshot']: raise StoreError('storage_error','Snapshot integrity failure')
        except (OSError,ValueError,TypeError,UnicodeError) as exc: raise StoreError('storage_error') from exc
        return row,data

    def _result(self,conn,row,data):
        content=conn.execute('SELECT created_at FROM contents WHERE id=?',(row['content_id'],)).fetchone()
        reviews=[dict(r) for r in conn.execute('SELECT id,revision,manifest_hash,kind,decision,notes,method,created_at FROM reviews WHERE content_id=? AND revision=? ORDER BY created_at,id',(row['content_id'],row['revision']))]
        return {**data,'id':row['content_id'],'source':'managed','revision':row['revision'],'manifest_hash':row['manifest_hash'],'reviews':reviews,'created_at':content['created_at'],'updated_at':row['created_at']}

    def get(self,content_id,revision=None):
        if revision is not None: _revision(revision)
        if not isinstance(content_id,str): _invalid()
        if not self._exists(): return None
        with self._db() as conn:
            found=self._snapshot(conn,content_id,revision)
            return self._result(conn,*found) if found else None

    def list(self,account='all'):
        if account not in ('all','personal','dept'): _invalid()
        if not self._exists(): return []
        with self._db() as conn:
            items=[]
            for row in conn.execute('SELECT id FROM contents ORDER BY updated_at DESC,id').fetchall():
                found=self._snapshot(conn,row['id'])
                item=self._result(conn,*found)
                if account=='all' or item['owner_account_id']==account or any(v['destination_account_id']==account for v in item['variants']): items.append(item)
            return items

    def list_revisions(self,content_id):
        if not isinstance(content_id,str): _invalid()
        if not self._exists(): return []
        with self._db() as conn:
            return [dict(r) for r in conn.execute('SELECT revision,manifest_hash,created_at FROM revisions WHERE content_id=? ORDER BY revision',(content_id,))]

    def _read_asset(self,conn,content_id,revision,asset_id):
        found=self._snapshot(conn,content_id,revision)
        if not found: raise StoreError('not_found')
        row,data=found
        asset=next((a for a in data['assets'] if a['id']==asset_id),None)
        if asset is None: raise StoreError('not_found')
        try: raw=self._path(Path(row['file_path']).parent/asset_id).read_bytes()
        except OSError as exc: raise StoreError('storage_error') from exc
        if len(raw)!=asset['size'] or _hash(raw)!=asset['sha256']: raise StoreError('storage_error','Asset integrity failure')
        return asset,raw

    def read_asset(self,content_id,revision,asset_id):
        _revision(revision)
        if not isinstance(content_id,str) or not isinstance(asset_id,str): _invalid()
        if not self._exists(): raise StoreError('not_found')
        with self._db() as conn: return self._read_asset(conn,content_id,revision,asset_id)

    def create(self,owner_account_id,payload):
        if owner_account_id not in ('personal','dept'): _invalid()
        data={**_payload(payload),'owner_account_id':owner_account_id,'assets':[]}
        return self._save('managed_'+uuid4().hex,None,data,{})

    def update(self,content_id,expected_revision,payload):
        _revision(expected_revision)
        edits=_payload(payload)
        with self._db() as conn:
            found=self._snapshot(conn,content_id)
            if not found: raise StoreError('not_found')
            row,old=found
            if row['revision']!=expected_revision: raise ConflictError()
            assets={a['id']:self._read_asset(conn,content_id,expected_revision,a['id'])[1] for a in old['assets']}
        return self._save(content_id,expected_revision,{**edits,'owner_account_id':old['owner_account_id'],'assets':old['assets']},assets)

    def add_asset(self,content_id,expected_revision,filename,media_type,data):
        _revision(expected_revision)
        _string(filename,200)
        if not filename or any(c in filename for c in ('/','\\','\x00','\r','\n')): _invalid()
        if not isinstance(data,bytes): _invalid()
        if len(data)>MAX_ASSET_BYTES: raise StoreError('too_large')
        suffix=Path(filename).suffix.lower()
        valid=False
        if media_type=='image/png': valid=suffix=='.png' and data.startswith(b'\x89PNG\r\n\x1a\n')
        elif media_type=='image/jpeg': valid=suffix in ('.jpg','.jpeg') and data.startswith(b'\xff\xd8\xff')
        elif media_type=='image/webp': valid=suffix=='.webp' and data[:4]==b'RIFF' and data[8:12]==b'WEBP'
        elif media_type=='video/mp4': valid=suffix=='.mp4' and len(data)>=12 and data[4:8]==b'ftyp' and int.from_bytes(data[:4],'big')>=12
        elif media_type=='audio/mpeg': valid=suffix=='.mp3' and (data.startswith(b'ID3') or (len(data)>=2 and data[0]==255 and data[1]&224==224))
        elif media_type=='audio/wav': valid=suffix=='.wav' and data[:4]==b'RIFF' and data[8:12]==b'WAVE'
        if not valid: raise StoreError('unsupported_media')
        with self._db() as conn:
            found=self._snapshot(conn,content_id)
            if not found: raise StoreError('not_found')
            row,old=found
            if row['revision']!=expected_revision: raise ConflictError()
            unique={}
            for r in conn.execute('SELECT snapshot FROM revisions WHERE content_id=?',(content_id,)):
                for a in json.loads(r['snapshot'])['assets']: unique[a['id']]=a['size']
            if sum(unique.values())+len(data)>MAX_CONTENT_ASSET_BYTES: raise StoreError('too_large')
            asset_data={a['id']:self._read_asset(conn,content_id,expected_revision,a['id'])[1] for a in old['assets']}
        asset={'id':'asset_'+uuid4().hex,'filename':filename,'media_type':media_type,'size':len(data),'sha256':_hash(data)}
        asset_data[asset['id']]=data
        old['assets'].append(asset)
        return self._save(content_id,expected_revision,old,asset_data)

    def _save(self,content_id,expected_revision,data,asset_data):
        if not self._initialized: raise StoreError('storage_error','initialize() required')
        revision=1 if expected_revision is None else expected_revision+1
        request_id=uuid4().hex
        staged=self._path(Path('.staging')/request_id)
        final=self._path(Path(data['owner_account_id'])/'content'/content_id/'revisions'/str(revision)/request_id)
        moved=False
        try:
            staged.mkdir(parents=True,exist_ok=False)
            raw=_json(data).encode(); digest=_hash(raw)
            for asset in data['assets']:
                value=asset_data[asset['id']]
                if len(value)!=asset['size'] or _hash(value)!=asset['sha256']: raise StoreError('storage_error')
                (staged/asset['id']).write_bytes(value)
            (staged/'manifest.json').write_bytes(raw)
            # Durability before the pointer becomes visible, including all asset bytes.
            for file in staged.iterdir():
                with file.open('rb') as handle: os.fsync(handle.fileno())
            with self._db(writable=True) as conn:
                conn.execute('BEGIN IMMEDIATE')
                try:
                    current=conn.execute('SELECT current_revision FROM contents WHERE id=?',(content_id,)).fetchone()
                    if expected_revision is None:
                        if current is not None: raise ConflictError()
                    elif current is None: raise StoreError('not_found')
                    elif current['current_revision']!=expected_revision: raise ConflictError()
                    final=self._path(final.relative_to(self.root))
                    final.parent.mkdir(parents=True,exist_ok=True)
                    if final.exists(): raise StoreError('storage_error')
                    staged.rename(final); moved=True
                    timestamp=_now()
                    if expected_revision is None:
                        conn.execute('INSERT INTO contents VALUES(?,?,?,?,?)',(content_id,data['owner_account_id'],revision,timestamp,timestamp))
                    conn.execute('INSERT INTO revisions VALUES(?,?,?,?,?,?)',(content_id,revision,digest,raw.decode(),str((final/'manifest.json').relative_to(self.root)),timestamp))
                    if expected_revision is not None:
                        changed=conn.execute('UPDATE contents SET current_revision=?,updated_at=? WHERE id=? AND current_revision=?',(revision,timestamp,content_id,expected_revision)).rowcount
                        if changed!=1: raise ConflictError()
                    conn.execute('INSERT INTO events(content_id,revision,kind,created_at) VALUES(?,?,?,?)',(content_id,revision,'created' if expected_revision is None else 'revised',timestamp))
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise
                result=self._result(conn,*self._snapshot(conn,content_id,revision))
            return result
        except StoreError: raise
        except (OSError,sqlite3.Error,ValueError,KeyError,TypeError) as exc: raise StoreError('storage_error') from exc
        finally:
            # UUID ownership means cleanup cannot remove another writer's files.
            if staged.exists(): shutil.rmtree(staged,ignore_errors=True)
            if moved:
                # Keep committed paths; only our own unreferenced request may be removed.
                try:
                    with self._db() as conn:
                        referenced=conn.execute('SELECT 1 FROM revisions WHERE file_path=?',(str((final/'manifest.json').relative_to(self.root)),)).fetchone()
                    if not referenced: shutil.rmtree(final,ignore_errors=True)
                except StoreError:
                    pass  # An orphan is safer than deleting a possibly committed snapshot.

    def record_review(self,content_id,revision,manifest_hash,kind,decision,notes):
        _revision(revision); _string(notes,10000)
        if kind not in ('calculation','source','general') or decision not in ('pass','changes_requested'): _invalid()
        if not isinstance(manifest_hash,str) or not re.fullmatch('[0-9a-f]{64}',manifest_hash): _invalid()
        with self._db(writable=True) as conn:
            conn.execute('BEGIN IMMEDIATE')
            try:
                found=self._snapshot(conn,content_id,revision)
                if not found: raise StoreError('not_found')
                if found[0]['manifest_hash']!=manifest_hash: raise ConflictError()
                review={'id':'review_'+uuid4().hex,'revision':revision,'manifest_hash':manifest_hash,'kind':kind,'decision':decision,'notes':notes,'method':'manual','created_at':_now()}
                conn.execute('INSERT INTO reviews VALUES(?,?,?,?,?,?,?,?,?)',(review['id'],content_id,revision,manifest_hash,kind,decision,notes,'manual',review['created_at']))
                conn.commit()
            except BaseException:
                conn.rollback(); raise
        return review
