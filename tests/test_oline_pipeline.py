import unittest
from refresh_oline_data import calculate, TEAMS

class OLinePipelineTests(unittest.TestCase):
    def setUp(self):
        self.rows=[]
        def add(team, **kw):
            row={"posteam":team,"play_type":"run","yards_gained":"4","epa":"0.2","success":"1",
                 "pass_attempt":"0","sack":"0","rush_attempt":"1","game_id":"G1",
                 "down":"1","ydstogo":"10","yardline_100":"50","first_down":"0",
                 "touchdown":"0","rush_touchdown":"0","penalty":"0","penalty_team":team,
                 "penalty_type":"","penalty_yards":"0"}
            row.update({k:str(v) for k,v in kw.items()})
            self.rows.append(row)
        add("CIN",yards_gained=5,epa=0.4,success=1,first_down=1)
        add("CIN",yards_gained=-1,epa=-0.5,success=0,down=3,ydstogo=2)
        add("CIN",yards_gained=12,epa=0.8,success=1,down=1,ydstogo=10)
        self.rows.append({"posteam":"CIN","play_type":"pass","yards_gained":"-7","epa":"-1",
            "success":"0","pass_attempt":"0","sack":"1","qb_hit":"0","rush_attempt":"0","game_id":"G1",
            "qb_hit":"0","tackled_for_loss":"0","penalty":"0","penalty_team":"CIN","penalty_type":"","penalty_yards":"0"})
        self.rows.append({"posteam":"CIN","play_type":"pass","yards_gained":"8","epa":"0.3",
            "success":"1","pass_attempt":"1","sack":"0","qb_hit":"1","rush_attempt":"0","game_id":"G1",
            "penalty":"1","penalty_team":"CIN","penalty_type":"Offensive Holding","penalty_yards":"10"})
        self.rows.append({"posteam":"CIN","play_type":"no_play","yards_gained":"0","epa":"0",
            "success":"0","pass_attempt":"0","sack":"0","rush_attempt":"0","game_id":"G1",
            "penalty":"1","penalty_team":"CIN","penalty_type":"False Start","penalty_yards":"5"})
        for team in TEAMS:
            if team!="CIN":
                self.rows.append({"posteam":team,"play_type":"run","yards_gained":"3","epa":"0.1",
                    "success":"1","pass_attempt":"0","sack":"0","rush_attempt":"1","game_id":team+"G1",
                    "penalty":"0","penalty_team":team,"penalty_type":"","penalty_yards":"0"})

    def test_pass_protection_and_rushing_outcomes(self):
        data=calculate(self.rows)
        cin=next(x for x in data if x["team"]=="CIN")
        self.assertEqual(cin["sacks_allowed"],1)
        self.assertEqual(cin["dropbacks"],2)
        self.assertAlmostEqual(cin["sack_rate"],0.5)
        self.assertEqual(cin["pressures_allowed"],2)
        self.assertAlmostEqual(cin["pressure_rate"],1.0)
        self.assertEqual(cin["tfls_allowed"],1)
        self.assertAlmostEqual(cin["tfl_rate"],1/3)
        self.assertEqual(cin["carries_faced"],3)
        self.assertAlmostEqual(cin["yards_per_carry"],16/3)
        self.assertAlmostEqual(cin["stuff_rate"],1/3)
        self.assertAlmostEqual(cin["explosive_run_rate"],1/3)
        self.assertEqual(cin["short_yardage_attempts"],1)
        self.assertEqual(cin["short_yardage_conversion_rate"],0)

    def test_penalties_count_only_offensive_line_categories(self):
        cin=next(x for x in calculate(self.rows) if x["team"]=="CIN")
        self.assertEqual(cin["holding_penalties"],1)
        self.assertEqual(cin["false_start_penalties"],1)
        self.assertNotIn("oline_penalty_yards",cin)

    def test_all_32_teams_returned(self):
        self.assertEqual(len(calculate(self.rows)),32)

if __name__=="__main__":
    unittest.main()
