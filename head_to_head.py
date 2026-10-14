"""Regular-season results from the endpoint used by KBO's schedule page."""
import datetime as dt
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

PAGE = 'https://www.koreabaseball.com/Schedule/Schedule.aspx'
API = 'https://www.koreabaseball.com/ws/Schedule.asmx/GetScheduleList'
TEAMS = ['KIA', '한화', 'LG', '두산', '삼성', '롯데', 'SSG', 'NC', 'KT', '키움']


def parse_month(payload, year, month, cutoff):
    if not isinstance(payload, dict) or not isinstance(payload.get('rows'), list):
        raise ValueError('KBO results response has no rows')
    games = {}
    active_date = None
    for item in payload['rows']:
        cells = item['row']
        for cell in cells:
            if cell.get('Class') == 'day':
                match = re.search(r'(\d{2})\.(\d{2})', cell['Text'])
                if not match:
                    raise ValueError('Unrecognized KBO date')
                active_date = dt.date(year, int(match[1]), int(match[2]))
        if active_date is None or active_date.month != month:
            raise ValueError('Month/date mismatch')
        if active_date > cutoff:
            continue
        markup = ''.join(c.get('Text', '') for c in cells)
        # KBO emits bare &section, which HTMLParser interprets as &sect.
        markup = re.sub(r'&(?!amp;)([A-Za-z]+)=', r'&amp;\1=', markup)
        html = BeautifulSoup(markup, 'html.parser')
        review = html.select_one('a[href*="section=REVIEW"]')
        # Scores in a live game are not final results. REVIEW is the final-game link.
        if review is None:
            continue
        query = parse_qs(urlparse(review['href']).query)
        game_id = query['gameId'][0]
        if query['gameDate'][0] != active_date.strftime('%Y%m%d') or not game_id.startswith(str(year)):
            raise ValueError('Game identity/date mismatch')
        play = next(c['Text'] for c in cells if c.get('Class') == 'play')
        soup = BeautifulSoup(play, 'html.parser')
        names = [s.get_text(strip=True) for s in soup.find_all('span', recursive=False)]
        scores = [s.get_text(strip=True) for s in soup.select('em span')]
        if len(names) != 2 or any(n not in TEAMS for n in names) or names[0] == names[1]:
            raise ValueError('Unknown matchup')
        if len(scores) != 3 or scores[1].lower() != 'vs' or not scores[0].isdigit() or not scores[2].isdigit():
            raise ValueError('Final score missing')
        game = dict(id=game_id, date=active_date.isoformat(), away=names[0], home=names[1],
                    away_score=int(scores[0]), home_score=int(scores[2]),
                    source='https://www.koreabaseball.com' + review['href'])
        if game_id in games and games[game_id] != game:
            raise ValueError('Conflicting duplicate result')
        games[game_id] = game
    return list(games.values())


def aggregate(games):
    teams = {t: {o: dict(wins=0, losses=0, draws=0, batting_average=None, era=None, flow=[])
                 for o in TEAMS if o != t} for t in TEAMS}
    seen = set()
    for g in sorted(games, key=lambda x: (x['date'], x['id'])):
        if g['id'] in seen:
            raise ValueError('Duplicate game ID')
        seen.add(g['id'])
        for side, other in [('away', 'home'), ('home', 'away')]:
            own, opponent = g[side + '_score'], g[other + '_score']
            result = '승' if own > opponent else '패' if own < opponent else '무'
            row = teams[g[side]][g[other]]
            row[{'승': 'wins', '패': 'losses', '무': 'draws'}[result]] += 1
            row['flow'].append(dict(id=g['id'], date=g['date'], result=result,
                                    score=f'{own}:{opponent}', source=g['source']))
    for opponents in teams.values():
        if sum(len(row['flow']) for row in opponents.values()) > 144:
            raise ValueError('More than 144 regular-season games for a team')
        if any(len(row['flow']) > 16 for row in opponents.values()):
            raise ValueError('More than 16 regular-season games against an opponent')
    return teams


def collect(cutoff, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    games, snapshots = [], []
    with requests.Session() as session:
        session.get(PAGE, timeout=30).raise_for_status()
        session.headers.update({'User-Agent': 'Mozilla/5.0', 'Referer': PAGE,
                                'X-Requested-With': 'XMLHttpRequest'})
        for month in range(1, cutoff.month + 1):
            response = session.post(API, data=dict(leId='1', srIdList='0,9,6',
                                    seasonId=str(cutoff.year), gameMonth=f'{month:02}', teamId=''), timeout=30)
            response.raise_for_status()
            # KBO omits a reliable charset on some JSON responses.
            payload = json.loads(response.content.decode('utf-8-sig'))
            games.extend(parse_month(payload, cutoff.year, month, cutoff))
            snapshots.append(dict(month=month, payload=payload))
    if not games:
        raise ValueError('No verified completed regular-season games; preserving previous file')
    result = dict(schema_version=1, season=cutoff.year, series='regular', through_date=cutoff.isoformat(),
                  updated_at=dt.datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),
                  source=PAGE, game_count=len(games), teams=aggregate(games))
    # Reject a suspicious partial response instead of replacing a complete season.
    path = directory / 'head_to_head.json'
    if path.exists():
        previous = json.loads(path.read_text(encoding='utf-8'))
        if previous.get('season') == cutoff.year and previous.get('game_count', 0) > len(games):
            raise ValueError('Result count decreased; preserving previous data')
    for name, content in [('head_to_head_sources.json', dict(season=cutoff.year, source=API,
                                                           requests=snapshots)), ('head_to_head.json', result)]:
        target = directory / name
        temp = target.with_suffix('.tmp')
        temp.write_text(json.dumps(content, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        temp.replace(target)
    return result


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', default=dt.datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    args = parser.parse_args()
    result = collect(dt.date.fromisoformat(args.date), Path(__file__).parent / 'data')
    print(f"Verified {result['game_count']} completed games")
