import unittest
from insight_engine import build_insights

class TestInsights(unittest.TestCase):
    def test_missing_stats_no_fake_players(self):
        notes=build_insights({'away':'KIA','home':'한화'})
        self.assertIn('보류', notes[0])
        self.assertIn('임의', notes[-1])
    def test_prediction_uses_actual_values(self):
        g={'away':'KIA','home':'한화','prediction':{'expected_away_runs':5.25,'expected_home_runs':4.1}}
        notes=build_insights(g)
        self.assertIn('5.25', notes[0])
        self.assertIn('선발투수',notes[1])
    def test_official_lineup_no_invented_matchup(self):
        g={'away':'KIA','home':'한화','lineups':{'status':'official'}}
        self.assertIn('개별 선수 상성 분석',build_insights(g)[-1])

if __name__=='__main__': unittest.main()
