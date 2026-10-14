"""Validate externally supplied pregame roster snapshots; never label projected as official."""
import json
from pathlib import Path

VALID_STATUS = {'official', 'projected', 'unavailable'}

def load_lineups(path, game_date, games):
    path = Path(path)
    if not path.exists():
        return games
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('date') != game_date:
        return games
    for game in games:
        key = f"{game['away']}-{game['home']}"
        entry = data.get('games', {}).get(key)
        if not entry:
            continue
        status = entry.get('status', 'unavailable')
        if status not in VALID_STATUS:
            raise ValueError('Invalid lineup status')
        if status == 'unavailable':
            continue
        if not entry.get('source_url') or not entry.get('checked_at'):
            raise ValueError('Lineup requires source URL and checked timestamp')
        for side in ('away', 'home'):
            lineup = entry.get(side, [])
            if len(lineup) != 9 or len({p.get('name') for p in lineup}) != 9:
                raise ValueError('Lineup must contain 9 distinct players')
            if any(not p.get('name') or not p.get('position') for p in lineup):
                raise ValueError('Lineup player missing name or position')
        game['lineups'] = {'status':status,'source_url':entry['source_url'],
                           'checked_at':entry['checked_at'],
                           'away':entry['away'],'home':entry['home']}
        starters = entry.get('starting_pitchers')
        if starters and all(starters.get(side) for side in ('away','home')):
            game['starting_pitchers'] = starters
    return games
