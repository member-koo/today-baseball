"""Fetch public KBO schedule; fail closed if page format changes."""
import argparse
import datetime as dt
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from team_rankings import parse_standings
from lineup import load_lineups
from data_quality import assess
from preview_rules import validate_games
from prediction_model import attach_predictions
from insight_engine import build_insights

URL = 'https://www.koreabaseball.com/Schedule/Schedule.aspx'
TEAMS = ['KIA', '한화', 'LG', '두산', '삼성', '롯데', 'SSG', 'NC', 'KT', '키움']
TEAM_RE = r'(?:KIA|한화|LG|두산|삼성|롯데|SSG|NC|KT|키움)'
GAME_RE = re.compile(rf'({TEAM_RE})\s*(?:\d+\s*)?(?:vs|VS|:)\s*(?:\d+\s*)?({TEAM_RE})')
TIME_RE = re.compile(r'\b(?:0?[0-9]|1[0-9]|2[0-3]):[0-5][0-9]\b')
DATE_RE = re.compile(r'(?<!\d)(\d{1,2})\.(\d{1,2})(?:\([^)]*\))?')


def extract(html, target):
    soup = BeautifulSoup(html, 'html.parser')
    games = []

    # KBO schedule is a date-grouped table.
    # Reject ambiguous rows rather than guess.
    for table in soup.select('table'):
        rows = table.select('tr')
        active_date = None

        for tr in rows:
            cells = tr.find_all(['th', 'td'], recursive=False)
            if not cells:
                continue

            values = [c.get_text(' ', strip=True) for c in cells]
            if not values:
                continue

            first = values[0]
            date_match = DATE_RE.search(first)

            if date_match:
                active_date = (
                    int(date_match.group(1)),
                    int(date_match.group(2))
                )

            if active_date != (target.month, target.day):
                continue

            joined = ' | '.join(values)
            match = GAME_RE.search(joined)
            if not match:
                continue

            time_match = TIME_RE.search(joined)
            if not time_match:
                continue

            away, home = match.groups()

            venue = next(
                (
                    v for v in values
                    if v in [
                        '잠실', '고척', '문학', '수원', '대전',
                        '광주', '대구', '사직', '창원',
                        '울산', '포항', '청주'
                    ]
                ),
                '미확인'
            )

            item = {
                'time': time_match.group(),
                'away': away,
                'home': home,
                'venue': venue,
                'starting_pitchers': None,
                'lineups': None,
                'prediction': None
            }

            if item not in games:
                games.append(item)

    return games


def diagnose_response(html, target, response_url):
    """Print safe diagnostic details without fabricating games."""
    soup = BeautifulSoup(html, 'html.parser')

    print(f'DIAG requested_date={target.isoformat()}')
    print(f'DIAG response_url={response_url}')
    print(f'DIAG tables={len(soup.select("table"))}')
    print(f'DIAG html_length={len(html)}')
    print(
        'DIAG page_title=' +
        (soup.title.get_text(' ', strip=True) if soup.title else 'none')
    )

    matching_dates = []
    for tr in soup.select('tr'):
        cells = tr.find_all(['th', 'td'], recursive=False)
        if not cells:
            continue
        first = cells[0].get_text(' ', strip=True)
        match = DATE_RE.search(first)
        if match:
            value = f'{match.group(1)}.{match.group(2)}'
            if value not in matching_dates:
                matching_dates.append(value)

    print(f'DIAG detected_dates={matching_dates[:20]}')
    print(f'DIAG game_pattern_matches={len(GAME_RE.findall(soup.get_text(" ", strip=True)))}')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--date', help='YYYY-MM-DD, default Korea today')
    p.add_argument('--fixture', help='Use local HTML for offline tests')
    args = p.parse_args()

    today = (
        dt.date.fromisoformat(args.date)
        if args.date
        else dt.datetime.now(ZoneInfo('Asia/Seoul')).date()
    )

    path = Path(__file__).parent / 'data' / 'today.json'

    try:
        response_url = 'local fixture'

        if args.fixture:
            html = Path(args.fixture).read_text(encoding='utf-8')
        else:
            r = requests.get(
                URL,
                params={'year': today.year, 'month': today.month},
                timeout=25,
                headers={
                    'User-Agent': 'Mozilla/5.0 (compatible; BaseballPreview/0.2)'
                }
            )
            r.raise_for_status()
            r.encoding = r.apparent_encoding
            html = r.text
            response_url = r.url

        games = extract(html, today)

        if not games:
            diagnose_response(html, today, response_url)
            raise ValueError(
                '경기 행을 찾지 못했습니다. '
                '휴식일이거나 페이지 구조가 변경됐을 수 있습니다.'
            )

        validate_games(games)

        games = load_lineups(
            Path(__file__).parent / 'data' / 'lineups' / f'{today.isoformat()}.json',
            today.isoformat(),
            games
        )

        try:
            attach_predictions(
                games,
                today,
                Path(__file__).parent / 'data' / 'team_stats.json'
            )
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as err:
            print(f'WARN prediction unavailable: {err}')

        for game in games:
            game['insights'] = build_insights(game)

        standings = []
        standings_status = '순위 데이터 확인 불가'

        try:
            if not args.fixture:
                sr = requests.get(
                    'https://www.koreabaseball.com/',
                    timeout=25,
                    headers={'User-Agent': 'Mozilla/5.0'}
                )
                sr.raise_for_status()
                sr.encoding = sr.apparent_encoding
                standings = parse_standings(sr.text)

                if standings:
                    standings_status = 'KBO 공식 순위 확인'

        except requests.RequestException as err:
            print(f'WARN standings unavailable: {err}')

        result = {
            'standings': standings,
            'standings_status': standings_status,
            'status': '경기 일정 확인 · 라인업은 출처 확인 시 표시',
            'title': f'{today.isoformat()} KBO 경기 일정',
            'game_date': today.isoformat(),
            'updated_at': dt.datetime.now(
                ZoneInfo('Asia/Seoul')
            ).isoformat(timespec='minutes'),
            'source': response_url,
            'games': games,
            'note': (
                '예측은 검증된 팀 득실점 기록이 있을 때만 표시합니다. '
                '선발·라인업을 반영한 정교한 분석은 아직 준비 중입니다.'
            )
        }

        check = assess(result)

        if not check['publishable']:
            raise ValueError(check['reason'])

        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8'
        )

        print(f'OK {today}: {len(games)} games')

    except Exception as exc:
        # Preserve the last valid result if collection fails.
        print(f'ERROR: {exc}')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
