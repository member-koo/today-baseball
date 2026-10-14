import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from data_quality import assess

class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.now=dt.datetime(2026,10,9,13,0,tzinfo=ZoneInfo('Asia/Seoul'))
        self.data={'game_date':'2026-10-09','updated_at':'2026-10-09T12:00:00+09:00','source':'https://www.koreabaseball.com/Schedule/Schedule.aspx','games':[]}
    def test_fresh(self): self.assertTrue(assess(self.data,self.now)['publishable'])
    def test_old_day(self):
        self.data['game_date']='2026-10-08'
        self.assertFalse(assess(self.data,self.now)['publishable'])
    def test_stale(self):
        self.data['updated_at']='2026-10-09T08:00:00+09:00'
        self.assertFalse(assess(self.data,self.now)['publishable'])
    def test_unverified_source(self):
        self.data['source']='https://example.com/'
        self.assertFalse(assess(self.data,self.now)['publishable'])
    def test_missing_date(self):
        del self.data['game_date']
        self.assertFalse(assess(self.data,self.now)['publishable'])
