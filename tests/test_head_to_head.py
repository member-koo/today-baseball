import datetime as dt
import pytest
from head_to_head import aggregate, parse_month


def payload(score='2', other='2', section='REVIEW', suffix='0'):
    return {'rows': [{'row': [
        {'Class': 'day', 'Text': '03.28(토)'},
        {'Class': 'play', 'Text': f'<span>KT</span><em><span>{score}</span><span>vs</span><span>{other}</span></em><span>LG</span>'},
        {'Class': 'relay', 'Text': f"<a href='/Schedule/GameCenter/Main.aspx?gameDate=20260328&gameId=20260328KTLG{suffix}&section={section}'>리뷰</a>"}
    ]}]}


def test_final_only_and_date_cutoff():
    assert parse_month(payload(section='PREVIEW'), 2026, 3, dt.date(2026, 10, 14)) == []
    assert parse_month(payload(), 2026, 3, dt.date(2026, 3, 27)) == []
    assert len(parse_month(payload(), 2026, 3, dt.date(2026, 3, 28))) == 1
    with pytest.raises(ValueError):
        parse_month({'unexpected': []}, 2026, 3, dt.date(2026, 3, 28))


def test_reciprocal_results_draws_and_doubleheader_order():
    date = dt.date(2026, 3, 28)
    games = parse_month(payload(suffix='2', score='1', other='3'), 2026, 3, date)
    games += parse_month(payload(suffix='1', score='4', other='1'), 2026, 3, date)
    games += parse_month(payload(), 2026, 3, date)
    result = aggregate(games)
    assert len(result) == 10 and all(len(rows) == 9 for rows in result.values())
    kt, lg = result['KT']['LG'], result['LG']['KT']
    assert (kt['wins'], kt['losses'], kt['draws']) == (1, 1, 1)
    assert [g['result'] for g in kt['flow']] == ['무', '승', '패']
    assert [g['result'] for g in lg['flow']] == ['무', '패', '승']
    assert kt['batting_average'] is None and kt['era'] is None
    with pytest.raises(ValueError):
        aggregate(games + [games[0]])


def test_bad_final_score_and_wrong_month_are_rejected():
    with pytest.raises(ValueError):
        parse_month(payload(score='-'), 2026, 3, dt.date(2026, 3, 28))
    with pytest.raises(ValueError):
        parse_month(payload(), 2026, 4, dt.date(2026, 4, 28))
