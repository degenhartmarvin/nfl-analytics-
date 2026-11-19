import unittest
from refresh_edge_data import build

class EdgePipelineTests(unittest.TestCase):
    def test_combines_de_and_olb_and_excludes_interior(self):
        players = [
            {"gsis_id":"DE1","pfr_id":"PFR1","position":"DE","display_name":"Defensive End"},
            {"gsis_id":"OLB1","pfr_id":"PFR2","position":"OLB","display_name":"Outside Linebacker"},
            {"gsis_id":"DT1","pfr_id":"PFR3","position":"DT","display_name":"Defensive Tackle"},
        ]
        pbp = [
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"1","defteam":"CIN",
             "sack_player_id":"DE1","tackle_for_loss_1_player_id":"DE1","qb_hit_1_player_id":"OLB1"},
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"2","defteam":"CIN",
             "half_sack_1_player_id":"OLB1","half_sack_2_player_id":"DE1"},
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"3","defteam":"CIN",
             "tackle_for_loss_1_player_id":"DT1"},
        ]
        defense = [
            {"season":"2026","game_type":"REG","pfr_player_id":"PFR1","team":"CIN","def_pressures":"5"},
            {"season":"2026","game_type":"REG","pfr_player_id":"PFR2","team":"CIN","def_pressures":"3"},
        ]
        snaps = [
            {"season":"2026","game_type":"REG","game_id":"G1","team":"CIN","pfr_player_id":"PFR1","defense_snaps":"50","defense_pct":"0.5"},
            {"season":"2026","game_type":"REG","game_id":"G1","team":"CIN","pfr_player_id":"PFR2","defense_snaps":"40","defense_pct":"0.4"},
        ]
        rows = build(pbp, players, defense, snaps)
        self.assertEqual({p["player_id"] for p in rows},{"DE1","OLB1"})
        de = next(p for p in rows if p["player_id"]=="DE1")
        olb = next(p for p in rows if p["player_id"]=="OLB1")
        self.assertEqual(de["sacks"],1.5)
        self.assertEqual(de["tfls"],1)
        self.assertEqual(de["negative_plays_forced"],2)
        self.assertAlmostEqual(de["negative_plays_forced_rate"],2/50)
        self.assertEqual(de["pressures"],5)
        self.assertEqual(olb["sacks"],0.5)
        self.assertEqual(olb["qb_hits"],1)
        self.assertIsNone(olb["pass_rush_win_rate"])
        self.assertIsNone(olb["double_team_rate"])
        self.assertEqual(de["sacks_rank"],1)
        self.assertEqual(olb["sacks_rank"],2)

if __name__ == "__main__":
    unittest.main()
