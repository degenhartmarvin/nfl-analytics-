import unittest
from refresh_data import calculate, parse, rank, TEAMS

class PipelineTest(unittest.TestCase):
 def test_plain_csv_parser(self):
  raw=b'posteam,defteam,play_type,yards_gained,epa,success,game_id,drive,yardline_100,touchdown\nCIN,BAL,pass,21,0.7,1,g,1,18,1\n'
  self.assertEqual(len(parse(raw)),1)
 def test_rejects_incomplete_32_team_sample(self):
  row={"posteam":"CIN","defteam":"BAL","play_type":"pass","yards_gained":"21","epa":"0.7","success":"1","game_id":"g","drive":"1","yardline_100":"18","touchdown":"1"}
  with self.assertRaisesRegex(ValueError,"No valid plays"):
   calculate([row])
 def test_missing_columns_rejected(self):
  with self.assertRaisesRegex(ValueError,"Missing required columns"):
   calculate([{"posteam":"CIN"}])
if __name__=="__main__":unittest.main()
