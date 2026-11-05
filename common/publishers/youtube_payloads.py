"""승인 snapshot의 순수 YouTube 변환. 파일·토큰·legacy 설정을 읽지 않는다."""
from collections.abc import Mapping
import hashlib
from common.operations.runtime_models import utc

FOLLOWUPS = ('thumbnail', 'playlist', 'comment', 'caption', 'public_switch', 'tiktok')


def _strings(values):
    if not isinstance(values, (tuple, list)) or any(not isinstance(value, str) for value in values):
        raise ValueError('invalid_youtube_tags')
    return list(dict.fromkeys(value.strip().lstrip('#') for value in values if value.strip()))


def _sanitize(text):
    return text.replace('<', '〈').replace('>', '〉')


def build_youtube_payload(snapshot, context, config_view=None):
    if (context.platform != 'youtube' or not isinstance(snapshot, Mapping) or
        snapshot.get('revision') != context.content_revision or snapshot.get('manifest_hash') != context.manifest_hash or
        snapshot.get('id', context.content_id) != context.content_id or
        snapshot.get('owner_account_id', context.owner_account_id) != context.owner_account_id):
        raise ValueError('content_changed')
    # config_view는 호출자가 승인한 고정 view다. adapter는 context.options 안의 view만 전달한다.
    cfg = config_view or {}
    if not isinstance(cfg, Mapping) or not isinstance(cfg.get('youtube', {}), Mapping):
        raise ValueError('invalid_youtube_config')
    ycfg, options = cfg.get('youtube', {}), context.options
    title = snapshot.get('title')
    variants = snapshot.get('variants', ())
    if not isinstance(variants, (tuple, list)) or any(not isinstance(item, Mapping) for item in variants):
        raise ValueError('invalid_youtube_content')
    selected = [item for item in variants if item.get('destination_account_id') == context.destination_account_id and item.get('platform') == 'youtube']
    if len(selected) > 1: raise ValueError('ambiguous_youtube_variant')
    text = selected[0].get('text') if selected else snapshot.get('original')
    if not isinstance(title, str) or not title.strip() or not isinstance(text, str) or not text.strip():
        raise ValueError('invalid_youtube_content')
    title = title.strip()
    prefix, suffix = ycfg.get('title_prefix', ''), ycfg.get('title_suffix', '')
    if not isinstance(prefix, str) or not isinstance(suffix, str) or len(prefix) > 90 or len(suffix) > 90:
        raise ValueError('invalid_youtube_title')
    if prefix.strip() and not title.startswith(prefix.strip()): title = prefix.strip() + ' ' + title
    if suffix.strip() and not title.endswith(suffix.strip()): title = title[:99 - len(suffix.strip())].rstrip() + ' ' + suffix.strip()
    title = _sanitize(title)[:100]
    parts = [text.strip()]
    footer = ycfg.get('seo_footer', '')
    if not isinstance(footer, str): raise ValueError('invalid_youtube_description')
    if footer.strip(): parts.extend(('', footer.strip()))
    playlists = ycfg.get('playlists', {})
    labels = ycfg.get('playlist_labels', {})
    kind = options.get('playlist_kind', 'news')
    if playlists.get(kind):
        parts.extend(('', f"▶ {labels.get(kind, '지난 편 몰아보기')}: https://www.youtube.com/playlist?list={playlists[kind]}"))
    if ycfg.get('homepage_url'):
        parts.extend(('', str(ycfg.get('homepage_label', '홈페이지')) + ': ' + ycfg['homepage_url']))
    for item in ycfg.get('channel_links', ()):
        if not isinstance(item, Mapping): raise ValueError('invalid_youtube_description')
        if item.get('url'): parts.append(str(item.get('label', '')) + ': ' + item['url'])
    notice = options.get('ai_notice', snapshot.get('ai_notice', ''))
    if not isinstance(notice, str): raise ValueError('invalid_youtube_description')
    if notice: parts.extend(('', notice))
    sources = snapshot.get('sources', ())
    if not isinstance(sources, (tuple, list)): raise ValueError('invalid_youtube_sources')
    for source in sources:
        if not isinstance(source, Mapping) or not isinstance(source.get('url'), str): raise ValueError('invalid_youtube_sources')
        if ycfg.get('include_sources', True):
            parts.extend((str(source.get('note', '출처')), source['url']))
    hashtags = _strings(options.get('tags', snapshot.get('tags', ())))
    tags = _strings(hashtags + _strings(cfg.get('hashtags', ())) + _strings(cfg.get('local_tags', ())))
    if not any(tag.lower() == 'shorts' for tag in tags): tags.insert(0, 'Shorts')
    if options.get('bgm_credit'): parts.extend(('', options['bgm_credit']))
    parts.extend(('', ' '.join('#' + tag for tag in tags)))
    description = _sanitize('\n'.join(parts).strip())
    if len(description) > 5000: raise ValueError('youtube_description_too_large')
    keywords, total = [], 0
    for tag in _strings([tag for tag in hashtags if tag.lower() != 'shorts'] + _strings(cfg.get('local_tags', ())) + _strings(ycfg.get('seo_keywords', ()))):
        if total + len(tag) + 1 > 460: break
        keywords.append(tag); total += len(tag) + 1
    assets = snapshot.get('assets', ())
    if not isinstance(assets, (tuple, list)) or any(not isinstance(a, Mapping) for a in assets): raise ValueError('invalid_youtube_asset')
    videos = [a for a in assets if a.get('media_type') == 'video/mp4']
    if len(videos) != 1: raise ValueError('youtube_video_required')
    asset = videos[0]
    if (not isinstance(asset.get('id'), str) or not asset['id'] or not isinstance(asset.get('sha256'), str) or
        len(asset['sha256']) != 64 or any(c not in '0123456789abcdef' for c in asset['sha256']) or
        type(asset.get('size')) is not int or asset['size'] <= 0): raise ValueError('invalid_youtube_asset')
    visibility = options.get('visibility', 'private')  # 승인 없는 공개 기본값 없음
    if visibility not in ('public', 'private', 'unlisted'): raise ValueError('invalid_youtube_visibility')
    status = dict(privacyStatus=visibility, selfDeclaredMadeForKids=False)
    synthetic = options.get('contains_synthetic_media', bool(notice))
    if type(synthetic) is not bool: raise ValueError('invalid_youtube_synthetic_flag')
    if synthetic: status['containsSyntheticMedia'] = True
    condition = context.schedule_condition
    if condition and condition.get('kind') not in ('immediate', 'fixed'): raise ValueError('youtube_schedule_unsupported')
    if condition.get('kind') == 'fixed':
        status['privacyStatus'] = 'private'
        status['publishAt'] = utc(condition.get('at')).isoformat()
    actions = options.get('followup_intents', ())
    if not isinstance(actions, (tuple, list)) or any(action not in FOLLOWUPS for action in actions): raise ValueError('invalid_youtube_followup')
    actions = list(dict.fromkeys(actions))
    if ycfg.get('thumbnail') is True and 'thumbnail' not in actions: actions.append('thumbnail')
    if (ycfg.get('playlist_default') or playlists.get(kind) or ycfg.get('playlist_rules')) and 'playlist' not in actions: actions.append('playlist')
    auto_comment = ycfg.get('auto_comment', {})
    if isinstance(auto_comment, Mapping) and auto_comment.get('enabled') is True and 'comment' not in actions:
        actions.append('comment')
    return dict(platform='youtube', connection_id=context.connection_id, target_id=context.target_id,
        owner_account_id=context.owner_account_id, destination_account_id=context.destination_account_id,
        content_id=context.content_id, content_revision=context.content_revision, manifest_hash=context.manifest_hash,
        body_text=text, body_sha256=hashlib.sha256(text.encode()).hexdigest(),
        body=dict(snippet=dict(title=title, description=description, tags=keywords,
                              categoryId=str(ycfg.get('category_id', '25')), defaultLanguage='ko', defaultAudioLanguage='ko'), status=status),
        asset={key: asset[key] for key in ('id', 'sha256', 'size', 'media_type')},
        followup_intents=[dict(action=action, state='not_started', required=True, separate_approval_required=True) for action in actions])
