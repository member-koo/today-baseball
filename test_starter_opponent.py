import datetime as dt
from game_analysis import starter_summary

def box(date, opponent, outs, er, w=0, l=0):
    return dict(id=date,date=date,pitchers=[dict(team='KIA',name='투수',opponent=opponent,outs=outs,ER=er,W=w,L=l,starter=True)])

def test_opponent_pitcher_decisions_and_weighted_era():
    rows=[box('2026-05-01','LG',18,1,1),box('2026-06-01','LG',10,7,0,1),box('2026-07-01','SSG',18,0,1)]
    stat=starter_summary(rows,'KIA','투수','LG',dt.date(2026,8,1))['opponent']
    assert (stat['wins'],stat['losses'],stat['IP'],stat['ERA']) == (1,1,'9 1/3',7.71)

def test_opponent_excludes_future_and_distinguishes_no_appearances():
    rows=[box('2026-05-01','SSG',18,0),box('2026-08-01','LG',18,0,1)]
    stat=starter_summary(rows,'KIA','투수','LG',dt.date(2026,8,1))['opponent']
    assert stat['appearances']==0 and stat['ERA'] is None
    assert starter_summary(rows,'KIA','미확인','LG',dt.date(2026,8,1)) is None

def test_zero_outs_does_not_fabricate_era():
    stat=starter_summary([box('2026-05-01','LG',0,2)],'KIA','투수','LG',dt.date(2026,8,1))['opponent']
    assert stat['IP']=='0' and stat['ERA'] is None

def test_unknown_decisions_are_not_assumed_zero():
    row=box('2026-05-01','LG',18,0)
    del row['pitchers'][0]['W']
    stat=starter_summary([row],'KIA','투수','LG',dt.date(2026,8,1))['opponent']
    assert stat['wins'] is None
