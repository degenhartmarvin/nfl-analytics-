import unittest
from refresh_qb_data import build

class QuarterbackPipelineTests(unittest.TestCase):
    def setUp(self):
        self.players=[
            {"gsis_id":"QB1","position":"QB","display_name":"Test QB"},
            {"gsis_id":"WR1","position":"WR","display_name":"Test WR"},
        ]
        self.pbp=[
            {"passer_player_id":"QB1","posteam":"AAA","play_type":"pass","pass_attempt":"1","complete_pass":"1","yards_gained":"30","air_yards":"25","pass_touchdown":"1","first_down":"1","epa":"1.2","success":"1","cpoe":"3.0","qb_dropback":"1"},
            {"passer_player_id":"QB1","posteam":"AAA","play_type":"pass","pass_attempt":"1","complete_pass":"0","yards_gained":"0","air_yards":"10","interception":"1","epa":"-2.0","success":"0","cpoe":"-5.0","qb_dropback":"1"},
            {"passer_player_id":"QB1","posteam":"AAA","play_type":"pass","pass_attempt":"0","sack":"1","yards_gained":"-8","epa":"-1.0","success":"0","qb_dropback":"1"},
            {"rusher_player_id":"QB1","fumbler_player_id":"QB1","posteam":"AAA","play_type":"run","yards_gained":"15","rush_touchdown":"1","touchdown":"1","first_down":"1","fumble_lost":"0"},
        ]

    def test_qb_passing_and_rushing_metrics(self):
        rows=build(self.pbp,self.players)
        qb=next(x for x in rows if x["player_id"]=="QB1")
        self.assertEqual(qb["attempts"],2)
        self.assertEqual(qb["completions"],1)
        self.assertEqual(qb["passing_yards"],30)
        self.assertEqual(qb["passing_tds"],1)
        self.assertEqual(qb["interceptions"],1)
        self.assertEqual(qb["sacks_taken"],1)
        self.assertEqual(qb["dropbacks"],3)
        self.assertEqual(qb["rush_attempts"],1)
        self.assertEqual(qb["rushing_yards"],15)
        self.assertEqual(qb["rushing_tds"],1)
        self.assertEqual(qb["longest_rush"],15)
        self.assertAlmostEqual(qb["completion_rate"],0.5)
        self.assertAlmostEqual(qb["epa_per_dropback"],-0.6)
        self.assertAlmostEqual(qb["cpoe"],-1.0)

    def test_qbr_and_time_to_throw_are_joined_by_player_name(self):
        qbr=[{"season":"2026","season_type":"Regular","name_display":"Test QB","qbr_total":"72.4"}]
        ngs=[{"season":"2026","season_type":"REG","week":"0","player_display_name":"Test QB","avg_time_to_throw":"2.81"}]
        rows=build(self.pbp,self.players,qbr,ngs)
        qb=next(x for x in rows if x["player_id"]=="QB1")
        self.assertAlmostEqual(qb["qbr_total"],72.4)
        self.assertAlmostEqual(qb["time_to_throw"],2.81)

    def test_backup_below_half_team_attempts_is_excluded(self):
        players=self.players+[
            {"gsis_id":"QB2","position":"QB","display_name":"Backup QB"}
        ]
        pbp=self.pbp+[
            {"passer_player_id":"QB2","posteam":"AAA","play_type":"pass","pass_attempt":"1","complete_pass":"1","yards_gained":"5","air_yards":"4","qb_dropback":"1"}
        ]
        rows=build(pbp,players)
        self.assertTrue(any(x["player_id"]=="QB1" for x in rows))
        self.assertFalse(any(x["player_id"]=="QB2" for x in rows))

    def test_non_qb_is_not_included(self):
        rows=build(self.pbp,self.players)
        self.assertFalse(any(x["player_id"]=="WR1" for x in rows))

if __name__=="__main__":
    unittest.main()
