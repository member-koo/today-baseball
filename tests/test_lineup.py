import json
from lineup import load_lineups

def sample():
    return {'date':'2026-10-09','games':{'KIA-NC':{'status':'projected','source_url':'https://example.org/source','checked_at':'2026-10-09T11:00:00+09:00','away':[{'name':f'A{i}','position':'포지션'} for i in range(9)],'home':[{'name':f'H{i}','position':'포지션'} for i in range(9)]}}}

def test_valid_projected(tmp_path):
    p=tmp_path/'lineup.json';p.write_text(json.dumps(sample()))
    games=load_lineups(p,'2026-10-09',[{'away':'KIA','home':'NC','lineups':None}])
    assert games[0]['lineups']['status']=='projected'

def test_wrong_date_ignored(tmp_path):
    p=tmp_path/'lineup.json';p.write_text(json.dumps(sample()))
    assert load_lineups(p,'2026-10-10',[{'away':'KIA','home':'NC','lineups':None}])[0]['lineups'] is None

def test_invalid_missing_player(tmp_path):
    d=sample();d['games']['KIA-NC']['away'].pop()
    p=tmp_path/'lineup.json';p.write_text(json.dumps(d))
    try: load_lineups(p,'2026-10-09',[{'away':'KIA','home':'NC'}])
    except ValueError: pass
    else: assert False
