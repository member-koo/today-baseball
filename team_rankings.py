"""Parse the official KBO team standings without guessing missing values."""
import re
from bs4 import BeautifulSoup

TEAMS = {'KIA','한화','LG','두산','삼성','롯데','SSG','NC','KT','키움'}

def parse_standings(html):
    soup = BeautifulSoup(html, 'html.parser')
    for table in soup.select('table'):
        rows = table.select('tr')
        parsed = []
        for row in rows:
            values = [c.get_text(' ', strip=True) for c in row.find_all(['th','td'], recursive=False)]
            if len(values) < 7 or values[1] not in TEAMS or not values[0].isdigit():
                continue
            try:
                rank, played, wins, losses, draws = map(int, [values[0],values[2],values[3],values[4],values[5]])
                pct = float(values[6])
            except ValueError:
                continue
            if not (1 <= rank <= 10 and played == wins+losses+draws and 0 <= pct <= 1):
                continue
            parsed.append({'rank':rank,'team':values[1],'games':played,'wins':wins,'losses':losses,'draws':draws,'win_pct':pct})
        if len(parsed) == 10 and len({r['team'] for r in parsed}) == 10:
            return sorted(parsed,key=lambda r:r['rank'])
    return []
