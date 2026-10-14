import unittest
from team_rankings import parse_standings

class RankingsTests(unittest.TestCase):
    def test_valid_table(self):
        teams=['KT','삼성','KIA','LG','두산','SSG','NC','롯데','한화','키움']
        rows=''.join(f'<tr><td>{i}</td><td>{t}</td><td>10</td><td>5</td><td>5</td><td>0</td><td>0.500</td></tr>' for i,t in enumerate(teams,1))
        self.assertEqual(parse_standings('<table>'+rows+'</table>')[2]['team'],'KIA')
    def test_partial_table_is_rejected(self):
        self.assertEqual(parse_standings('<table><tr><td>3</td><td>KIA</td><td>10</td><td>5</td><td>5</td><td>0</td><td>0.500</td></tr></table>'),[])
