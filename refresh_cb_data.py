#!/usr/bin/env python3
"""Build individual cornerback defensive-event snapshot from nflverse play-by-play."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
COVERAGE_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_{SEASON}.csv"
SNAPS_URL=f"https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{SEASON}.csv"
OUT=os.environ.get("NFL_CB_OUTPUT","public/data/cb_players_2026.json")

METRICS=[
 {"key":"defensive_snaps","label":"Defensive Snaps","category":"Snap Counts","format":"number","higher_is_better":True},
 {"key":"defensive_snap_share","label":"Defensive Snap Share","category":"Snap Counts","format":"percent","higher_is_better":True},
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
 {"key":"targets_allowed","label":"Targets Allowed","category":"Coverage Volume","format":"number","higher_is_better":False},
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
 {"key":"combined_tackles","label":"Combined Tackles","category":"Tackling & Run Support","format":"number","higher_is_better":True},
 {"key":"targets_per_100_defensive_snaps","label":"Targets per 100 Defensive Snaps","category":"Coverage Efficiency","format":"decimal","higher_is_better":False},
 {"key":"yards_allowed_per_100_defensive_snaps","label":"Yards Allowed per 100 Defensive Snaps","category":"Coverage Efficiency","format":"decimal","higher_is_better":False},
 {"key":"touchdown_rate_allowed","label":"TD Rate Allowed","category":"Coverage Efficiency","format":"percent","higher_is_better":False},
 {"key":"interception_rate","label":"Interception Rate","category":"Ball Skills","format":"percent","higher_is_better":True},
 {"key":"pass_breakup_rate","label":"Pass Breakup Rate","category":"Ball Skills","format":"percent","higher_is_better":True},
 {"key":"forced_incompletion_rate","label":"Forced Incompletion Rate (INT + PBU)","category":"Ball Skills","format":"percent","higher_is_better":True},
 {"key":"yac_per_reception_allowed","label":"YAC per Reception Allowed","category":"Coverage Efficiency","format":"decimal","higher_is_better":False},
 {"key":"missed_tackles_per_game","label":"Missed Tackles per Game","category":"Tackling","format":"decimal","higher_is_better":False}
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

def build(pbp, player_rows, coverage_rows=(), snap_rows=()):
 roster={}
 for p in player_rows:
  pid=p.get("gsis_id") or p.get("player_id")
  if pid and str(p.get("position","")).upper()=="CB":
   roster[pid]=p
 pfr_to_gsis={p.get("pfr_id") or p.get("player_pfr_id"):pid for pid,p in roster.items() if p.get("pfr_id") or p.get("player_pfr_id")}
 snap_totals=defaultdict(float)
 player_teams=defaultdict(set)
 team_game_totals={}
 for row in snap_rows:
  if str(row.get("season","")).strip() != str(SEASON): continue
  if str(row.get("game_type","")).upper() != "REG": continue
  pfr_id=row.get("pfr_player_id") or row.get("player_pfr_id")
  pid=pfr_to_gsis.get(pfr_id)
  snaps=num(row.get("defense_snaps"))
  pct=num(row.get("defense_pct"))
  team=row.get("team") or ""
  game=row.get("game_id") or row.get("pfr_game_id") or ""
  if pid and snaps is not None:
   snap_totals[pid]+=snaps
   if team: player_teams[pid].add(team)
  if team and game and snaps is not None and pct is not None and pct>0:
   pct=pct/100 if pct>1 else pct
   key=(team,game)
   team_game_totals[key]=max(team_game_totals.get(key,0),snaps/pct)
 team_season_totals=defaultdict(float)
 for (team,game),total in team_game_totals.items():
  team_season_totals[team]+=total
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
  # Weekly PFR defensive rows use pfr_player_id and are already game-level.
  pid=pfr_to_gsis.get(row.get("pfr_player_id") or row.get("pfr_id"))
  if not pid: continue
  if str(row.get("game_type","REG")).upper() != "REG": continue
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
  # Rebuild every season total from distinct weekly game rows on each refresh.
  # This is idempotent: reruns replace the snapshot instead of adding the same game twice.
  chosen=crows
  def cv(*keys):
   vals=[]
   for r in chosen:
    v=next((num(r.get(k)) for k in keys if num(r.get(k)) is not None),None)
    if v is not None: vals.append(v)
   return sum(vals) if vals else None
  def weighted_avg(key,weight_key="def_targets",fallback_key=None,fallback_weight="g"):
   vals=[]
   for r in chosen:
    value=num(r.get(key))
    if value is None and fallback_key: value=num(r.get(fallback_key))
    weight=num(r.get(weight_key))
    if weight is None or weight<=0: weight=num(r.get(fallback_weight)) or 0
    if value is not None and weight>0: vals.append((value,weight))
   return (sum(v*w for v,w in vals)/sum(w for _,w in vals)) if vals else None
  targets=cv("def_targets","tgt"); completions=cv("def_completions_allowed","cmp"); yards=cv("def_yards_allowed","yds")
  team=(max(chosen,key=lambda r:int(num(r.get("week")) or 0)).get("team") if chosen else "") or (teams[pid].most_common(1)[0][0] if teams[pid] else p.get("team") or "")
  name=p.get("display_name") or p.get("full_name") or p.get("name") or pid
  player_snaps=int(snap_totals.get(pid,0))
  team_snap_denominator=sum(team_season_totals[t] for t in player_teams.get(pid,set()))
  player_pfr_ids={p.get("pfr_id"),p.get("player_pfr_id")}
  games_played=len({(r.get("game_id") or r.get("pfr_game_id")) for r in snap_rows
                    if (r.get("pfr_player_id") or r.get("player_pfr_id")) in player_pfr_ids and
                    num(r.get("defense_snaps")) is not None and num(r.get("defense_snaps"))>0 and
                    str(r.get("game_type","REG")).upper()=="REG" and
                    str(r.get("season","")).strip()==str(SEASON)})
  row={"player_id":pid,"player_name":name,"team":team,"defensive_snaps":player_snaps,
       "defensive_snap_share":(player_snaps/team_snap_denominator if team_snap_denominator>0 else None)}
  for key in ("interceptions","passes_defended","forced_fumbles","solo_tackles","assisted_tackles","tackles_for_loss","qb_hits","defensive_penalties","defensive_penalty_yards"):
   row[key]=int(s[key])
  row["sacks"]=s["sacks"]
  row.update({
   "targets_allowed":targets,
   "targets":targets,
   "completions_allowed":completions,
   "completion_rate_allowed":(completions/targets if completions is not None and targets else None),
   "yards_allowed":yards,
   "yards_per_target_allowed":(yards/targets if yards is not None and targets else None),
   "yards_per_completion_allowed":(yards/completions if yards is not None and completions else None),
   "touchdowns_allowed":cv("def_receiving_td_allowed","td"),
   "passer_rating_allowed":weighted_avg("def_passer_rating_allowed","def_targets","rat"),
   "average_depth_of_target":weighted_avg("def_adot","def_targets","dadot"),
   "air_yards_allowed":cv("def_air_yards_completed","air"),
   "yards_after_catch_allowed":cv("def_yards_after_catch","yac"),
   "blitzes":cv("def_times_blitzed","bltz"),
   "hurries":cv("def_times_hurried","hrry"),
   "qb_knockdowns":cv("def_times_hitqb","qbkd"),
   "pressures":cv("def_pressures","prss"),
   "missed_tackles":cv("def_missed_tackles","m_tkl"),
   "missed_tackle_rate":weighted_avg("def_missed_tackle_pct", "def_tackles_combined", "m_tkl_percent", "comb"),
   "combined_tackles":cv("def_tackles_combined","comb"),
   "games_played":games_played,
   "targets_per_100_defensive_snaps":(targets/player_snaps*100 if targets is not None and player_snaps>0 else None),
   "yards_allowed_per_100_defensive_snaps":(yards/player_snaps*100 if yards is not None and player_snaps>0 else None),
   "touchdown_rate_allowed":(cv("def_receiving_td_allowed","td")/targets if targets and cv("def_receiving_td_allowed","td") is not None else None),
   "interception_rate":(s["interceptions"]/targets if targets else None),
   "pass_breakup_rate":(s["passes_defended"]/targets if targets else None),
   "forced_incompletion_rate":((s["interceptions"]+s["passes_defended"])/targets if targets else None),
   "yac_per_reception_allowed":(cv("def_yards_after_catch","yac")/completions if completions and cv("def_yards_after_catch","yac") is not None else None),
   "missed_tackles_per_game":(cv("def_missed_tackles","m_tkl")/games_played if games_played>0 and cv("def_missed_tackles","m_tkl") is not None else None)
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
 snaps=parse(download(SNAPS_URL))
 data=build(pbp,players,coverage,snaps)
 if not data: raise RuntimeError("No CB defensive-event data produced; refusing to overwrite snapshot.")
 payload={"season":SEASON,"source":"nflverse weekly PFR advanced defense + play-by-play + players registry",
  "source_url":COVERAGE_URL,"snap_counts_url":SNAPS_URL,"updated_at":datetime.now(timezone.utc).isoformat(),
  "player_count":len(data),"players":data,"metrics":METRICS,
  "limitations":[
   "Coverage allowed statistics are rebuilt by summing weekly PFR charted defender-in-coverage rows; they are not the NFL Next Gen Stats nearest-defender or coverage-responsibility model.",
   "Defensive snap totals are summed from the weekly PFR snap-count feed. Coverage snaps and yards per coverage snap are not included and are not estimated.",
   "Missed tackle rate and pass-rush pressure counts are PFR advanced charting fields; rates are only shown where the source provides them."
  ]}
 os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
 with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
 print(f"CB refresh OK: {len(pbp):,} plays + {len(coverage):,} weekly PFR defense rows + {len(snaps):,} snap rows, {len(data)} cornerbacks saved to {OUT}")

if __name__=="__main__": main()
