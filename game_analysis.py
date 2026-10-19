"""Deterministic pre-game estimates and numeric comparisons; no generative service."""
import datetime as dt
import json
import math
from pathlib import Path
from zoneinfo import ZoneInfo
from head_to_head import TEAMS
from player_records import BASE, CODES, ROOT, atomic, request, session
from experimental_model import forecast as experimental_forecast
from next_schedule import find_next

DAILY = BASE+'/ws/Main.asmx/GetKboGameList'


def team_history(boxes, team, before):
    result=[]
    for g in sorted(boxes,key=lambda x:(x['date'],x['id'])):
        if g['date']>=before.isoformat() or team not in (g['away'],g['home']):
            continue
        side='away' if g['away']==team else 'home'
        other='home' if side=='away' else 'away'
        result.append(dict(date=g['date'],id=g['id'],opponent=g[other],
                           rs=g[side+'_score'],ra=g[other+'_score'],source=g['source']))
    return result


def team_summary(games):
    n=len(games)
    return dict(games=n,runs_scored=sum(g['rs'] for g in games),runs_allowed=sum(g['ra'] for g in games),
                scored_per_game=round(sum(g['rs'] for g in games)/n,2) if n else None,
                allowed_per_game=round(sum(g['ra'] for g in games)/n,2) if n else None,
                wins=sum(g['rs']>g['ra'] for g in games),losses=sum(g['rs']<g['ra'] for g in games),
                draws=sum(g['rs']==g['ra'] for g in games))


