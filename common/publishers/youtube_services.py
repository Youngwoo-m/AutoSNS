"""YouTube의 실제 Google transport. import/조립은 외부 I/O를 하지 않는다."""
from datetime import datetime, timezone
from dataclasses import dataclass
import re
from collections.abc import Mapping
import hashlib
import io
from common.operations.runtime_models import utc


@dataclass(frozen=True)
class VerifiedYoutubeMedia:
    """서버 media_factory가 실제 원본 바이트를 검증한 뒤 만드는 SDK 미디어 봉투."""
    upload: object
    sha256: str
    size: int

    def __post_init__(self):
        if (self.upload is None or not isinstance(self.sha256, str)
                or re.fullmatch(r'[0-9a-f]{64}', self.sha256) is None
                or type(self.size) is not int or self.size <= 0):
            raise ValueError('invalid_verified_youtube_media')


def _bound_receipt(prepared, target):
    """실제 SDK에 전달할 입력의 식별자만 고정한다. 공개/원격 바이트 검증 증거는 아니다."""
    if not isinstance(prepared, Mapping) or not isinstance(target, Mapping):
        raise ValueError('invalid_youtube_binding')
    names=('connection_id','target_id','owner_account_id','destination_account_id','content_id','manifest_hash')
    identity={name:prepared[name] for name in names}
    for value in identity.values():
        if not isinstance(value,str) or not value or '\x00' in value or len(value)>2000:
            raise ValueError('invalid_youtube_binding')
        value.encode('utf-8')
    destination=identity['destination_account_id']
    if (identity['owner_account_id'] not in ('personal','dept') or destination not in ('personal','dept')
            or identity['connection_id'] != destination+'.youtube' or identity['target_id'] != target.get('target_id')
            or type(prepared['content_revision']) is not int or prepared['content_revision'] < 1):
        raise ValueError('invalid_youtube_binding')
    asset=prepared['asset']
    if (not isinstance(asset,Mapping) or not isinstance(asset.get('id'),str) or not asset['id']
            or '\x00' in asset['id'] or len(asset['id'])>2000 or asset.get('media_type')!='video/mp4'
            or not isinstance(asset.get('sha256'),str) or re.fullmatch(r'[0-9a-f]{64}',asset['sha256']) is None
            or type(asset.get('size')) is not int or asset['size']<=0):
        raise ValueError('invalid_youtube_binding')
    asset['id'].encode('utf-8')
    snippet=prepared['body']['snippet']
    title,description=snippet['title'],snippet['description']
    if not isinstance(title,str) or not title.strip() or not isinstance(description,str):
        raise ValueError('invalid_youtube_binding')
    return dict(kind='youtube_upload_receipt_v1',**identity,content_revision=prepared['content_revision'],
                asset_id=asset['id'],asset_sha256=asset['sha256'],asset_size=asset['size'],
                title_sha256=hashlib.sha256(title.encode('utf-8')).hexdigest(),
                description_sha256=hashlib.sha256(description.encode('utf-8')).hexdigest())


def _visibility(status):
    privacy = status.get('privacyStatus')
    if privacy == 'private' and status.get('publishAt'):
        try:
            utc(status['publishAt'])
            return 'scheduled'
        except Exception:
            pass
    return privacy


def _target_matches(observation, target):
    return (observation.get('authenticated') is True and observation.get('target_id') == target.get('target_id')
            and observation.get('login_subject') == target.get('target_id')
            and (not target.get('expected_login_subject') or observation['login_subject'] == target['expected_login_subject']))


