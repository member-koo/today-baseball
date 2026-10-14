import datetime as dt
from pathlib import Path
from update_data import extract


def test_offline_schedule_two_games():
    html = (Path(__file__).parent / 'fixtures' / 'kbo_schedule_sample.html').read_text(encoding='utf-8')
    games = extract(html, dt.date(2026, 10, 9))
    assert len(games) == 2
    assert games[0]['away'] == 'KIA' and games[0]['home'] == 'NC'
    assert games[0]['time'] == '14:00'
    assert games[1]['venue'] == '사직'
