#!/usr/bin/env python3
"""Build team-level offensive-line unit snapshot from nflverse play-by-play.

Only directly observable team outcomes are published. Pressure/hurry/individual
blocking grades and Adjusted Line Yards are intentionally not inferred from PBP.
"""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
OUT=os.environ.get("NFL_OLINE_OUTPUT","public/data/oline_2026.json")
TEAMS=["ARI","ATL","BAL","BUF","CAR","CHI","CIN","CLE","DAL","DEN","DET","GB","HOU","IND","JAX","KC","LA","LAC","LV","MIA","MIN","NE","NO","NYG","NYJ","PHI","PIT","SEA","SF","TB","TEN","WAS"]

METRICS=[
 {"id":"sacks_allowed","name":"Sacks Allowed","category":"Pass Protection","unit":"Sacks","higher_is_better":False},
 {"id":"sack_rate","name":"Sack Rate Allowed","category":"Pass Protection","unit":"% Dropbacks","higher_is_better":False},
 {"id":"sack_yards_lost","name":"Sack Yards Lost","category":"Pass Protection","unit":"Yards","higher_is_better":False},
 {"id":"pressures_allowed","name":"Pressures Allowed (Sacks + QB Hits)","category":"Pass Protection","unit":"Pressures","higher_is_better":False},
 {"id":"pressure_rate","name":"Pressure Rate Allowed (Sacks + QB Hits)","category":"Pass Protection","unit":"% Dropbacks","higher_is_better":False},
 {"id":"pass_attempts","name":"Pass Attempts Faced","category":"Volume","unit":"Attempts","higher_is_better":None},
 {"id":"carries_faced","name":"Run-Block Opportunities (Carries)","category":"Volume","unit":"Carries","higher_is_better":None},
 {"id":"rush_yards","name":"Team Rushing Yards","category":"Run Game Outcomes","unit":"Yards","higher_is_better":True},
 {"id":"yards_per_carry","name":"Rushing Yards per Carry","category":"Run Game Outcomes","unit":"Yards/Carry","higher_is_better":True},
 {"id":"run_success_rate","name":"Run Success Rate","category":"Run Game Outcomes","unit":"% Runs","higher_is_better":True},
 {"id":"stuff_rate","name":"Stuff Rate (0 or Fewer Yards)","category":"Run Game Outcomes","unit":"% Runs","higher_is_better":False},
 {"id":"explosive_run_rate","name":"Explosive Run Rate (10+ Yards)","category":"Run Game Outcomes","unit":"% Runs","higher_is_better":True},
 {"id":"rush_epa_per_play","name":"Rushing EPA per Play","category":"Run Game Outcomes","unit":"EPA/Run","higher_is_better":True},
 {"id":"rush_first_down_rate","name":"Rushing First Down Rate","category":"Run Game Outcomes","unit":"% Runs","higher_is_better":True},
 {"id":"short_yardage_attempts","name":"3rd/4th & 2 or Less Run Attempts","category":"Short Yardage & Power","unit":"Attempts","higher_is_better":None},
 {"id":"short_yardage_conversion_rate","name":"Short-Yardage Conversion Rate","category":"Short Yardage & Power","unit":"% Attempts","higher_is_better":True},
 {"id":"goal_line_td_rate","name":"Goal-Line Rushing TD Rate","category":"Short Yardage & Power","unit":"% Attempts","higher_is_better":True},
 {"id":"holding_penalties","name":"Offensive Holding Penalties","category":"Discipline","unit":"Penalties","higher_is_better":False},
 {"id":"false_start_penalties","name":"False Start Penalties","category":"Discipline","unit":"Penalties","higher_is_better":False},
 {"id":"tfls_allowed","name":"Tackles for Loss Allowed","category":"Run Blocking","unit":"TFLs","higher_is_better":False},
 {"id":"tfl_rate","name":"TFL Rate Allowed","category":"Run Blocking","unit":"% Runs","higher_is_better":False},
 {"id":"rush_yards_before_contact","name":"Rush Yards Before Contact","category":"Run Blocking","unit":"Yards","higher_is_better":True},
 {"id":"yards_before_contact_per_carry","name":"Yards Before Contact per Carry","category":"Run Blocking","unit":"Yards/Carry","higher_is_better":True}
]

def fnum(v):
 try:
  if v is None or str(v).strip() in ("","NA","NaN"): return None
  return float(v)
 except (ValueError,TypeError): return None

def truth(v): return str(v).strip().lower() in ("1","true","t","yes")

