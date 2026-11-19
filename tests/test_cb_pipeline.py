import unittest
from refresh_cb_data import build

class CornerbackPipelineTests(unittest.TestCase):
    def test_defensive_events_and_rankings(self):
        players=[
          {"gsis_id":"CB1","pfr_id":"PFR1","position":"CB","display_name":"Corner One"},
          {"gsis_id":"CB2","pfr_id":"PFR2","position":"CB","display_name":"Corner Two"},
          {"gsis_id":"LB1","position":"LB","display_name":"Linebacker"}
        ]
        pbp=[
          {"defteam":"CIN","solo_tackle_1_player_id":"CB1","pass_defense_1_player_id":"CB1",
           "interception_player_id":"CB1","tackle_for_loss_1_player_id":"CB1","sack_player_id":"CB1",
           "penalty":"1","penalty_team":"CIN","penalty_player_id":"CB1","penalty_yards":"10"},
          {"defteam":"CIN","assist_tackle_1_player_id":"CB1","qb_hit_1_player_id":"CB1",
           "forced_fumble_player_1_player_id":"CB1","penalty":"0"},
          {"defteam":"BUF","solo_tackle_1_player_id":"CB2","pass_defense_1_player_id":"CB2",
           "half_sack_1_player_id":"CB2","half_sack_2_player_id":"CB2","penalty":"0"},
          {"defteam":"CIN","solo_tackle_1_player_id":"LB1","penalty":"0"}
        ]
        coverage=[{"season":"2026","pfr_id":"PFR1","pos":"RCB","tm":"CIN","tgt":"20","cmp":"10","yds":"100","td":"1","rat":"60.5","dadot":"8.0","air":"120","yac":"30","bltz":"5","hrry":"2","qbkd":"1","sk":"1","prss":"4","comb":"15","m_tkl":"3","m_tkl_percent":"0.15"}]
        snaps=[{"season":"2026","game_type":"REG","pfr_player_id":"PFR1","defense_snaps":"125"},{"season":"2026","game_type":"REG","pfr_player_id":"PFR2","defense_snaps":"75"},{"season":"2026","game_type":"POST","pfr_player_id":"PFR1","defense_snaps":"20"}]
        data=build(pbp,players,coverage,snaps)
        self.assertEqual(len(data),2)
        one=next(p for p in data if p["player_id"]=="CB1")
        two=next(p for p in data if p["player_id"]=="CB2")
        self.assertEqual(one["defensive_snaps"],125)
        self.assertEqual(two["defensive_snaps"],75)
        self.assertEqual(one["targets_allowed"],20)
        self.assertEqual(one["completions_allowed"],10)
        self.assertAlmostEqual(one["completion_rate_allowed"],0.5)
        self.assertAlmostEqual(one["yards_per_target_allowed"],5.0)
        self.assertEqual(one["touchdowns_allowed"],1)
        self.assertEqual(one["pressures"],4)
        self.assertAlmostEqual(one["missed_tackle_rate"],0.15)
        self.assertEqual(one["interceptions"],1)
        self.assertEqual(one["passes_defended"],1)
        self.assertEqual(one["solo_tackles"],1)
        self.assertEqual(one["assisted_tackles"],1)
        self.assertEqual(one["tackles_for_loss"],1)
        self.assertEqual(one["sacks"],1)
        self.assertEqual(one["qb_hits"],1)
        self.assertEqual(one["forced_fumbles"],1)
        self.assertEqual(one["defensive_penalties"],1)
        self.assertEqual(one["defensive_penalty_yards"],10)
        self.assertEqual(two["sacks"],1)
        self.assertEqual(one["interceptions_rank"],1)
        self.assertEqual(two["interceptions_rank"],2)

if __name__=="__main__":
    unittest.main()
