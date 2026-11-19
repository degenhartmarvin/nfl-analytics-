#!/usr/bin/env python3
"""Build individual cornerback defensive-event snapshot from nflverse play-by-play."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
COVERAGE_URL="https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_season_def.csv"
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
 {"key":"defensive_penalty_yards","label":"Defensive Penalty Yards","category":"Discipline","format":"number","higher_is_better":False},
 {"key":"targets_allowed","label":"Targets Allowed","category":"Coverage Volume","format":"number","higher_is_better":None},
 {"key":"completions_allowed","label":"Completions Allowed","category":"Coverage Volume","format":"number","higher_is_better":False},
 {"key":"completion_rate_allowed","label":"Completion Rate Allowed","category":"Coverage Efficiency","format":"percent","higher_is_better":False},
 {"key":"yards_allowed","label":"Receiving Yards Allowed","category":"Coverage Volume","format":"number","higher_is_better":False},
 {"key":"yards_per_target_allowed","label":"Yards per Target Allowed","category":"Coverage Efficiency","format":"decimal","higher_is_better":False},
 {"key":"yards_per_completion_allowed","label":"Yards per Completion Allowed","category":"Coverage Efficiency","format":"decimal","higher_is_better":False},
 {"key":"touchdowns_allowed","label":"Receiving TDs Allowed","category":"Coverage Volume","format":"number","higher_is_better":False},
 {"key":"passer_rating_allowed","label":"Passer Rating Allowed","category":"Coverage Efficiency","format":"decimal","higher_is_better":False},
 {"key":"average_depth_of_target","label":"Average Depth of Target","category":"Coverage Profile","format":"decimal","higher_is_better":None},
 {"key":"air_yards_allowed","label":"Air Yards Allowed","category":"Coverage Profile","format":"number","higher_is_better":False},
 {"key":"yards_after_catch_allowed","label":"Yards After Catch Allowed","category":"Coverage Profile","format":"number","higher_is_better":False},
 {"key":"blitzes","label":"Blitzes","category":"Pass Rush","format":"number","higher_is_better":True},
 {"key":"hurries","label":"Hurries","category":"Pass Rush","format":"number","higher_is_better":True},
 {"key":"qb_knockdowns","label":"QB Knockdowns","category":"Pass Rush","format":"number","higher_is_better":True},
 {"key":"pressures","label":"Pressures","category":"Pass Rush","format":"number","higher_is_better":True},
 {"key":"missed_tackles","label":"Missed Tackles","category":"Tackling & Run Support","format":"number","higher_is_better":False},
 {"key":"missed_tackle_rate","label":"Missed Tackle Rate","category":"Tackling & Run Support","format":"percent","higher_is_better":False},
 {"key":"combined_tackles","label":"Combined Tackles","category":"Tackling & Run Support","format":"number","higher_is_better":True}
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

def build(pbp, player_rows, coverage_rows=()):
 roster={}
 for p in player_rows:
  pid=p.get("gsis_id") or p.get("player_id")
  if pid and str(p.get("position","")).upper()=="CB":
   roster[pid]=p
 pfr_to_gsis={p.get("pfr_id") or p.get("player_pfr_id"):pid for pid,p in roster.items() if p.get("pfr_id") or p.get("player_pfr_id")}
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
  add(row.get("interception_player_id"),"interceptions",team=team)
  sack=row.get("sack_player_id")
  if sack: add(sack,"sacks",1,team)
  else:
   for i in (1,2): add(row.get(f"half_sack_{i}_player_id"),"sacks",0.5,team)
  penalty_pid=row.get("penalty_player_id")
  if penalty_pid and row.get("penalty_team") and row.get("penalty_team")==team and truth(row.get("penalty")):
   add(penalty_pid,"defensive_penalties",team=team)
   add(penalty_pid,"defensive_penalty_yards",abs(num(row.get("penalty_yards")) or 0),team=team)

 # PFR advanced defense data is keyed by PFR ID, so join through nflverse's
 # player registry rather than fuzzy-matching names.
 coverage_by_id=defaultdict(list)
 for row in coverage_rows:
  if str(row.get("season",""))!=str(SEASON): continue
  pid=pfr_to_gsis.get(row.get("pfr_id"))
  if not pid: continue
  if str(row.get("pos","")).upper() not in ("CB","RCB","LCB","SCB","NCB"):
   continue
  coverage_by_id[pid].append(row)

 def summed(rows,key):
  vals=[num(r.get(key)) for r in rows]
  vals=[v for v in vals if v is not None]
  return sum(vals) if vals else None

 output=[]
 for pid,p in roster.items():
  s=stats[pid]
  crows=coverage_by_id.get(pid,[])
  if not any(s.values()) and not crows: continue
  # Prefer an explicit 2TM season aggregate if present; otherwise sum team rows.
  aggregate=[r for r in crows if r.get("tm")=="2TM"]
  chosen=aggregate[:1] if aggregate else crows
  def cv(key): return summed(chosen,key)
  def weighted_avg(key):
   vals=[(num(r.get(key)),num(r.get("g")) or 1) for r in chosen]
   vals=[(v,w) for v,w in vals if v is not None]
   return (sum(v*w for v,w in vals)/sum(w for _,w in vals)) if vals else None
  targets=cv("tgt"); completions=cv("cmp"); yards=cv("yds")
  team=teams[pid].most_common(1)[0][0] if teams[pid] else (chosen[0].get("tm") if chosen else p.get("team") or "")
  name=p.get("display_name") or p.get("full_name") or p.get("name") or pid
  row={"player_id":pid,"player_name":name,"team":team}
  for key in ("interceptions","passes_defended","forced_fumbles","solo_tackles","assisted_tackles","tackles_for_loss","qb_hits","defensive_penalties","defensive_penalty_yards"):
   row[key]=int(s[key])
  row["sacks"]=s["sacks"]
  row.update({
   "targets_allowed":targets,
   "targets":targets,
   "completions_allowed":completions,
   "completion_rate_allowed":(completions/targets if targets else None),
   "yards_allowed":yards,
   "yards_per_target_allowed":(yards/targets if targets else None),
   "yards_per_completion_allowed":(yards/completions if completions else None),
   "touchdowns_allowed":cv("td"),
   "passer_rating_allowed":weighted_avg("rat"),
   "average_depth_of_target":weighted_avg("dadot"),
   "air_yards_allowed":cv("air"),
   "yards_after_catch_allowed":cv("yac"),
   "blitzes":cv("bltz"),
   "hurries":cv("hrry"),
   "qb_knockdowns":cv("qbkd"),
   "pressures":cv("prss"),
   "missed_tackles":cv("m_tkl"),
   "missed_tackle_rate":weighted_avg("m_tkl_percent"),
   "combined_tackles":cv("comb")
  })
  output.append(row)
 for metric in METRICS:
  key=metric["key"]; valid=[p for p in output if p.get(key) is not None]
  if metric["higher_is_better"] is None: valid.sort(key=lambda p:p[key])
  else: valid.sort(key=lambda p:p[key],reverse=metric["higher_is_better"])
  previous=None; rank=0
  for index,p in enumerate(valid,1):
   if previous is None or p[key]!=previous: rank=index
   p[key+"_rank"]=rank; previous=p[key]
 return sorted(output,key=lambda p:(p.get("targets_allowed") or 0,p["passes_defended"]),reverse=True)

def main():
 pbp=parse(download(PBP_URL))
 players=parse(download(PLAYERS_URL))
 coverage=parse(download(COVERAGE_URL))
 data=build(pbp,players,coverage)
 if not data: raise RuntimeError("No CB defensive-event data produced; refusing to overwrite snapshot.")
 payload={"season":SEASON,"source":"nflverse PFR advanced defense + play-by-play + players registry",
  "source_url":COVERAGE_URL,"updated_at":datetime.now(timezone.utc).isoformat(),
  "player_count":len(data),"players":data,"metrics":METRICS,
  "limitations":[
   "Coverage allowed statistics are PFR charted defender-in-coverage values; they are not the NFL Next Gen Stats nearest-defender or coverage-responsibility model.",
   "Coverage snaps and yards per coverage snap are not included in this season-level PFR defense feed and are intentionally not estimated.",
   "Missed tackle rate and pass-rush pressure counts are PFR advanced charting fields; rates are only shown where the source provides them."
  ]}
 os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
 with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
 print(f"CB refresh OK: {len(pbp):,} plays + {len(coverage):,} PFR defense rows, {len(data)} cornerbacks saved to {OUT}")

if __name__=="__main__": main()
