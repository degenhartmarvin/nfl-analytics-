import unittest
from refresh_rb_data import build

class RunningBackPipelineTests(unittest.TestCase):
    def setUp(self):
        self.players=[{"gsis_id":"RB1","position":"RB","display_name":"Test Back","pfr_id":"TestBa00"}]
        self.pbp=[
          {"rusher_player_id":"RB1","posteam":"AAA","play_type":"run","rush_attempt":"1","yards_gained":"12","rush_touchdown":"0","first_down":"1","epa":"0.8","success":"1","yardline_100":"50","ydstogo":"5","down":"1","fumble":"0","fumble_lost":"0"},
          {"rusher_player_id":"RB1","posteam":"AAA","play_type":"run","rush_attempt":"1","yards_gained":"-2","rush_touchdown":"0","first_down":"0","epa":"-1.0","success":"0","yardline_100":"10","ydstogo":"2","down":"3","fumble":"1","fumble_lost":"1"},
          {"receiver_player_id":"RB1","posteam":"AAA","play_type":"pass","pass_attempt":"1","complete_pass":"1","yards_gained":"8","pass_touchdown":"0","first_down":"1","yards_after_catch":"5","epa":"0.5","success":"1"},
          {"receiver_player_id":"WR1","posteam":"AAA","play_type":"pass","pass_attempt":"1","complete_pass":"1","yards_gained":"20","epa":"0.6","success":"1"}
        ]

    def test_rushing_receiving_and_derived_metrics(self):
        rows=build(self.pbp,self.players)
        rb=next(x for x in rows if x["player_id"]=="RB1")
        self.assertEqual(rb["carries"],2)
        self.assertEqual(rb["rushing_yards"],10)
        self.assertEqual(rb["rushing_first_downs"],1)
        self.assertEqual(rb["targets"],1)
        self.assertEqual(rb["receptions"],1)
        self.assertEqual(rb["receiving_yards"],8)
        self.assertEqual(rb["scrimmage_yards"],18)
        self.assertEqual(rb["fumbles"],1)
        self.assertAlmostEqual(rb["yards_per_carry"],5.0)
        self.assertAlmostEqual(rb["epa_per_rush"],-0.1)
        self.assertAlmostEqual(rb["stuff_rate"],0.5)

    def test_ngs_and_pfr_advanced_stats_join(self):
        ngs=[{"season":"2026","week":"0","season_type":"REG","player_position":"RB","player_gsis_id":"RB1",
              "rush_yards_over_expected":"6.0","rush_yards_over_expected_per_att":"3.0",
              "efficiency":"3.2","percent_attempts_gte_eight_defenders":"0.25","avg_time_to_los":"2.8"}]
        pfr=[{"season":"2026","pos":"RB","pfr_id":"TestBa00","ybc":"4","yac":"7","brk_tkl":"2"}]
        rows=build(self.pbp,self.players,ngs,pfr)
        rb=rows[0]
        self.assertAlmostEqual(rb["ryoe"],6.0)
        self.assertAlmostEqual(rb["heavy_box_rate"],0.25)
        self.assertAlmostEqual(rb["yards_after_contact_per_carry"],3.5)
        self.assertAlmostEqual(rb["broken_tackles"],2)

    def test_non_rb_is_ignored(self):
        players=self.players+[{"gsis_id":"WR1","position":"WR","display_name":"Test Receiver"}]
        rows=build(self.pbp,players)
        self.assertFalse(any(x["player_id"]=="WR1" for x in rows))

if __name__=="__main__":
    unittest.main()
