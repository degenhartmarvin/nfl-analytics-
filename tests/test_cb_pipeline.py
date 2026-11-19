import unittest
from refresh_cb_data import build

class CornerbackPipelineTests(unittest.TestCase):
    def test_defensive_events_and_rankings(self):
        players=[
          {"gsis_id":"CB1","position":"CB","display_name":"Corner One"},
          {"gsis_id":"CB2","position":"CB","display_name":"Corner Two"},
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
        data=build(pbp,players)
        self.assertEqual(len(data),2)
        one=next(p for p in data if p["player_id"]=="CB1")
        two=next(p for p in data if p["player_id"]=="CB2")
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
