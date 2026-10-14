"""Safety checks before showing or publishing a KBO preview."""
import datetime as dt
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')

def assess(data, now=None):
    now = now or dt.datetime.now(KST)
    if now.tzinfo is None:
        raise ValueError('now must be timezone-aware')
    try:
        date = dt.date.fromisoformat(data['game_date'])
        checked = dt.datetime.fromisoformat(data['updated_at'])
        if checked.tzinfo is None:
            raise ValueError('timestamp lacks timezone')
    except (KeyError, TypeError, ValueError) as exc:
        return {'publishable': False, 'reason': f'날짜 검증 실패: {exc}'}
    if date != now.astimezone(KST).date():
        return {'publishable': False, 'reason': '오늘 경기 데이터가 아닙니다'}
    age = (now - checked).total_seconds()
    if age < -300 or age > 3 * 3600:
        return {'publishable': False, 'reason': '데이터가 오래되었거나 시각이 잘못됐습니다'}
    if not data.get('source', '').startswith('https://www.koreabaseball.com/'):
        return {'publishable': False, 'reason': '공식 일정 출처를 확인할 수 없습니다'}
    if not isinstance(data.get('games'), list):
        return {'publishable': False, 'reason': '경기 목록이 올바르지 않습니다'}
    return {'publishable': True, 'reason': '경기 일정 기준일과 출처 확인'}