class GoogleYoutubeServices:
    def __init__(self, service, *, media_factory, clock=None):
        self.service, self.media_factory = service, media_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def inspect(self, target):
        try:
            rows = self.service.channels().list(part='id,contentDetails', mine=True).execute().get('items', [])
            # 여러 채널·표시명으로 대상 선택을 추정하지 않는다.
            match = len(rows) == 1 and rows[0].get('id') == target.get('target_id') and bool(target.get('target_id'))
            subject = rows[0].get('id') if len(rows) == 1 else None
            observed = dict(platform='youtube', target_id=subject if match else None, login_subject=subject,
                            authenticated=bool(match), verification_method='immutable_channel_id',
                            status='ready' if match else 'needs_review')
            if not _target_matches(observed, target):
                observed.update(authenticated=False, target_id=None, status='needs_review')
            if observed['authenticated']:
                observed['uploads_playlist_id'] = (rows[0].get('contentDetails') or {}).get('relatedPlaylists', {}).get('uploads')
            return observed
        except Exception:
            return dict(platform='youtube', target_id=None, login_subject=None, authenticated=False,
                        verification_method='immutable_channel_id', status='needs_auth')

    def submit(self, prepared, target):
        try:
            receipt_binding = _bound_receipt(prepared, target)
            status = prepared['body']['status']
            if not isinstance(status, Mapping): raise ValueError('invalid_youtube_status')
        except Exception:
            return dict(outcome='failed', evidence=dict(reason='media_or_schedule_unavailable', confirmed_not_submitted=True))
        if not _target_matches(self.inspect(target), target):
            return dict(outcome='failed', evidence=dict(reason='target_unverified', confirmed_not_submitted=True))
        try:
            # 과거 publishAt는 YouTube가 즉시 공개로 해석하므로 I/O 직전에 다시 거절한다.
            if status.get('publishAt') and (status.get('privacyStatus') != 'private' or utc(status['publishAt']) <= utc(self.clock())):
                return dict(outcome='failed', evidence=dict(reason='schedule_not_future', confirmed_not_submitted=True))
            media = self.media_factory(prepared['asset'], prepared)
            verified_media = isinstance(media, VerifiedYoutubeMedia)
            if verified_media:
                # factory 이후에도 실제 전송 입력이 바뀌지 않았는지 재검증한다.
                if (_bound_receipt(prepared, target) != receipt_binding
                        or media.sha256 != receipt_binding['asset_sha256'] or media.size != receipt_binding['asset_size']):
                    raise ValueError('youtube_asset_changed')
                media = media.upload
            if status.get('publishAt') and utc(status['publishAt']) <= utc(self.clock()):
                return dict(outcome='failed', evidence=dict(reason='schedule_not_future', confirmed_not_submitted=True))
        except Exception:
            return dict(outcome='failed', evidence=dict(reason='media_or_schedule_unavailable', confirmed_not_submitted=True))
        try:
            request = self.service.videos().insert(part='snippet,status', body=prepared['body'], media_body=media)
            response = None
            while response is None:
                _, response = request.next_chunk(num_retries=0)
            remote_id = response.get('id')
            if not isinstance(remote_id, str) or not remote_id:
                return dict(outcome='unknown', evidence=dict(reason='remote_id_missing'))
            # ID 획득 후 추가 조회/후처리 I/O 없음. 응답의 실제 status만 예약 근거다.
            observed = response.get('status')
            if not isinstance(observed, Mapping): observed = {}
            evidence = dict(privacy=observed.get('privacyStatus'), visibility=_visibility(observed),
                publish_at=observed.get('publishAt'), upload_status=observed.get('uploadStatus'),
                schedule_confirmed=_visibility(observed) == 'scheduled',
                followup_intents=prepared.get('followup_intents', []),
                followup_completion='pending' if prepared.get('followup_intents') else 'not_required')
            if verified_media:
                evidence['upload_receipt'] = dict(receipt_binding, remote_id=remote_id)
            result = dict(outcome='submitted', remote_id=remote_id, url='https://www.youtube.com/watch?v=' + remote_id, evidence=evidence)
            if evidence['schedule_confirmed']:
                try:
                    result.update(outcome='scheduled', scheduled_at=utc(observed['publishAt']).isoformat())
                except Exception:
                    evidence.update(schedule_confirmed=False, reason='invalid_remote_schedule')
            return result
        except Exception:
            # 같은 request를 새 insert로 재구성하지 않는다. 다음 작업은 읽기 조회다.
            return dict(outcome='unknown', evidence=dict(reason='youtube_submission_uncertain',
                        followup_intents=prepared.get('followup_intents', [])))

    def read_video(self, target, remote_id):
        if not isinstance(remote_id, str) or not remote_id or not _target_matches(self.inspect(target), target): return None
        rows = self.service.videos().list(part='snippet,status,contentDetails,processingDetails', id=remote_id).execute().get('items', [])
        return rows[0] if len(rows) == 1 else None

    def read_statistics(self, target, remote_id):
        """인증된 고정 채널의 공개 영상 하나만 읽는다. 업로드·목록 스캔·후처리 없음."""
        if (not isinstance(target, Mapping) or not isinstance(remote_id, str)
                or not remote_id.strip() or '\x00' in remote_id
                or not _target_matches(self.inspect(target), target)):
            return None
        rows = self.service.videos().list(part='snippet,status,statistics', id=remote_id).execute().get('items', [])
        if not isinstance(rows, list) or len(rows) != 1 or not isinstance(rows[0], Mapping):
            return None
        row = rows[0]
        snippet, status = row.get('snippet'), row.get('status')
        if (row.get('id') != remote_id or not isinstance(snippet, Mapping)
                or snippet.get('channelId') != target.get('target_id')
                or not isinstance(status, Mapping) or status.get('privacyStatus') != 'public'):
            return None
        return row

    def lookup(self, target, attempt):
        remote_id = attempt.get('remote_id') or (attempt.get('result') or {}).get('remote_id')
        if remote_id:
            row = self.read_video(target, remote_id)
            return [row] if row else []
        observed = self.inspect(target)
        if not _target_matches(observed, target) or not observed.get('uploads_playlist_id'): return []
        # API로 받은 uploads 목록만 사용한다. 한 페이지 부재는 재발행 허가가 아니다.
        rows = self.service.playlistItems().list(part='contentDetails', playlistId=observed['uploads_playlist_id'], maxResults=50).execute().get('items', [])
        ids = [row.get('contentDetails', {}).get('videoId') for row in rows]
        ids = list(dict.fromkeys(item for item in ids if isinstance(item, str) and item))
        if not ids: return []
        return self.service.videos().list(part='snippet,status,contentDetails,processingDetails', id=','.join(ids)).execute().get('items', [])


