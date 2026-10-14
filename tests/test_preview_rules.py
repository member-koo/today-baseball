import unittest
from preview_rules import TEAMS,validate_games,preview_status

class PreviewRulesTest(unittest.TestCase):
    def test_ten_teams(self): self.assertEqual(len(TEAMS),10)
    def test_all_matchups(self):
        validate_games([{'away':'KIA','home':'한화','time':'18:30'}, {'away':'LG','home':'두산','time':'18:30'}])
    def test_invalid_team(self):
        with self.assertRaises(ValueError):validate_games([{'away':'가상','home':'KIA'}])
    def test_no_fake_prediction(self):
        self.assertIn('미연결',preview_status({'prediction':None}))
if __name__=='__main__':unittest.main()
