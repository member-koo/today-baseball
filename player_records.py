"""Verified KBO regular-season player tables and per-game box scores. No AI API."""
import datetime as dt
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from head_to_head import PAGE, TEAMS, parse_month

ROOT = Path(__file__).parent
BASE = 'https://www.koreabaseball.com'
CODES = dict(zip(['KIA','한화','LG','두산','삼성','롯데','SSG','NC','KT','키움'],
                 ['HT','HH','LG','OB','SS','LT','SK','NC','KT','WO']))
BOX = BASE + '/ws/Schedule.asmx/GetBoxScoreScroll'


def text(value):
    return BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True).replace('\xa0',' ').strip()


def request(session, method, url, **kwargs):
    for attempt in range(3):
        try:
            response = session.request(method, url, timeout=35, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def session():
    s = requests.Session()
    s.headers.update({'User-Agent':'Mozilla/5.0','Referer':PAGE})
    return s


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    temp.replace(path)


def form(soup):
    values = {i['name']:i.get('value','') for i in soup.select('input[type=hidden][name]')}
    for select in soup.select('select[name]'):
        option = select.select_one('option[selected]') or select.select_one('option')
        values[select['name']] = option.get('value','') if option else ''
    return values


def innings_outs(value):
    raw = text(value)
    if re.fullmatch(r'\d+',raw):
        return int(raw)*3
    match = re.fullmatch(r'(?:(\d+)\s+)?([12])\s*/\s*3',raw)
    if match:
        return int(match[1] or 0)*3+int(match[2])
    # Some KBO tables use baseball notation (6.1 = 6 innings and one out).
    match = re.fullmatch(r'(\d+)\.([012])',raw)
    if match:
        return int(match[1])*3+int(match[2])
    raise ValueError(f'Unknown innings: {raw}')


def official_players(kind, team, year):
    category = 'Hitter' if kind == 'batters' else 'Pitcher'
    url = BASE + f'/Record/Player/{category}Basic/Basic1.aspx'
    s = session()
    soup = BeautifulSoup(request(s,'GET',url).content,'html.parser')
    values = form(soup)
    def key(suffix):
        return next(k for k in values if k.endswith(suffix))
    season, series, team_key = (key('$ddlSeason$ddlSeason'),key('$ddlSeries$ddlSeries'),key('$ddlTeam$ddlTeam'))
    values.update({season:str(year),series:'0',team_key:CODES[team],
                   '__EVENTTARGET':series,'__EVENTARGUMENT':''})
    soup = BeautifulSoup(request(s,'POST',url,data=values).content,'html.parser')
    players = []
    seen = set()
    page = 1
    while True:
        current = form(soup)
        if [current.get(k) for k in (season,series,team_key)] != [str(year),'0',CODES[team]]:
            raise ValueError('Player season/series/team filter mismatch')
        table = soup.select_one('table.tData01')
        if table is None:
            raise ValueError('Player record table missing')
        headers = [h.get_text(' ',strip=True) for h in table.select('thead th')]
        found = 0
        for row in table.select('tbody tr'):
            link = row.select_one('a[href*="playerId="]')
            if not link:
                continue
            cells = row.select('td')
            if len(cells) != len(headers):
                raise ValueError('Player columns changed')
            player_id = parse_qs(urlparse(link['href']).query)['playerId'][0]
            if player_id in seen:
                raise ValueError('Repeated player page')
            seen.add(player_id)
            values_row = dict(zip(headers,[c.get_text(' ',strip=True) for c in cells]))
            if values_row.get('팀명') != team:
                raise ValueError('Wrong team in player row')
            stats = {k: v for k,v in values_row.items() if k not in ('순위','선수명','팀명')}
            players.append(dict(id=player_id,name=link.get_text(strip=True),team=team,
                                season=stats,source=url,profile=BASE+link['href']))
            found += 1
        if found == 0:
            raise ValueError(f'No official {kind}: {team}')
        next_link = next((a for a in soup.select('.paging a') if a.get_text(strip=True)==str(page+1)),None)
        if next_link is None:
            break
        target = re.search(r"__doPostBack\('([^']+)'",next_link['href'])
        if not target or page > 10:
            raise ValueError('Unrecognized player pagination')
        values = form(soup)
        values.update({'__EVENTTARGET':target[1],'__EVENTARGUMENT':''})
        soup = BeautifulSoup(request(s,'POST',url,data=values).content,'html.parser')
        page += 1
    return kind,team,players


def rows(table):
    return [[text(c.get('Text','')) for c in row['row']] for row in json.loads(table)['rows']]


def parse_box(payload, game):
    if str(payload.get('code')) != '100' or len(payload.get('arrHitter',[])) != 2 or len(payload.get('arrPitcher',[])) != 2:
        raise ValueError('Incomplete official box score')
    result = dict(game)
    result['batters'],result['pitchers'] = [],[]
    for i,side in enumerate(['away','home']):
        team,opponent = game[side],game['home' if side=='away' else 'away']
        hitter = payload['arrHitter'][i]
        names,stats = rows(hitter['table1']),rows(hitter['table3'])
        if not names or len(names) != len(stats):
            raise ValueError('Batter row count mismatch')
        for name,stat in zip(names,stats):
            if len(name)!=3 or len(stat)!=5 or not name[2]:
                raise ValueError('Batter layout changed')
            ab,h,rbi,r = [int(v) for v in stat[:4]]
            if not 0 <= h <= ab or min(ab,rbi,r)<0:
                raise ValueError('Invalid batter totals')
            result['batters'].append(dict(name=name[2],team=team,opponent=opponent,AB=ab,H=h,RBI=rbi,R=r))
        pitchers = rows(payload['arrPitcher'][i]['table'])
        if not pitchers:
            raise ValueError('Missing pitchers')
        for p in pitchers:
            if len(p)!=17:
                raise ValueError('Pitcher layout changed')
            result['pitchers'].append(dict(name=p[0],team=team,opponent=opponent,
                outs=innings_outs(p[6]),BF=int(p[7]),pitches=int(p[8]),AB=int(p[9]),H=int(p[10]),
                HR=int(p[11]),BB_HBP=int(p[12]),SO=int(p[13]),R=int(p[14]),ER=int(p[15]),
                W=int(p[2]=='승'),L=int(p[2]=='패'),SV=int(p[2]=='세'),HLD=int(p[2]=='홀드'),
                starter=(p[1]=='선발')))
        # Cross-check game totals: do not publish a misaligned/incomplete box score.
        own_batters=[p for p in result['batters'] if p['team']==team]
        own_pitchers=[p for p in result['pitchers'] if p['team']==team]
        if sum(p['R'] for p in own_batters)!=game[side+'_score']:
            raise ValueError('Batter runs disagree with official final score')
        if sum(p['R'] for p in own_pitchers)!=game[('home' if side=='away' else 'away')+'_score']:
            raise ValueError('Pitcher runs disagree with final score')
    return result


def fetch_box(game, year):
    s=session()
    response=request(s,'POST',BOX,data=dict(leId='1',srId='0',seasonId=str(year),gameId=game['id']))
    return parse_box(json.loads(response.content.decode('utf-8-sig')),game)


def summary(logs, kind):
    keys = ('AB','H','RBI','R') if kind=='batters' else ('outs','BF','pitches','AB','H','HR','BB_HBP','SO','R','ER','W','L','SV','HLD')
    result = {key:sum(p.get(key,0) for p in logs) for key in keys}
    result['G']=len(logs)
    if kind=='batters':
        result['AVG']=f"{result['H']/result['AB']:.3f}" if result['AB'] else None
    else:
        result['IP']=str(result['outs']//3)+(f" {result['outs']%3}/3" if result['outs']%3 else '')
        result['ERA']=f"{result['ER']*27/result['outs']:.2f}" if result['outs'] else None
    return result


def assemble(players, boxes, cutoff):
    teams={t:{'batters':[],'pitchers':[]} for t in TEAMS}
    for kind in ('batters','pitchers'):
        for team in TEAMS:
            people=players[team][kind]
            for person in people:
                logs=[]
                ambiguous=sum(p['name']==person['name'] for p in people)>1
                for box in boxes:
                    if box['date'] > cutoff.isoformat():
                        continue
                    matches=[p for p in box[kind] if p['team']==team and p['name']==person['name']]
                    if len(matches)>1:
                        ambiguous=True
                    for p in matches:
                        logs.append(dict(p,date=box['date'],game_id=box['id'],source=box['source']))
                logs.sort(key=lambda p:(p['date'],p['game_id']))
                # Reconcile totals with the ID-bearing official season table before
                # linking name-only box rows to a player (protects homonyms/trades).
                field='AB' if kind=='batters' else 'ER'
                season_value=person['season'].get(field)
                reconciled=not ambiguous and season_value is not None and int(season_value)==sum(p[field] for p in logs)
                if kind=='batters':
                    reconciled=reconciled and int(person['season']['H'])==sum(p['H'] for p in logs)
                else:
                    reconciled=reconciled and innings_outs(person['season']['IP'])==sum(p['outs'] for p in logs)
                person=dict(person,logs_verified=reconciled,
                            recent5=summary(logs[-5:],kind) if reconciled else None,
                            recent10=summary(logs[-10:],kind) if reconciled else None,
                            opponents={o:summary([p for p in logs if p['opponent']==o],kind) for o in TEAMS if o!=team} if reconciled else {},
                            last_game=logs[-1]['date'] if logs else None)
                teams[team][kind].append(person)
    return teams


def collect(date, directory=None):
    directory=Path(directory or ROOT/'data')
    cutoff=date-dt.timedelta(days=1)
    source=json.loads((directory/'head_to_head_sources.json').read_text(encoding='utf-8'))
    if source['season']!=date.year:
        raise ValueError('Result season mismatch')
    games=[]
    for snapshot in source['requests']:
        games.extend(parse_month(snapshot['payload'],date.year,snapshot['month'],cutoff))
    games.sort(key=lambda g:(g['date'],g['id']))
    if not games:
        raise ValueError('No complete game history')
    cache_path=directory/'boxscores.json'
    cache=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    cache={k:v for k,v in cache.items() if k.startswith(str(date.year))}
    missing=[g for g in games if g['id'] not in cache or g['date'] >= (cutoff-dt.timedelta(days=2)).isoformat()]
    print(f'Official box scores: {len(games)} games, {len(missing)} to fetch',flush=True)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(fetch_box,g,date.year):g for g in missing}
        for n,future in enumerate(as_completed(futures),1):
            result=future.result(); cache[result['id']]=result
            if n%30==0:
                atomic(cache_path,cache)
                print(f'Box scores {n}/{len(missing)}',flush=True)
    atomic(cache_path,cache)
    players={t:{} for t in TEAMS}
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(official_players,kind,t,date.year) for t in TEAMS for kind in ('batters','pitchers')]
        for future in as_completed(futures):
            kind,team,people=future.result(); players[team][kind]=people
            print(f'Official player IDs: {team} {kind} {len(people)}',flush=True)
    boxes=[cache[g['id']] for g in games]
    result=dict(schema_version=1,season=date.year,series='regular',through_date=cutoff.isoformat(),
                updated_at=dt.datetime.now(ZoneInfo('Asia/Seoul')).isoformat(timespec='seconds'),
                game_count=len(boxes),source=PAGE,teams=assemble(players,boxes,cutoff))
    atomic(directory/'players.json',result)
    print('Player records published',flush=True)
    return result


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--date',default=dt.datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat())
    collect(dt.date.fromisoformat(p.parse_args().date))