def observation(raw, context):
    snippet, status = raw.get('snippet') or {}, raw.get('status') or {}
    # contentDetails.duration와 transcoded asset는 원본 바이트 해시의 증거가 아니다.
    return dict(remote_id=raw.get('id'), target_id=snippet.get('channelId'),
        destination_account_id=context['destination_account_id'], title=snippet.get('title'),
        description=snippet.get('description'), created_at=snippet.get('publishedAt'),
        privacy=status.get('privacyStatus'), visibility=_visibility(status), publish_at=status.get('publishAt'),
        upload_status=status.get('uploadStatus'), processing_status=(raw.get('processingDetails') or {}).get('processingStatus'),
        duration=(raw.get('contentDetails') or {}).get('duration'), media_sha256=None)


def create_youtube_services(connection_id, credentials, *, media_loader):
    if connection_id not in ('dept.youtube', 'personal.youtube') or credentials is None:
        raise ValueError('youtube_credentials_required')
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
    service = build('youtube', 'v3', credentials=credentials, cache_discovery=False)
    def media_factory(asset, prepared):
        metadata, raw = media_loader(prepared['content_id'], prepared['content_revision'], asset['id'])
        if (metadata.get('sha256') != asset['sha256'] or len(raw) != asset['size'] or
            hashlib.sha256(raw).hexdigest() != asset['sha256']): raise ValueError('youtube_asset_changed')
        upload = MediaIoBaseUpload(io.BytesIO(raw), mimetype='video/mp4', chunksize=-1, resumable=True)
        return VerifiedYoutubeMedia(upload, hashlib.sha256(raw).hexdigest(), len(raw))
    return GoogleYoutubeServices(service, media_factory=media_factory)
