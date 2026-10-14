"""Transparent pre-game baseline; refuses missing/unverified team run-rate data."""
import datetime as dt
import math
from pathlib import Path
import json

TEAMS = {'KIA','한화','LG','두산','삼성','롯데','SSG','NC','KT','키움'}

def validate_stats(data, game_date):
    if not isinstance(data, dict) or data.get('season') != game_date.year:
        raise ValueError('시즌 정보 불일치')
    as_of = dt.date.fromisoformat(data['as_of'])
    if not (dt.date(game_date.year, 1, 1) <= as_of < game_date):
        raise ValueError('경기 전 기준 기록이 아닙니다')
    if not str(data.get('source','')).startswith('https://'):
        raise ValueError('기록 출처 누락')
    teams = data.get('teams')
    if not isinstance(teams, dict) or set(teams) != TEAMS:
        raise ValueError('10개 구단 기록 필요')
    for name, stats in teams.items():
        gp, rs, ra = (stats.get(k) for k in ('games','runs_scored','runs_allowed'))
        if type(gp) is not int or not 10 <= gp <= 144:
            raise ValueError(f'{name}: 경기 수 오류')
        if any(type(v) is not int or v < 0 for v in (rs,ra)):
            raise ValueError(f'{name}: 득실점 오류')
    return True

def poisson_win_prob(away_mu, home_mu, max_runs=30):
    """Independent Poisson approximation, ties split evenly (not KBO tie rules)."""
    def pmf(mu):
        arr=[math.exp(-mu)]
        for k in range(1,max_runs+1): arr.append(arr[-1]*mu/k)
        arr[-1] += max(0.0,1-sum(arr))
        return arr
    a,h=pmf(away_mu),pmf(home_mu)
    p_home=sum(h[i]*sum(a[:i]) for i in range(1,len(h)))
    p_tie=sum(x*y for x,y in zip(a,h))
    return round(100*(p_home+p_tie/2),1)

def predict(game, stats, game_date):
    validate_stats(stats, game_date)
    away,home=game['away'],game['home']
    if away not in TEAMS or home not in TEAMS or away==home:
        raise ValueError('대진 오류')
    a,h=stats['teams'][away],stats['teams'][home]
    # League baseline + each team's offense and opposing defense, with modest smoothing.
    league=sum(s['runs_scored'] for s in stats['teams'].values())/sum(s['games'] for s in stats['teams'].values())
    if league<=0: raise ValueError('득점 데이터 부족')
    def rate(s,key): return (s[key]+10*league)/(s['games']+10)
    mu_a=max(0.1,min(15,rate(a,'runs_scored')*rate(h,'runs_allowed')/league))
    mu_h=max(0.1,min(15,rate(h,'runs_scored')*rate(a,'runs_allowed')/league*1.04))
    return {'away_score':round(mu_a),'home_score':round(mu_h),
            'home_win_pct':poisson_win_prob(mu_a,mu_h),
            'method':'팀 경기당 득점·실점 기반 포아송 기초 모델 (선발·라인업 미반영)',
            'stats_as_of':stats['as_of'],'stats_source':stats['source'],
            'expected_away_runs':round(mu_a,2),'expected_home_runs':round(mu_h,2)}

def attach_predictions(games, date, path):
    if not Path(path).is_file(): return False
    stats=json.loads(Path(path).read_text(encoding='utf-8'))
    validate_stats(stats,date)
    for game in games: game['prediction']=predict(game,stats,date)
    return True
