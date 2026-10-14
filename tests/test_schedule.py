import unittest
import datetime as dt
from update_data import extract
class ScheduleTests(unittest.TestCase):
    def test_date_filter_and_games(self):
        html='''<table><tr><th>날짜</th><th>시간</th><th>경기</th><th>구장</th></tr>
        <tr><td>10.08(목)</td><td>18:30</td><td>KIA vs LG</td><td>잠실</td></tr>
        <tr><td>10.09(금)</td><td>14:00</td><td>KIA vs NC</td><td>창원</td></tr>
        <tr><td></td><td>14:00</td><td>LG vs 롯데</td><td>사직</td></tr></table>'''
        games=extract(html,dt.date(2026,10,9))
        self.assertEqual(len(games),2)
        self.assertEqual(games[0]['away'],'KIA')
        self.assertEqual(games[0]['home'],'NC')
        self.assertIsNone(games[0]['prediction'])
    def test_missing_rows(self):
        self.assertEqual(extract('<html></html>',dt.date(2026,10,9)),[])
if __name__=='__main__':unittest.main()
