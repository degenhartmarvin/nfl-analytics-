import unittest
from refresh_edge_data import build, parse_savant, parse_espn_win_rates

class EdgePipelineTests(unittest.TestCase):
    def test_combines_de_and_olb_and_excludes_interior(self):
        players = [
            {"gsis_id":"DE1","pfr_id":"PFR1","position":"DE","display_name":"Defensive End"},
            {"gsis_id":"OLB1","pfr_id":"PFR2","position":"OLB","display_name":"Outside Linebacker"},
            {"gsis_id":"DT1","pfr_id":"PFR3","position":"DT","display_name":"Defensive Tackle"},
        ]
        pbp = [
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"1","defteam":"CIN",
             "sack_player_id":"DE1","tackle_for_loss_1_player_id":"DE1","qb_hit_1_player_id":"OLB1","forced_fumble_player_1_player_id":"DE1"},
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"2","defteam":"CIN",
             "half_sack_1_player_id":"OLB1","half_sack_2_player_id":"DE1"},
            {"season":"2026","game_type":"REG","game_id":"G1","play_id":"3","defteam":"CIN",
             "tackle_for_loss_1_player_id":"DT1"},
        ]
        defense = [
            {"season":"2026","game_type":"REG","pfr_player_id":"PFR1","team":"CIN","def_pressures":"5","def_times_hurried":"3","def_times_hitqb":"1","def_times_blitzed":"4","def_tackles_combined":"10","def_missed_tackles":"2"},
            {"season":"2026","game_type":"REG","pfr_player_id":"PFR2","team":"CIN","def_pressures":"3","def_times_hurried":"2","def_times_hitqb":"1","def_times_blitzed":"2","def_tackles_combined":"8","def_missed_tackles":"1"},
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
        self.assertEqual(de["hurries"],3)
        self.assertEqual(de["knockdowns"],1)
        self.assertEqual(de["blitzes"],4)
        self.assertEqual(de["combined_tackles"],10)
        self.assertEqual(de["missed_tackles"],2)
        self.assertAlmostEqual(de["missed_tackle_rate"],2/12)
        self.assertEqual(de["forced_fumbles"],1)
        self.assertEqual(de["defensive_snaps"],50)
        self.assertAlmostEqual(de["defensive_snap_share"],0.5)
        self.assertAlmostEqual(de["sacks_per_game"],1.5)
        self.assertEqual(olb["sacks"],0.5)
        self.assertEqual(olb["qb_hits"],1)
        self.assertIsNone(olb["pass_rush_win_rate"])
        self.assertIsNone(olb["double_team_rate"])
        self.assertEqual(de["sacks_rank"],1)
        self.assertEqual(olb["sacks_rank"],2)

    def test_pass_rush_rates_stay_blank_without_matching_snap_source(self):
        players = [{"gsis_id":"EDGE1","pfr_id":"PFR1","position":"DE","display_name":"Test Edge"}]
        defense = [{"season":"2026","game_type":"REG","pfr_player_id":"PFR1","team":"CIN","def_pressures":"6"}]
        snaps = [{"season":"2026","game_type":"REG","game_id":"G1","team":"CIN","pfr_player_id":"PFR1","defense_snaps":"60","defense_pct":"0.6"}]
        pbp = [{"season":"2026","game_type":"REG","game_id":"G1","play_id":"1","defteam":"CIN","sack_player_id":"EDGE1"}]
        savant = {"testedge":{"pass_rush_snaps":100,"savant_pressures":8,"savant_sacks":4}}
        espn = {"pass_rush_win_rate":{"testedge":0.25},"run_stop_win_rate":{"testedge":0.30}}
        row = build(pbp, players, defense, snaps, savant, espn)[0]
        self.assertEqual(row["pass_rush_snaps"],100)
        self.assertAlmostEqual(row["sack_rate"],1/100)
        self.assertAlmostEqual(row["pressure_rate"],6/100)
        self.assertAlmostEqual(row["pressure_per_defensive_snap"],6/60)
        self.assertAlmostEqual(row["sacks_per_defensive_snap"],1/60)
        self.assertAlmostEqual(row["pass_rush_win_rate"],0.25)
        self.assertAlmostEqual(row["run_stop_win_rate"],0.30)
        self.assertIsNone(row["quick_pressure_rate"])

    def test_external_html_sources_parse_edge_leaderboards(self):
        savant_html = """
        <table><tr><th>Rank</th><th>Player</th><th>Pos</th><th>Team</th><th>Pressure %</th><th>Pressures</th><th>Sacks</th><th>QB Hits</th><th>Pass Rushes</th></tr>
        <tr><td>1</td><td>Test Edge</td><td>EDGE</td><td>CIN</td><td>10.0%</td><td>10</td><td>4.0</td><td>6</td><td>100</td></tr></table>
        """
        espn_html = """
        <h3>Edge rushers — pass rush win rate</h3>
        <table><tr><th>#</th><th>Move</th><th>Player</th><th>Team</th><th>Win rate</th><th>Won / snaps</th></tr>
        <tr><td>1</td><td>new</td><td>Test Edge</td><td>CIN</td><td>25%</td><td>25/100</td></tr></table>
        <h3>Edge rushers — run stop win rate</h3>
        <table><tr><th>#</th><th>Move</th><th>Player</th><th>Team</th><th>Win rate</th><th>Won / snaps</th></tr>
        <tr><td>1</td><td>new</td><td>Test Edge</td><td>CIN</td><td>30%</td><td>30/100</td></tr></table>
        """
        savant = parse_savant(savant_html)
        espn = parse_espn_win_rates(espn_html)
        self.assertEqual(savant["testedge"]["pass_rush_snaps"],100)
        # Current NFL/Savant layout combines position and team into one cell.
        combined_layout = """
        <table><tr><th>Rank</th><th>Player</th><th>Pos/Team</th><th>Pressure %</th><th>Pressures</th><th>Sacks</th><th>QB Hits</th><th>Pass Rushes</th></tr>
        <tr><td>1</td><td>Maxx Crosby</td><td>EDGELV</td><td>9.0%</td><td>27</td><td>5.0</td><td>21</td><td>299</td></tr>
        </table>
        """
        combined = parse_savant(combined_layout)
        self.assertEqual(combined["maxxcrosby"]["pass_rush_snaps"],299)
        self.assertAlmostEqual(espn["pass_rush_win_rate"]["testedge"],0.25)
        self.assertAlmostEqual(espn["run_stop_win_rate"]["testedge"],0.30)
        # The ESPN season leaderboard contains 20 edge pass-rush entries and 10 run-stop entries.
        pr_rows = "".join(
            f"<tr><td>{i}</td><td>move</td><td>Pass Edge {i}</td><td>CIN</td><td>{30-i}%</td><td>30/100</td></tr>"
            for i in range(1, 21)
        )
        rs_rows = "".join(
            f"<tr><td>{i}</td><td>move</td><td>Run Edge {i}</td><td>CIN</td><td>{20-i}%</td><td>20/100</td></tr>"
            for i in range(1, 11)
        )
        full_espn_html = (
            "<h3>Edge rushers — pass rush win rate</h3><table>" + pr_rows + "</table>"
            "<h3>Edge rushers — run stop win rate</h3><table>" + rs_rows + "</table>"
        )
        full_espn = parse_espn_win_rates(full_espn_html)
        self.assertEqual(len(full_espn["pass_rush_win_rate"]), 20)
        self.assertEqual(len(full_espn["run_stop_win_rate"]), 10)

if __name__ == "__main__":
    unittest.main()
