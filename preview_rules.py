"""Presentation rules: no invented forecasts or starters."""
TEAMS=('KIA','한화','LG','두산','삼성','롯데','SSG','NC','KT','키움')

def validate_games(games):
    if not isinstance(games,list): raise ValueError('games must be a list')
    seen=set()
    for game in games:
        if game.get('away') not in TEAMS or game.get('home') not in TEAMS or game['away']==game['home']:
            raise ValueError('invalid KBO matchup')
        key=(game['away'],game['home'],game.get('time'))
        if key in seen: raise ValueError('duplicate game')
        seen.add(key)
    return True

def preview_status(game):
    if game.get('prediction') is None:
        return '예측 준비 중 · 실제 기록 기반 모델 미연결'
    return '예측 제공'