def starter_summary(boxes, team, name, opponent, before):
    logs=[]
    if not name:
        return None
    for box in sorted(boxes,key=lambda x:(x['date'],x['id'])):
        if box['date']>=before.isoformat():
            continue
        matches=[p for p in box['pitchers'] if p['team']==team and p['name']==name]
        if len(matches)>1:
            return None
        logs.extend(matches)
    if not logs:
        return None
    def stats(rows):
        outs=sum(p['outs'] for p in rows)
        return dict(appearances=len(rows),outs=outs,
                    IP=str(outs//3)+(f' {outs%3}/3' if outs%3 else ''),
                    wins=sum(p['W'] for p in rows) if all(p.get('W') in (0,1) for p in rows) else None,
                    losses=sum(p['L'] for p in rows) if all(p.get('L') in (0,1) for p in rows) else None,
                    ERA=round(sum(p['ER'] for p in rows)*27/outs,2) if outs else None)
    starts=[p for p in logs if p.get('starter')]
    return dict(name=name,season=stats(logs),recent3=stats(starts[-3:]),recent5=stats(starts[-5:]),
                opponent=stats([p for p in logs if p['opponent']==opponent]))


def estimate(game, boxes, date):
    # Exclusively use completed games dated before today's game.
    eligible=[b for b in boxes if b['date']<date.isoformat()]
    histories={t:team_history(eligible,t,date) for t in TEAMS}
    a,h=histories[game['away']],histories[game['home']]
    if min(len(a),len(h))<10:
        return None
    gp=sum(len(rows) for rows in histories.values())
    league=sum(g['rs'] for rows in histories.values() for g in rows)/gp
    if league<=0:
        return None
    def rate(history,key,opponent):
        def smooth(rows,n):
            return (sum(g[key] for g in rows)+n*league)/(len(rows)+n)
        return (.60*smooth(history,10)+.30*smooth(history[-10:],5)
                +.10*smooth([g for g in history if g['opponent']==opponent],10))
    away=rate(a,'rs',game['home'])*rate(h,'ra',game['away'])/league
    home=rate(h,'rs',game['away'])*rate(a,'ra',game['home'])/league*1.04
    starters={}
    # Starting-pitcher identity must already come from the official daily listing.
    for side,other in [('away','home'),('home','away')]:
        starter=(game.get('starting_pitchers') or {}).get(side)
        name=starter.get('name') if isinstance(starter,dict) and starter.get('logs_verified') else None
        stat=starter_summary(eligible,game[side],name,game[other],date)
        starters[side]=stat
        if stat and stat['season']['outs']>=90:
            recent=stat['recent5']
            era=.7*stat['season']['ERA']+.3*(recent['ERA'] if recent['outs']>=27 else stat['season']['ERA'])
            # Modest, capped influence: starter covers only part of the game.
            factor=max(.85,min(1.15,1+.25*(era-league)/league))
            if side=='away': home*=factor
            else: away*=factor
    away,home=(max(.1,min(15,x)) for x in (away,home))
    return dict(away_score=math.floor(away+.5),home_score=math.floor(home+.5),
                expected_away_runs=round(away,2),expected_home_runs=round(home,2),
                stats_as_of=max(g['date'] for g in eligible),
                method='참고 예상 · 시즌 60% / 최근10경기 30% / 상대전적 10% (평균으로 보정)',
                starters_included=[side for side in starters if starters[side] and starters[side]['season']['outs']>=90],
                provisional=True,validated_accuracy=False)


def comparison(game, boxes, date):
    result={}
    for side,other in [('away','home'),('home','away')]:
        history=team_history(boxes,game[side],date)
        pitcher=(game.get('starting_pitchers') or {}).get(side)
        name=pitcher.get('name') if isinstance(pitcher,dict) and pitcher.get('logs_verified') else None
        result[side]=dict(team=game[side],season=team_summary(history),recent5=team_summary(history[-5:]),
                          recent10=team_summary(history[-10:]),
                          opponent=team_summary([g for g in history if g['opponent']==game[other]]),
                          starter=starter_summary(boxes,game[side],name,game[other],date))
    return result


def parse_daily(payload,date):
    if str(payload.get('code'))!='100' or not isinstance(payload.get('game'),list):
        raise ValueError('Daily KBO response unverified')
    games=[]
    reverse={v:k for k,v in CODES.items()}
    for raw in payload['game']:
        if raw.get('G_DT')!=date.strftime('%Y%m%d') or int(raw.get('SEASON_ID',0))!=date.year:
            raise ValueError('Daily game date/season mismatch')
        if raw.get('AWAY_ID') not in reverse or raw.get('HOME_ID') not in reverse:
            raise ValueError('Unknown daily team')
        starting={}
        for side,prefix in [('away','T'),('home','B')]:
            pid=raw.get(prefix+'_PIT_P_ID')
            name=str(raw.get(prefix+'_PIT_P_NM') or '').strip()
            starting[side]=dict(id=str(pid),name=name) if pid and name else None
        games.append(dict(id=raw['G_ID'],time=raw.get('G_TM'),venue=raw.get('S_NM'),
                          date=date.isoformat(),starters_announced=raw.get('START_PIT_CK') in (True,1,'1'),
                          away=reverse[raw['AWAY_ID']],home=reverse[raw['HOME_ID']],
                          series_id=raw['SR_ID'],state=str(raw.get('GAME_STATE_SC','')),
                          cancelled=str(raw.get('CANCEL_SC_ID','0'))!='0',
                          final=raw.get('GAME_RESULT_CK')==1,
                          away_score=raw.get('T_SCORE_CN'),home_score=raw.get('B_SCORE_CN'),
                          starting_pitchers=starting,
                          source=BASE+'/Schedule/GameCenter/Main.aspx?gameDate='+raw['G_DT']+'&gameId='+raw['G_ID']))
    if len({g['id'] for g in games})!=len(games):
        raise ValueError('Duplicate daily game')
    return games


def collect(date,directory=None,now=None):
    directory=Path(directory or ROOT/'data')
    now=now or dt.datetime.now(ZoneInfo('Asia/Seoul'))
    s=session()
    def fetch_day(day):
        payload=json.loads(request(s,'POST',DAILY,data=dict(leId='1',srId='0,1,3,4,5,6,7,9',date=day.strftime('%Y%m%d'))).content.decode('utf-8-sig'))
        return parse_daily(payload,day)
    games=fetch_day(date)
    display_date=date
    schedule_kind='today'
    schedule_message=''
    if not any(not g['cancelled'] for g in games):
        try:
            following=find_next(s,date,fetch_day)
            if following:
                display_date,games=following
                schedule_kind='next'
                schedule_message='오늘 경기가 없어 다음 경기일의 전 구단 일정을 표시합니다.'
            else:
                games=[]
                schedule_kind='none'
                schedule_message='공식적으로 확인된 다음 경기 일정이 없습니다.'
        except Exception as error:
            games=[]
            schedule_kind='unavailable'
            schedule_message='오늘 경기가 없습니다. 다음 공식 일정은 확인하지 못했습니다.'
            print(f'Next schedule unavailable: {error}',flush=True)
    cache=json.loads((directory/'boxscores.json').read_text(encoding='utf-8'))
    boxes=[box for box in cache.values() if box['date']<date.isoformat()]
    players_path=directory/'players.json'
    players=json.loads(players_path.read_text(encoding='utf-8')) if players_path.exists() else {}
    old_path=directory/'daily_analysis.json'
    old=json.loads(old_path.read_text(encoding='utf-8')) if old_path.exists() else {}
    previous={g['id']:g for g in old.get('games',[]) if old.get('display_date',old.get('game_date'))==display_date.isoformat()}
    for g in games:
        regular = str(g['series_id']) in ('0','9','6')
        if display_date>date and not g['starters_announced']:
            g['starting_pitchers']={'away':None,'home':None}
        for side in ('away','home'):
            starter=g['starting_pitchers'].get(side)
            if starter:
                matches=[p for p in players.get('teams',{}).get(g[side],{}).get('pitchers',[])
                         if p['id']==starter['id'] and p['name']==starter['name']]
                starter['logs_verified']=len(matches)==1 and matches[0].get('logs_verified',False)
        g['comparison']=comparison(g,boxes,date)
        kickoff=(dt.datetime.fromisoformat(display_date.isoformat()+'T'+g['time']).replace(tzinfo=ZoneInfo('Asia/Seoul'))
                 if re_time(g.get('time')) else None)
        g['prediction']=None
        g['model_prediction']=None
        if regular and not g['cancelled'] and not g['final'] and kickoff and now<kickoff:
            g['prediction']=estimate(g,boxes,display_date)
            g['model_prediction']=experimental_forecast(g,boxes,display_date)
            if g['model_prediction']:
                g['model_prediction']['generated_at']=now.isoformat(timespec='seconds')
            if g['prediction']:
                g['prediction']['generated_at']=now.isoformat(timespec='seconds')
        elif regular and g['id'] in previous and not g['cancelled']:
            g['prediction']=previous[g['id']].get('prediction')
            g['model_prediction']=previous[g['id']].get('model_prediction')
        g['prediction_status']='취소 경기' if g['cancelled'] else ('경기 전 저장된 예상' if g['prediction'] else '경기 전 기록 부족 또는 경기 시작 후 신규 예측 보류')
        if not regular:
            g['prediction_status']='포스트시즌 예상은 제공하지 않습니다'
    result=dict(schema_version=1,game_date=date.isoformat(),updated_at=now.isoformat(timespec='seconds'),
                display_date=display_date.isoformat(),schedule_kind=schedule_kind,schedule_message=schedule_message,
                source=BASE+'/Schedule/GameCenter/Main.aspx',games=games,
                note='AI API 미사용 · 공식 정규시즌 기록 기반 참고 예상 · 정확도 미검증 · 확정 라인업·불펜 소모 미반영')
    atomic(old_path,result)
    print(f'Daily comparison: {date}, {len(games)} games',flush=True)
    return result


def re_time(value):
    # Unannounced times are schedule data, never an implicit midnight kickoff.
    try:
        return isinstance(value,str) and len(value)==5 and dt.time.fromisoformat(value) is not None
    except ValueError:
        return False


if __name__=='__main__':
    collect(dt.datetime.now(ZoneInfo('Asia/Seoul')).date())
