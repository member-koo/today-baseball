import datetime as dt
import json
from zoneinfo import ZoneInfo
import pytest
import game_analysis as module
import next_schedule as lookup

def raw(day,away='HT',home='LG',suffix='0',cancel='0',series=0):
    return dict(G_ID=day.replace('-','')+away+home+suffix,G_DT=day.replace('-',''),G_TM='18:30',SEASON_ID=int(day[:4]),SR_ID=series,AWAY_ID=away,HOME_ID=home,GAME_STATE_SC='1',GAME_RESULT_CK=0,CANCEL_SC_ID=cancel,START_PIT_CK=0)

def run_collect(tmp_path,monkeypatch,today,calendar,next_result=None):
    def fake_request(session,method,url,**kwargs):
        day=kwargs['data']['date']
        class Response:content=json.dumps(dict(code='100',game=calendar.get(day,[]))).encode()
        return Response()
    monkeypatch.setattr(module,'request',fake_request)
    monkeypatch.setattr(module,'find_next',lambda session,date,fetch:next_result(fetch) if callable(next_result) else next_result)
    (tmp_path/'boxscores.json').write_text('{}',encoding='utf-8')
    return module.collect(today,tmp_path,dt.datetime.combine(today,dt.time(12),tzinfo=ZoneInfo('Asia/Seoul')))

def test_rest_day_displays_all_games_on_next_day(tmp_path,monkeypatch):
    today=dt.date(2026,8,31);tomorrow=today+dt.timedelta(days=1)
    games=[raw('2026-09-01',a,h) for a,h in [('HT','LG'),('OB','SS'),('LT','KT'),('SK','NC'),('WO','HH')]]
    result=run_collect(tmp_path,monkeypatch,today,{'20260901':games},lambda fetch:(tomorrow,fetch(tomorrow)))
    assert result['game_date']=='2026-08-31' and result['display_date']=='2026-09-01'
    assert result['schedule_kind']=='next' and len(result['games'])==5
    assert all(g['model_prediction'] is None for g in result['games'])
    assert {g[s] for g in result['games'] for s in ('away','home')}==set(module.TEAMS)

def test_today_games_take_precedence_even_if_favorite_idle(tmp_path,monkeypatch):
    today=dt.date(2026,9,1)
    def forbidden(*args):raise AssertionError('Must not search next day')
    monkeypatch.setattr(module,'request',lambda *args,**kwargs:type('R',(),{'content':json.dumps(dict(code='100',game=[raw('2026-09-01','OB','LG',series=7)])).encode()})())
    monkeypatch.setattr(module,'find_next',forbidden)
    (tmp_path/'boxscores.json').write_text('{}',encoding='utf-8')
    result=module.collect(today,tmp_path,dt.datetime(2026,9,1,12,tzinfo=ZoneInfo('Asia/Seoul')))
    assert result['schedule_kind']=='today' and result['games'][0]['away']=='두산'

def test_no_future_fixture_does_not_invent_season_end(tmp_path,monkeypatch):
    result=run_collect(tmp_path,monkeypatch,dt.date(2026,11,10),{},None)
    assert result['schedule_kind']=='none' and result['games']==[]
    assert '공식적으로 확인된' in result['schedule_message']

def test_all_cancelled_today_can_show_next_day(tmp_path,monkeypatch):
    today=dt.date(2026,8,31);tomorrow=today+dt.timedelta(days=1)
    result=run_collect(tmp_path,monkeypatch,today,{'20260831':[raw('2026-08-31',cancel='1')],'20260901':[raw('2026-09-01')]},lambda fetch:(tomorrow,fetch(tomorrow)))
    assert result['schedule_kind']=='next' and len(result['games'])==1

def test_next_game_unannounced_starters_are_not_inferred(tmp_path,monkeypatch):
    today=dt.date(2026,8,31);tomorrow=today+dt.timedelta(days=1)
    r=raw('2026-09-01');r.update(T_PIT_P_ID='1',T_PIT_P_NM='미발표',B_PIT_P_ID='2',B_PIT_P_NM='미발표')
    result=run_collect(tmp_path,monkeypatch,today,{'20260901':[r]},lambda fetch:(tomorrow,fetch(tomorrow)))
    assert result['games'][0]['starting_pitchers']=={'away':None,'home':None}

def test_month_candidates_include_future_and_cross_month():
    def row(date):return dict(row=[dict(Class='day',Text=date),dict(Class='play',Text='<span>KIA</span><em><span>vs</span></em><span>LG</span>')])
    assert lookup.candidate_dates(dict(rows=[row('09.01(화)')]),2026,9,dt.date(2026,8,31))==[dt.date(2026,9,1)]
    assert lookup.candidate_dates(dict(rows=[row('08.31(월)')]),2026,8,dt.date(2026,8,31))==[]
    with pytest.raises(ValueError):lookup.candidate_dates(dict(game=[]),2026,8,dt.date(2026,8,31))

def test_lookup_skips_cancelled_and_returns_whole_day(monkeypatch):
    day=dt.date(2026,10,19)
    payload=dict(rows=[dict(row=[dict(Class='day',Text='10.20(화)'),dict(Class='play',Text='<span>KIA</span><span>LG</span>')]),dict(row=[dict(Class='day',Text='10.21(수)'),dict(Class='play',Text='<span>KIA</span><span>LG</span>')])])
    monkeypatch.setattr(lookup,'request',lambda *a,**k:type('R',(),{'content':json.dumps(payload).encode()})())
    def fetch(date):return [dict(id='cancelled',cancelled=True,final=False)] if date.day==20 else [dict(id='a',cancelled=False,final=False),dict(id='b',cancelled=False,final=False)]
    selected,games=lookup.find_next(None,day,fetch)
    assert selected==dt.date(2026,10,21) and len(games)==2

def test_missing_time_does_not_mean_midnight():
    assert module.re_time('18:30')
    assert not module.re_time(None) and not module.re_time('시간 미정')
