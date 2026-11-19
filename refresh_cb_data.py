#!/usr/bin/env python3
"""Build individual cornerback defensive-event snapshot from nflverse play-by-play."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
OUT=os.environ.get("NFL_CB_OUTPUT","public/data/cb_players_2026.json")

METRICS=[
 {"key":"interceptions","label":"Interceptions","category":"Ball Skills","format":"number","higher_is_better":True},
 {"key":"passes_defended","label":"Passes Defended / PBUs","category":"Ball Skills","format":"number","higher_is_better":True},
 {"key":"forced_fumbles","label":"Forced Fumbles","category":"Ball Skills","format":"number","higher_is_better":True},
 {"key":"solo_tackles","label":"Solo Tackles","category":"Tackling & Run Support","format":"number","higher_is_better":True},
 {"key":"assisted_tackles","label":"Assisted Tackles","category":"Tackling & Run Support","format":"number","higher_is_better":True},
 {"key":"tackles_for_loss","label":"Tackles for Loss","category":"Tackling & Run Support","format":"number","higher_is_better":True},
 {"key":"sacks","label":"Sacks","category":"Pass Rush","format":"decimal","higher_is_better":True},
 {"key":"qb_hits","label":"QB Hits","category":"Pass Rush","format":"number","higher_is_better":True},
 {"key":"defensive_penalties","label":"Defensive Penalties","category":"Discipline","format":"number","higher_is_better":False},
 {"key":"defensive_penalty_yards","label":"Defensive Penalty Yards","category":"Discipline","format":"number","higher_is_better":False}
]

def download(url):
 req=urllib.request.Request(url,headers={"User-Agent":"NFL-Analytics-CB-refresh/1.0"})
 with urllib.request.urlopen(req,timeout=150) as response: return response.read()

def parse(raw):
 if raw[:2]==b"\x1f\x8b": raw=gzip.decompress(raw)
 return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def truth(v): return str(v).strip().lower() in ("1","true","t","yes")

def num(v):
 try:
  if v is None or str(v).strip() in ("","NA","NaN"): return None
  return float(v)
 except (TypeError,ValueError): return None

def build(pbp, player_rows):
 roster={}
 for p in player_rows:
  pid=p.get("gsis_id") or p.get("player_id")
  if pid and str(p.get("position","")).upper()=="CB":
   roster[pid]=p
 stats=defaultdict(lambda:defaultdict(float))
 teams=defaultdict(Counter)

 def add(pid, key, amount=1, team=""):
  if pid not in roster: return
  stats[pid][key]+=amount
  if team: teams[pid][team]+=1

 for row in pbp:
  team=row.get("defteam") or ""
  for i in (1,2):
   add(row.get(f"solo_tackle_{i}_player_id"),"solo_tackles",team=team)
   add(row.get(f"tackle_for_loss_{i}_player_id"),"tackles_for_loss",team=team)
   add(row.get(f"qb_hit_{i}_player_id"),"qb_hits",team=team)
   add(row.get(f"pass_defense_{i}_player_id"),"passes_defended",team=team)
   add(row.get(f"forced_fumble_player_{i}_player_id"),"forced_fumbles",team=team)
  for i in (1,2,3,4):
   add(row.get(f"assist_tackle_{i}_player_id"),"assisted_tackles",team=team)
  for i in (1,2):
   add(row.get(f"tackle_with_assist_{i}_player_id"),"assisted_tackles",team=team)
  interception=row.get("interception_player_id")
  add(interception,"interceptions",team=team)
  sack=row.get("sack_player_id")
  if sack:
   add(sack,"sacks",1,team)
  else:
   for i in (1,2):
    add(row.get(f"half_sack_{i}_player_id"),"sacks",0.5,team)
  penalty_pid=row.get("penalty_player_id")
  if penalty_pid and row.get("penalty_team") and row.get("penalty_team")==team and truth(row.get("penalty")):
   add(penalty_pid,"defensive_penalties",team=team)
   add(penalty_pid,"defensive_penalty_yards",abs(num(row.get("penalty_yards")) or 0),team=team)

 output=[]
 for pid,s in stats.items():
  p=roster[pid]
  team=teams[pid].most_common(1)[0][0] if teams[pid] else (p.get("team") or "")
  name=p.get("display_name") or p.get("full_name") or p.get("name") or pid
  row={"player_id":pid,"player_name":name,"team":team}
  for key in ("interceptions","passes_defended","forced_fumbles","solo_tackles","assisted_tackles","tackles_for_loss","qb_hits","defensive_penalties","defensive_penalty_yards"):
   row[key]=int(s[key])
  row["sacks"]=s["sacks"]
  output.append(row)
 for metric in METRICS:
  key=metric["key"]; valid=[p for p in output if p.get(key) is not None]
  valid.sort(key=lambda p:p[key],reverse=metric["higher_is_better"])
  previous=None; rank=0
  for index,p in enumerate(valid,1):
   if previous is None or p[key]!=previous: rank=index
   p[key+"_rank"]=rank; previous=p[key]
 return sorted(output,key=lambda p:(p["passes_defended"],p["interceptions"]),reverse=True)

def main():
 pbp=parse(download(PBP_URL))
 players=parse(download(PLAYERS_URL))
 data=build(pbp,players)
 if not data: raise RuntimeError("No CB defensive-event data produced; refusing to overwrite snapshot.")
 payload={"season":SEASON,"source":"nflverse play-by-play + players registry (recorded defensive events)",
  "source_url":PBP_URL,"updated_at":datetime.now(timezone.utc).isoformat(),
  "player_count":len(data),"players":data,"metrics":METRICS,
  "limitations":[
   "Targets, completions, yards, touchdowns and passer rating allowed cannot be attributed to a specific CB from standard play-by-play; pass-defense events are recorded, but full coverage responsibility is not.",
   "Coverage snaps, target rate, yards per coverage snap, separation and open-target rate require participation/charting or Next Gen Stats coverage attribution not present in this feed.",
   "Missed tackles, run-stop rate and blitz/pressure rates require reliable opportunity or assignment data; raw recorded solo/assisted tackles, TFLs, sacks and QB hits are shown instead."
  ]}
 os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
 with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
 print(f"CB refresh OK: {len(pbp):,} plays, {len(data)} cornerbacks saved to {OUT}")

if __name__=="__main__": main()
