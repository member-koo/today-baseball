import datetime as dt
import unittest
from prediction_model import validate_stats, predict, attach_predictions, TEAMS

DATE=dt.date(2026,10,9)
def sample():
    return {'season':2026,'as_of':'2026-10-07','source':'https://www.koreabaseball.com/Record/Team/Hitter/Basic1.aspx',
            'teams':{t:{'games':120,'runs_scored':600,'runs_allowed':600} for t in TEAMS}}

class TestPrediction(unittest.TestCase):
    def test_valid(self):
        self.assertTrue(validate_stats(sample(),DATE))
    def test_no_future_leak(self):
        s=sample();s['as_of']='2026-10-09'
        with self.assertRaises(ValueError): validate_stats(s,DATE)
    def test_missing_team(self):
        s=sample();del s['teams']['KIA']
        with self.assertRaises(ValueError): validate_stats(s,DATE)
    def test_predictions_are_bounded(self):
        p=predict({'away':'KIA','home':'한화'},sample(),DATE)
        self.assertGreaterEqual(p['home_win_pct'],0)
        self.assertLessEqual(p['home_win_pct'],100)
        self.assertEqual(p['stats_as_of'],'2026-10-07')
    def test_no_file_no_prediction(self):
        games=[{'away':'KIA','home':'한화','prediction':None}]
        self.assertFalse(attach_predictions(games,DATE,'/nonexistent/stats.json'))
        self.assertIsNone(games[0]['prediction'])
if __name__=='__main__': unittest.main()
