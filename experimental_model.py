"""Experimental frozen ensemble inference. Standard library only; no AI API."""
import datetime as dt
import json
import math
from pathlib import Path
def sigmoid(x):return 1/(1+math.exp(-max(-35,min(35,x))))
def logit(p):
    p=max(.001,min(.999,p))
    return math.log(p/(1-p))
def build_features(g,past,elo,prior):
    assert all(b['date']<g['date'] for b in past)
    year=g['date'][:4];season=[b for b in past if b['date'][:4]==year]
    if not season:return None
    league=sum(b['away_score']+b['home_score'] for b in season)/(2*len(season))
    pitch=[p for b in season for p in b['pitchers']]
    lgouts=sum(p['outs'] for p in pitch);lgBF=sum(p['BF'] for p in pitch)
    lgRA=sum(p['R'] for p in pitch)*27/lgouts
    lgAVG=sum(p['H'] for b in season for p in b['batters'])/sum(p['AB'] for b in season for p in b['batters'])
    lgcomponent={k:sum(p[k] for p in pitch)/lgBF for k in ('SO','BB_HBP','HR')}
    teams={};starters={}
    for side in ('away','home'):
        team=g[side];hist=[b for b in season if team in (b['away'],b['home'])]
        if len(hist)<10:return None
        def value(b,own=True):
            s='away' if b['away']==team else 'home'
            return b[(s if own else ('home' if s=='away' else 'away'))+'_score']
        rs=lambda rows,own,n:(sum(value(b,own) for b in rows)+n*league)/(len(rows)+n)
        bat=[p for b in hist for p in b['batters'] if p['team']==team]
        teamAVG=(sum(p['H'] for p in bat)+50*lgAVG)/(sum(p['AB'] for p in bat)+50)
        actual_starters=[p for p in g['pitchers'] if p['team']==team and p['starter']]
        assert len(actual_starters)==1
        name=actual_starters[0]['name'];starters[side]=name
        logs=[dict(p,date=b['date']) for b in hist for p in b['pitchers'] if p['team']==team and p['name']==name]
        # Discounted previous-year history gives a prior without future stats.
        previous_logs=prior.get(team+'|'+name,[])
        def weighted_rate(key):
            return (sum(p[key] for p in logs)+.35*sum(p[key] for p in previous_logs)+100*lgcomponent[key])/(sum(p['BF'] for p in logs)+.35*sum(p['BF'] for p in previous_logs)+100)
        starts=[p for p in logs if p['starter']]
        def RA(rows,prior):return (sum(p['R'] for p in rows)*27+prior*lgRA)/(sum(p['outs'] for p in rows)+prior)
        starterRA=.7*RA(logs,90)+.3*RA(starts[-5:],60)
        ip=max(3,min(7,(sum(p['outs'] for p in starts[-5:])/3+10)/(len(starts[-5:])+2)))
        rel=[dict(p,date=b['date']) for b in hist for p in b['pitchers'] if p['team']==team and not p['starter']]
        day=dt.date.fromisoformat(g['date'])
        recent=[p for p in rel if (day-dt.date.fromisoformat(p['date'])).days<=30]
        bullpenRA=.7*RA(rel,180)+.3*RA(recent,120)
        load=lambda days:sum(p['pitches'] for p in rel if (day-dt.date.fromisoformat(p['date'])).days<=days)
        w=sum(value(b)>value(b,False) for b in hist);loss=sum(value(b)<value(b,False) for b in hist)
        teams[side]=dict(rs=rs(hist,True,15),ra=rs(hist,False,15),recent_rs=rs(hist[-10:],True,5),recent_ra=rs(hist[-10:],False,5),AVG=teamAVG,starter_RA=starterRA,starter_IP=ip,bullpen_RA=bullpenRA,load1=load(1),load3=load(3),rest=min(7,(day-dt.date.fromisoformat(hist[-1]['date'])).days),winrate=(w+5)/(w+loss+10),**{k:weighted_rate(k) for k in lgcomponent})
    a,h=teams['away'],teams['home']
    log5=logit(h['winrate'])-logit(a['winrate'])
    base=[h['rs']-a['rs'],a['ra']-h['ra'],h['recent_rs']-a['recent_rs'],a['recent_ra']-h['recent_ra'],h['AVG']-a['AVG'],a['starter_RA']-h['starter_RA'],h['SO']-a['SO'],a['BB_HBP']-h['BB_HBP'],a['HR']-h['HR'],h['starter_IP']-a['starter_IP'],a['bullpen_RA']-h['bullpen_RA'],a['load1']-h['load1'],a['load3']-h['load3'],h['rest']-a['rest'],logit(elo['20']),log5]
    # Interactions reflect innings allocation, not universal fixed percentage penalties.
    context=[a['starter_RA']*a['starter_IP']/9-h['starter_RA']*h['starter_IP']/9,a['bullpen_RA']*(9-a['starter_IP'])/9-h['bullpen_RA']*(9-h['starter_IP'])/9,a['load3']*(9-a['starter_IP'])/9-h['load3']*(9-h['starter_IP'])/9]
    score=[]
    for own,opp,home in [(a,h,0),(h,a,1)]:
        score.append([own['rs'],opp['ra'],own['recent_rs'],opp['recent_ra'],own['AVG'],opp['starter_RA'],opp['starter_IP'],opp['bullpen_RA'],opp['load3'],home])
    return dict(id=g['id'],date=g['date'],year=int(year),away=g['away'],home=g['home'],actual=[g['away_score'],g['home_score']],source=g['source'],starters=starters,history_latest=max(b['date'] for b in past),x=base,context=context,score_x=score,league=league,elo=elo,log5=float(sigmoid(log5)),teams=teams)

