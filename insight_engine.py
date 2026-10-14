"""Conservative, data-grounded preview notes; never invent player matchups."""

def build_insights(game, team_stats=None):
    away, home = game['away'], game['home']
    notes = []
    prediction = game.get('prediction')
    if prediction:
        a, h = prediction['expected_away_runs'], prediction['expected_home_runs']
        leader = away if a > h else home if h > a else None
        if leader:
            notes.append(f'기초 득점 모델은 {leader}의 기대 득점이 조금 더 높다고 봅니다 ({away} {a:.2f}점 · {home} {h:.2f}점).')
        else:
            notes.append('양 팀의 기대 득점이 같아 기초 모델로는 우열을 가리기 어렵습니다.')
        notes.append('이 예측에는 선발투수·확정 라인업·불펜 소모가 아직 반영되지 않았습니다.')
    else:
        notes.append('검증된 팀 득실점 자료가 없어 예상 점수와 승패를 보류합니다.')
    lineup = game.get('lineups')
    if lineup and lineup.get('status') == 'official':
        notes.append('공식 선발 라인업이 확인되었습니다. 개별 선수 상성 분석은 아직 제공하지 않습니다.')
    else:
        notes.append('공식 선발 라인업 미확인: 기대 선수·경계 선수를 임의로 선정하지 않습니다.')
    return notes
