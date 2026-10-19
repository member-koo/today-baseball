import datetime as dt
import json
from pathlib import Path
import experimental_model as model

ROOT=Path(__file__).parent

def examples():
    return json.loads((ROOT/'model_preview.json').read_text(encoding='utf-8'))['games']

def game_from(example):
    return dict(example,series_id=0,cancelled=False,starting_pitchers={side:dict(example['starting_pitchers'][side],logs_verified=True) for side in ('away','home')})

def test_inference_reproduces_exported_examples():
    boxes=list(json.loads((ROOT/'data/boxscores.json').read_text(encoding='utf-8')).values())
    for example in examples()[::10]:
        result=model.forecast(game_from(example),boxes,dt.date.fromisoformat(example['date']))
        assert abs(result['home_probability']-example['forecast']['home_probability'])<1e-10
        assert result['away_score']==example['forecast']['away_score']
        assert result['home_score']==example['forecast']['home_score']

def test_postseason_cancelled_unknown_and_wrong_year_are_withheld():
    game=game_from(examples()[0]);date=dt.date.fromisoformat(game['date'])
    assert model.forecast(dict(game,series_id=7),[],date) is None
    assert model.forecast(dict(game,cancelled=True),[],date) is None
    assert model.forecast(dict(game,starting_pitchers={}),[],date) is None
    assert model.forecast(game,[],date.replace(year=2027)) is None

def test_future_results_never_enter_inference():
    example=examples()[0];date=dt.date.fromisoformat(example['date']);game=game_from(example)
    boxes=list(json.loads((ROOT/'data/boxscores.json').read_text(encoding='utf-8')).values())
    before=model.forecast(game,boxes,date)
    for b in boxes:
        if b['date']>=example['date']:
            b['away_score']=999
            for p in b['pitchers']:p.update(outs=999,SO=999,BF=999,R=999)
    assert before==model.forecast(game,boxes,date)

def test_collector_clears_old_postseason_predictions(tmp_path,monkeypatch):
    import game_analysis as module
    from zoneinfo import ZoneInfo
    day=dt.date(2026,10,18)
    raw=dict(G_ID='20261018HTLG0',G_DT='20261018',G_TM='14:00',SEASON_ID=2026,SR_ID=7,
             AWAY_ID='HT',HOME_ID='LG',GAME_STATE_SC='1',GAME_RESULT_CK=0,CANCEL_SC_ID='0')
    class Response:content=json.dumps(dict(code='100',game=[raw])).encode()
    monkeypatch.setattr(module,'request',lambda *args,**kwargs:Response())
    (tmp_path/'boxscores.json').write_text('{}',encoding='utf-8')
    (tmp_path/'daily_analysis.json').write_text(json.dumps(dict(game_date=day.isoformat(),games=[dict(id=raw['G_ID'],prediction={'away_score':4},model_prediction={'home_probability':.9})])),encoding='utf-8')
    result=module.collect(day,tmp_path,dt.datetime(2026,10,18,12,tzinfo=ZoneInfo('Asia/Seoul')))['games'][0]
    assert result['prediction'] is None and result['model_prediction'] is None

def test_preview_is_explicitly_historical_and_covers_all_teams():
    payload=json.loads((ROOT/'model_preview.json').read_text(encoding='utf-8'))
    assert payload['kind']=='historical_preview'
    assert len({g[side] for g in payload['games'] for side in ('away','home')})==10
    assert all(g['forecast']['stats_as_of']<g['date'] for g in payload['games'])
