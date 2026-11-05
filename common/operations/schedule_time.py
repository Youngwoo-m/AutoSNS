"""오프셋과 지역 시간대가 일치하는 확정 시각만 받는다."""
from datetime import datetime, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from .models import ContractError


def normalize_schedule(value: str, timezone: str = 'Asia/Seoul') -> str:
    try:
        if not isinstance(value, str) or not isinstance(timezone, str):
            raise ValueError()
        supplied = datetime.fromisoformat(value)
        if supplied.tzinfo is None or supplied.utcoffset() is None:
            raise ValueError()
        zone = ZoneInfo(timezone)
        wall = supplied.replace(tzinfo=None)
        candidates = []
        for fold in (0, 1):
            local = wall.replace(tzinfo=zone, fold=fold)
            utc = local.astimezone(dt_timezone.utc)
            if utc.astimezone(zone).replace(tzinfo=None) == wall:
                if utc not in candidates:
                    candidates.append(utc)
        if len(candidates) != 1 or candidates[0] != supplied.astimezone(dt_timezone.utc):
            raise ValueError()
        return candidates[0].isoformat()
    except (ValueError, TypeError, OverflowError, ZoneInfoNotFoundError) as error:
        raise ContractError('invalid_schedule', '확정된 지역 시간대와 오프셋이 일치하는 시각이 필요합니다') from error
