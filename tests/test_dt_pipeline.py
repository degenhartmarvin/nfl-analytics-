import unittest
from refresh_dt_data import build

class DefensiveTacklePipelineTests(unittest.TestCase):
    def test_builds_joint_dt_ranking_and_pfr_stats(self):
        players = [
            {"gsis_id":"DT1","pfr_id":"PFR1","position":"DT","display_name":"Interior One","team":"CIN"},
            {"gsis_id":"NT1","pfr_id":"PFR2","position":"NT","display_name":"Nose One","team":"CIN"},
            {"gsis_id":"EDGE1","pfr_id":"PFR3","position":"DE","display_name":"Edge One","team":"CIN"}
        ]
        defense = [
            {"season":"2026","game_type":"REG","pfr_player_id":"PFR1","team":"CIN","def_sacks":"2","def_pressures":"8","def_times_hitqb":"4","def_times_hurried":"3","def_tackles_combined":"12","def_tackles_solo":"7","def_missed_tackles":"2"},
            {"season":"2026","game_type":"REG","pfr_player_id":"PFR2","team":"CIN","def_sacks":"1","def_pressures":"5","def_times_hitqb":"2","def_times_hurried":"2","def_tackles_combined":"8","def_tackles_solo":"5","def_missed_tackles":"1"}
        ]
        snaps = [
            {"season":"2026","game_type":"REG","game_id":"G1","team":"CIN","pfr_player_id":"PFR1","defense_snaps":"50","defense_pct":"0.5"},
            {"season":"2026","game_type":"REG","game_id":"G1","team":"CIN","pfr_player_id":"PFR2","defense_snaps":"40","defense_pct":"0.4"}
        ]
        pbp = [
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"1","defteam":"CIN","tackle_for_loss_1_player_id":"DT1","sack_player_id":"DT1","forced_fumble_player_1_player_id":"DT1"},
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"2","defteam":"CIN","tackle_for_loss_1_player_id":"NT1"}
        ]
        rows = build(pbp, players, defense, snaps)
        self.assertEqual({p["player_id"] for p in rows},{"DT1","NT1"})
        dt = next(p for p in rows if p["player_id"]=="DT1")
        nt = next(p for p in rows if p["player_id"]=="NT1")
        self.assertEqual(dt["sacks"],2)
        self.assertEqual(dt["pressures"],8)
        self.assertEqual(dt["qb_hits"],4)
        self.assertEqual(dt["hurries"],3)
        self.assertEqual(dt["tfls"],1)
        self.assertEqual(dt["defensive_snaps"],50)
        self.assertAlmostEqual(dt["defensive_snap_share"],0.5)
        self.assertEqual(dt["negative_plays_forced"],1)
        self.assertAlmostEqual(dt["negative_plays_forced_rate"],1/50)
        self.assertEqual(dt["games_played"],1)
        self.assertEqual(dt["sacks_per_game"],2)
        self.assertEqual(dt["pressures_per_game"],8)
        self.assertEqual(dt["qb_hits_per_game"],4)
        self.assertEqual(dt["hurries_per_game"],3)
        self.assertAlmostEqual(dt["qb_hits_per_100_def_snaps"],4/50*100)
        self.assertAlmostEqual(dt["hurries_per_100_def_snaps"],3/50*100)
        self.assertAlmostEqual(dt["pressure_to_sack_rate"],2/8)
        self.assertAlmostEqual(dt["tfls_per_100_def_snaps"],1/50*100)
        self.assertFalse(dt["interior_technique_01"])
        self.assertTrue(nt["interior_technique_01"])
        self.assertIsNone(dt["sack_rate"])
        self.assertIsNone(dt["pressure_rate"])
        self.assertIsNone(dt["double_team_rate"])
        self.assertEqual(dt["sacks_rank"],1)
        self.assertEqual(nt["sacks_rank"],2)

if __name__ == "__main__":
    unittest.main()
