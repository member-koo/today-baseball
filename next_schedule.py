"""Find the nearest officially listed game day within the current season year."""
import datetime as dt
import json
import re
from bs4 import BeautifulSoup
from head_to_head import API, TEAMS
from player_records import request

def candidate_dates(payload,year,month,after):
    if not isinstance(payload,dict) or not isinstance(payload.get('rows'),list):
        raise ValueError('Monthly schedule response unverified')
    active=None;dates=set()
    for item in payload['rows']:
        cells=item['row']
        for cell in cells:
            if cell.get('Class')=='day':
                match=re.search(r'(\d{2})\.(\d{2})',cell.get('Text',''))
                if not match:raise ValueError('Schedule date missing')
                active=dt.date(year,int(match[1]),int(match[2]))
        if active is None or active.month!=month:raise ValueError('Schedule month mismatch')
        if active<=after:continue
        play=next((c.get('Text','') for c in cells if c.get('Class')=='play'),'')
        soup=BeautifulSoup(play,'html.parser')
        teams=[span.get_text(strip=True) for span in soup.find_all('span',recursive=False)]
        if len(teams)==2 and all(team in TEAMS for team in teams) and teams[0]!=teams[1]:dates.add(active)
    return sorted(dates)

def find_next(session,date,fetch_day):
    # Stop at year end: an unannounced next season must not appear as this season.
    for month in range(date.month,13):
        payload=json.loads(request(session,'POST',API,data=dict(leId='1',srIdList='0,3,4,5,6,7,9',seasonId=str(date.year),gameMonth=f'{month:02}',teamId='')).content.decode('utf-8-sig'))
        for day in candidate_dates(payload,date.year,month,date):
            games=[g for g in fetch_day(day) if not g['cancelled'] and not g['final']]
            if games:return day,games
    return None
