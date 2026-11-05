"""X 원격 원문과 승인 원문의 정확한 대응. URL 조회·정규화·공개 판정은 하지 않는다.

공식 entities 필드 계약: https://docs.x.com/x-api/fundamentals/data-dictionary
인덱스 단위를 추측해 원문을 바꾸지 않는다. codepoint/UTF-16 경계 후보 각각에서
실제 URL 구간과 승인 전체 문자열이 모두 일치하는 경우만 증거로 허용한다.
"""
from collections.abc import Mapping
import hashlib
import re
from urllib.parse import urlsplit


def _text(value):
    if type(value) is not str or not value or len(value)>100000:return False
    try:value.encode('utf-8')
    except UnicodeError:return False
    return not any(ord(c)<32 and c not in '\n\r\t' or ord(c)==127 for c in value)


def _url(value):
    if not _text(value) or any(c.isspace() or c=='\\' for c in value):return False
    try:
        parsed=urlsplit(value)
        return parsed.scheme in ('http','https') and bool(parsed.hostname) and parsed.username is None and parsed.password is None
    except ValueError:return False


def safe_x_url(value,remote_id):
    if type(remote_id) is not str or re.fullmatch(r'[0-9]{1,64}',remote_id) is None:return None
    if not _url(value) or not value.isascii():return None
    try:
        parsed=urlsplit(value)
        if (parsed.scheme!='https' or parsed.netloc not in ('x.com','www.x.com','twitter.com','www.twitter.com')
                or parsed.query or parsed.fragment or '?' in value or '#' in value):return None
        if re.fullmatch(r'/(?:[A-Za-z0-9_]{1,15}/status|i/web/status)/'+re.escape(remote_id),parsed.path) is None:return None
        return value
    except ValueError:return None


def _spans(text,rows,utf16):
    boundaries={0:0};units=0
    for index,char in enumerate(text):
        units+=2 if utf16 and ord(char)>0xffff else 1
        boundaries[units]=index+1
    spans=[];last=0
    for row in rows:
        start,end=boundaries.get(row['start']),boundaries.get(row['end'])
        if start is None or end is None or start<last or text[start:end]!=row['url']:return None
        spans.append((start,end,row));last=end
    return spans


def _matches(text,spans,approved):
    offsets={0};previous=0
    for start,end,row in spans:
        literal=text[previous:start];next_offsets=set()
        # unwound_url은 최종 redirect 목적지일 수 있다. 같은 목적지라는 사실로
        # 게시 당시 입력한 서로 다른 URL을 동일한 원문으로 취급하지 않는다.
        options={row['expanded_url']}
        # 원문이 이미 같은 URL이면 원격 원문도 그대로 허용한다.
        options.add(row['url'])
        for offset in offsets:
            if not approved.startswith(literal,offset):continue
            offset+=len(literal)
            for option in options:
                if approved.startswith(option,offset):next_offsets.add(offset+len(option))
        offsets=next_offsets
        if not offsets:return False
        previous=end
    return any(approved[offset:]==text[previous:] for offset in offsets)


def reconstruct_x_text(remote_text,entities,approved_text):
    if not _text(remote_text) or not _text(approved_text) or not isinstance(entities,Mapping) or set(entities)-{'urls'}:return None
    rows=entities.get('urls',[])
    if type(rows) not in (list,tuple) or len(rows)>100:return None
    for row in rows:
        if (not isinstance(row,Mapping) or not {'start','end','url','expanded_url'}<=set(row)
                or set(row)-{'start','end','url','expanded_url','display_url','unwound_url'}
                or type(row['start']) is not int or type(row['end']) is not int
                or not 0<=row['start']<row['end']<=200000
                or not _url(row['url']) or not _url(row['expanded_url'])
                or 'unwound_url' in row and not _url(row['unwound_url'])
                or 'display_url' in row and not _text(row['display_url'])):return None
        if remote_text!=approved_text and re.fullmatch(r'https://t\.co/[A-Za-z0-9]+',row['url']) is None:return None
    rows=sorted(rows,key=lambda row:row['start'])
    accepted=False
    for utf16 in (False,True):
        spans=_spans(remote_text,rows,utf16)
        if spans is not None and _matches(remote_text,spans,approved_text):accepted=True
    if not accepted:return None
    return dict(text=approved_text,remote_text_sha256=hashlib.sha256(remote_text.encode()).hexdigest(),
        body_sha256=hashlib.sha256(approved_text.encode()).hexdigest())