def parse(raw):
 if raw[:2]==b"\x1f\x8b": raw=gzip.decompress(raw)
 return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def calculate(rows):
 if not rows: raise ValueError("Empty play-by-play dataset")
 required={"posteam","play_type","yards_gained","epa","success","pass_attempt","sack","rush_attempt"}
 missing=required-set(rows[0])
 if missing: raise ValueError("Missing required PBP columns: "+", ".join(sorted(missing)))
 stats=defaultdict(lambda:defaultdict(float))
 games=defaultdict(set)
 for r in rows:
  team=r.get("posteam")
  if team not in TEAMS: continue
  if r.get("game_id"): games[team].add(r["game_id"])
  s=stats[team]; kind=r.get("play_type")
  if kind=="pass":
   if truth(r.get("pass_attempt")):
    s["pass_attempts"]+=1; s["dropbacks"]+=1
   if truth(r.get("sack")):
    s["sacks_allowed"]+=1
    s["sack_yards_lost"]+=abs(fnum(r.get("yards_gained")) or 0)
    s["dropbacks"]+=1
   if truth(r.get("qb_hit")): s["qb_hits_allowed"]+=1
  elif kind=="run" and truth(r.get("rush_attempt")):
   yards=fnum(r.get("yards_gained"))
   if yards is None: continue
   s["carries_faced"]+=1;s["rush_yards"]+=yards
   if truth(r.get("tackled_for_loss")) or yards<0: s["tfls_allowed"]+=1
   s["run_success_total"]+=fnum(r.get("success")) or 0
   s["rush_epa_total"]+=fnum(r.get("epa")) or 0
   s["stuffed"]+=int(yards<=0);s["explosive_runs"]+=int(yards>=10)
   s["rush_first_downs"]+=int(truth(r.get("first_down")) or truth(r.get("touchdown")))
   down=fnum(r.get("down")); togo=fnum(r.get("ydstogo")); yline=fnum(r.get("yardline_100"))
   if down in (3,4) and togo is not None and togo<=2:
    s["short_yardage_attempts"]+=1
    s["short_yardage_conversions"]+=int(truth(r.get("first_down")) or truth(r.get("touchdown")))
   if yline is not None and yline<=5:
    s["goal_line_attempts"]+=1
    s["goal_line_tds"]+=int(truth(r.get("rush_touchdown")) or truth(r.get("touchdown")))
  # Count offensive penalties attributed to the offense, not defensive penalties.
  pteam=r.get("penalty_team") or team
  ptype=(r.get("penalty_type") or "").lower()
  if pteam==team and truth(r.get("penalty")):
   if "holding" in ptype:
    s["holding_penalties"]+=1;s["oline_penalty_yards"]+=abs(fnum(r.get("penalty_yards")) or 0)
   elif "false start" in ptype:
    s["false_start_penalties"]+=1;s["oline_penalty_yards"]+=abs(fnum(r.get("penalty_yards")) or 0)
 out=[]
 for team in TEAMS:
  s=stats[team]; carries=s["carries_faced"]; dropbacks=s["dropbacks"]
  if not (carries or dropbacks): raise ValueError(f"No current season plays found for {team}")
  row={"team":team,"games":len(games[team]),"dropbacks":int(dropbacks),
   "pass_attempts":int(s["pass_attempts"]),"carries_faced":int(carries),
   "sacks_allowed":int(s["sacks_allowed"]),"sack_rate":s["sacks_allowed"]/dropbacks if dropbacks else None,
   "pressures_allowed":int(s["sacks_allowed"]+s["qb_hits_allowed"]),"pressure_rate":(s["sacks_allowed"]+s["qb_hits_allowed"])/dropbacks if dropbacks else None,
   "rush_yards":int(s["rush_yards"]),"yards_per_carry":s["rush_yards"]/carries if carries else None,
   "tfls_allowed":int(s["tfls_allowed"]),"tfl_rate":s["tfls_allowed"]/carries if carries else None,
   "rush_yards_before_contact":None,"yards_before_contact_per_carry":None,
   "run_success_rate":s["run_success_total"]/carries if carries else None,
   "stuff_rate":s["stuffed"]/carries if carries else None,
   "explosive_run_rate":s["explosive_runs"]/carries if carries else None,
   "rush_epa_per_play":s["rush_epa_total"]/carries if carries else None,
   "rush_first_down_rate":s["rush_first_downs"]/carries if carries else None,
   "short_yardage_attempts":int(s["short_yardage_attempts"]),
   "short_yardage_conversion_rate":s["short_yardage_conversions"]/s["short_yardage_attempts"] if s["short_yardage_attempts"] else None,
   "goal_line_td_rate":s["goal_line_tds"]/s["goal_line_attempts"] if s["goal_line_attempts"] else None,
   "holding_penalties":int(s["holding_penalties"]),"false_start_penalties":int(s["false_start_penalties"])}
  out.append(row)
 for m in METRICS:
  if m["higher_is_better"] is None: continue
  key=m["id"]; valid=[x for x in out if x.get(key) is not None]
  valid.sort(key=lambda x:x[key],reverse=m["higher_is_better"])
  prev=None; rank=0
  for i,x in enumerate(valid,1):
   if prev is None or x[key]!=prev: rank=i
   x[key+"_rank"]=rank;prev=x[key]
 return out

def main():
 req=urllib.request.Request(URL,headers={"User-Agent":"NFL-Analytics-Oline-refresh/1.0"})
 with urllib.request.urlopen(req,timeout=180) as response: rows=parse(response.read())
 data=calculate(rows)
 if len(data)!=32: raise RuntimeError(f"Expected 32 teams, got {len(data)}")
 payload={"season":SEASON,"source":"nflverse play-by-play; pressures = sacks + QB hits (proxy)",
  "source_url":URL,"updated_at":datetime.now(timezone.utc).isoformat(),"team_count":32,
  "plays_loaded":len(rows),"data":data,"metrics":METRICS,
  "limitations":["Pressure is defined as sacks plus QB hits; this is a proxy, not a charted pressure grade.",
  "Run-game values describe team rushing outcomes and are not pure offensive-line attribution.",
  "Adjusted Line Yards and individual blocking grades are not calculated."]}
 os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
 with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
 print(f"OLine refresh OK: {len(rows):,} plays, 32 teams saved to {OUT}")
if __name__=="__main__": main()