def load_bundle():
    return json.loads(Path(__file__).with_name('model_bundle.json').read_text(encoding='utf-8'))

def elo_before(boxes,date,bundle):
    ratings={int(k):dict(table) for k,table in bundle['elo_seed'].items()}
    past=[b for b in boxes if b['date']<date and b['date'][:4]==date[:4]]
    for day in sorted({b['date'] for b in past}):
        delta={k:{t:0. for t in table} for k,table in ratings.items()}
        for b in [b for b in past if b['date']==day]:
            y=.5 if b['home_score']==b['away_score'] else float(b['home_score']>b['away_score'])
            for k,table in ratings.items():
                p=sigmoid((table[b['home']]-table[b['away']]+40)*math.log(10)/400)
                change=k*(y-p);delta[k][b['home']]+=change;delta[k][b['away']]-=change
        for k in ratings:
            for t,value in delta[k].items():ratings[k][t]+=value
    return ratings

def standardized_score(x,model):
    return model['beta'][0]+sum(beta*(value-mean)/sd for value,mean,sd,beta in zip(x,model['mean'],model['sd'],model['beta'][1:]))

def from_features(row,bundle):
    models=bundle['models']
    context=sigmoid(standardized_score(row['x']+row['context'],models['context_logistic']))
    expected=[max(.1,min(15,math.exp(max(-8,min(5,math.log(row['league'])+standardized_score(x,models['Poisson'])))))) for x in row['score_x']]
    def pmf(rate):
        probs=[math.exp(-rate)]
        for k in range(1,81):probs.append(probs[-1]*rate/k)
        return probs
    a,h=map(pmf,expected);tie=sum(x*y for x,y in zip(a,h));cumulative=0.;wins=0.
    for ap,hp in zip(a,h):wins+=hp*cumulative;cumulative+=ap
    poisson=wins/(1-tie)
    raw=(row['elo'][str(models['Elo']['K'])]+context+poisson)/3
    p=sigmoid(bundle['calibration'][0]+bundle['calibration'][1]*logit(raw))
    assert all(math.isfinite(v) for v in [p,*expected])
    return dict(model_version=bundle['model_version'],home_probability=p,away_probability=1-p,
        expected_away_runs=expected[0],expected_home_runs=expected[1],
        away_score=math.floor(expected[0]+.5),home_score=math.floor(expected[1]+.5),
        stats_as_of=row['history_latest'],lineup_included=False,experimental=True,
        probability_basis='conditional_on_decisive_game')

def forecast(game,boxes,date,bundle=None):
    # No inference for postseason, cancelled games, wrong season or unknown starters.
    if str(game.get('series_id')) not in ('0','9','6') or game.get('cancelled'):return None
    bundle=bundle or load_bundle()
    if date.year!=bundle['season']:return None
    starters=game.get('starting_pitchers') or {}
    if any(not isinstance(starters.get(s),dict) or not starters[s].get('logs_verified') for s in ('away','home')):return None
    before=date.isoformat();past=sorted([b for b in boxes if b['date']<before and b['date'][:4]==str(date.year)],key=lambda b:(b['date'],b['id']))
    if not past:return None
    ratings=elo_before(past,before,bundle)
    elo={str(k):sigmoid((table[game['home']]-table[game['away']]+40)*math.log(10)/400) for k,table in ratings.items()}
    request=dict(game,date=before,away_score=None,home_score=None,id=game.get('id','pregame'),source=game.get('source',''),pitchers=[dict(team=game[s],name=starters[s]['name'],starter=True) for s in ('away','home')])
    features=build_features(request,past,elo,bundle['prior_pitchers'])
    if features is None:return None
    return from_features(features,bundle)
