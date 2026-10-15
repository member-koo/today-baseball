import datetime as dt
import pytest
from player_records import innings_outs, summary, assemble
from game_analysis import estimate, parse_daily, team_history, comparison
from head_to_head import TEAMS


def test_fractional_innings_and_weighted_rates():
    assert innings_outs('6 2/3')==20
    assert innings_outs('0 1/3')==1
    assert innings_outs('6.1')==19
    with pytest.raises(ValueError): innings_outs('6.5')
    assert summary([dict(AB=1,H=1),dict(AB=9,H=0)],'batters')['AVG']=='0.100'
    stat=summary([dict(outs=2,ER=1),dict(outs=1,ER=0)],'pitchers')
    assert stat['ERA']=='9.00' and stat['IP']=='1'
    assert summary([dict(outs=0,ER=2)],'pitchers')['ERA'] is None


def test_missing_or_wrong_daily_payload():
    with pytest.raises(ValueError): parse_daily({},dt.date(2026,10,15))
    assert parse_daily(dict(code='100',game=[]),dt.date(2026,10,15))==[]
    raw=dict(G_DT='20261014',SEASON_ID=2026,AWAY_ID='HT',HOME_ID='LG')
    with pytest.raises(ValueError): parse_daily(dict(code='100',game=[raw]),dt.date(2026,10,15))


def test_player_identity_reconciliation_and_homonyms():
    people={t:{'batters':[],'pitchers':[]} for t in TEAMS}
    people['KIA']['batters']=[dict(id='1',name='동명',season=dict(AB='4',H='2')),
                              dict(id='2',name='동명',season=dict(AB='4',H='2')),
                              dict(id='3',name='확인',season=dict(AB='4',H='2'))]
    boxes=[dict(date='2026-04-01',id='a',source='https://www.koreabaseball.com/',batters=[dict(name=n,team='KIA',opponent='LG',AB=4,H=2,R=0,RBI=0)
                                               for n in ['동명','확인']],pitchers=[])]
    result=assemble(people,boxes,dt.date(2026,4,1))['KIA']['batters']
    assert not result[0]['logs_verified'] and result[0]['recent5'] is None
    assert not result[1]['logs_verified']
    assert result[2]['logs_verified'] and result[2]['opponents']['LG']['H']==2


def history():
    return [dict(id=f'g{i}',date=f'2026-04-{i:02}',away='KIA',home='LG',away_score=6,home_score=4,
                 source='https://www.koreabaseball.com/',pitchers=[])
            for i in range(1,21)]


def test_prediction_is_deterministic_and_excludes_future_results():
    boxes=history()
    game=dict(away='KIA',home='LG',starting_pitchers={})
    date=dt.date(2026,4,15)
    first=estimate(game,boxes,date)
    assert first and first==estimate(game,boxes,date)
    changed=history()
    for g in changed[14:]: g['away_score']=99
    assert first==estimate(game,changed,date)
    assert first['stats_as_of']=='2026-04-14'
    assert len(team_history(boxes,'KIA',date))==14
    assert estimate(game,boxes,dt.date(2026,4,5)) is None
    assert comparison(game,boxes,date)['away']['recent5']['games']==5


def test_daily_cancelled_and_final_flags():
    raw=dict(G_ID='20261015HTLG0',G_DT='20261015',SEASON_ID=2026,SR_ID=0,
             AWAY_ID='HT',HOME_ID='LG',GAME_STATE_SC='3',GAME_RESULT_CK=1,CANCEL_SC_ID='0',
             T_PIT_P_ID=1,T_PIT_P_NM='투수',B_PIT_P_ID=None,B_PIT_P_NM='')
    game=parse_daily(dict(code='100',game=[raw]),dt.date(2026,10,15))[0]
    assert game['final'] and not game['cancelled']
    assert game['starting_pitchers']['away']['id']=='1'
    raw['CANCEL_SC_ID']='1'
    assert parse_daily(dict(code='100',game=[raw]),dt.date(2026,10,15))[0]['cancelled']


def test_daily_freezes_pregame_prediction_after_start(tmp_path, monkeypatch):
    import json
    import game_analysis as module
    from zoneinfo import ZoneInfo
    raw=dict(G_ID='20260415HTLG0',G_DT='20260415',G_TM='18:30',SEASON_ID=2026,SR_ID=0,
             AWAY_ID='HT',HOME_ID='LG',GAME_STATE_SC='1',GAME_RESULT_CK=0,CANCEL_SC_ID='0')
    payload=dict(code='100',game=[raw])
    class Response:
        content=json.dumps(payload).encode()
    monkeypatch.setattr(module,'request',lambda *args,**kwargs:Response())
    (tmp_path/'boxscores.json').write_text(json.dumps({g['id']:g for g in history()}),encoding='utf-8')
    before=module.collect(dt.date(2026,4,15),tmp_path,dt.datetime(2026,4,15,16,tzinfo=ZoneInfo('Asia/Seoul')))
    prediction=before['games'][0]['prediction']
    assert prediction
    raw['GAME_STATE_SC']='3';raw['GAME_RESULT_CK']=1
    Response.content=json.dumps(payload).encode()
    after=module.collect(dt.date(2026,4,15),tmp_path,dt.datetime(2026,4,15,22,tzinfo=ZoneInfo('Asia/Seoul')))
    assert after['games'][0]['prediction']==prediction
    raw['CANCEL_SC_ID']='1';Response.content=json.dumps(payload).encode()
    cancelled=module.collect(dt.date(2026,4,15),tmp_path,dt.datetime(2026,4,15,22,tzinfo=ZoneInfo('Asia/Seoul')))
    assert cancelled['games'][0]['prediction'] is None
