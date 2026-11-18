#!/usr/bin/env python3
"""Refresh validated 32-team NFL PBP metrics from one nflverse release."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict
from datetime import datetime, timezone

SEASON = int(os.environ.get("NFL_SEASON", "2026"))
URL = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
OUT = os.environ.get("NFL_OUTPUT", "public/data/teams_2026.json")
TEAMS = sorted("ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LA LAC LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS".split())
METRICS = [
 {"id":"off_yards_per_play","name":"Offense Yards/Play","side":"offense","unit":"yds/play","higher_is_better":True},
 {"id":"off_epa_per_play","name":"Offense EPA/Play","side":"offense","unit":"EPA/play","higher_is_better":True},
 {"id":"off_success_rate","name":"Offense Success Rate","side":"offense","unit":"%","higher_is_better":True},
 {"id":"off_explosive_pass_rate","name":"Explosive Pass Rate (20+)","side":"offense","unit":"%","higher_is_better":True},
 {"id":"off_explosive_rush_rate","name":"Explosive Rush Rate (10+)","side":"offense","unit":"%","higher_is_better":True},
 {"id":"off_redzone_td_rate","name":"Red Zone TD Rate","side":"offense","unit":"% drives","higher_is_better":True},
 {"id":"def_yards_allowed_per_play","name":"Defense Yards/Play Allowed","side":"defense","unit":"yds/play","higher_is_better":False},
 {"id":"def_epa_allowed_per_play","name":"Defense EPA/Play Allowed","side":"defense","unit":"EPA/play","higher_is_better":False},
 {"id":"def_success_rate_allowed","name":"Defense Success Rate Allowed","side":"defense","unit":"%","higher_is_better":False},
 {"id":"def_explosive_pass_rate_allowed","name":"Explosive Pass Allowed (20+)","side":"defense","unit":"%","higher_is_better":False},
 {"id":"def_explosive_rush_rate_allowed","name":"Explosive Rush Allowed (10+)","side":"defense","unit":"%","higher_is_better":False},
 {"id":"def_redzone_td_rate_allowed","name":"Defense Red Zone TD Rate Allowed","side":"defense","unit":"% drives","higher_is_better":False},
 {"id":"off_pass_epa_per_play","name":"Passing EPA/Play","side":"offense","unit":"EPA/play","higher_is_better":True},
 {"id":"off_rush_epa_per_play","name":"Rushing EPA/Play","side":"offense","unit":"EPA/play","higher_is_better":True},
 {"id":"off_completion_rate","name":"Completion Rate","side":"offense","unit":"%","higher_is_better":True},
 {"id":"off_yards_per_pass_attempt","name":"Passing Yards/Attempt","side":"offense","unit":"yds/att","higher_is_better":True},
 {"id":"off_first_down_rate","name":"First Down Rate","side":"offense","unit":"% plays","higher_is_better":True},
 {"id":"off_third_down_rate","name":"3rd Down Conversion","side":"offense","unit":"%","higher_is_better":True},
 {"id":"off_fourth_down_rate","name":"4th Down Conversion","side":"offense","unit":"%","higher_is_better":True},
 {"id":"off_sack_rate_allowed","name":"Sack Rate Allowed","side":"offense","unit":"% dropbacks","higher_is_better":False},
 {"id":"off_turnovers_per_drive","name":"Turnovers per Drive","side":"offense","unit":"TO/drive","higher_is_better":False},
 {"id":"def_pass_epa_allowed","name":"Passing EPA Allowed/Play","side":"defense","unit":"EPA/play","higher_is_better":False},
 {"id":"def_rush_epa_allowed","name":"Rushing EPA Allowed/Play","side":"defense","unit":"EPA/play","higher_is_better":False},
 {"id":"def_completion_rate_allowed","name":"Completion Rate Allowed","side":"defense","unit":"%","higher_is_better":False},
 {"id":"def_yards_per_pass_attempt_allowed","name":"Passing Yards/Attempt Allowed","side":"defense","unit":"yds/att","higher_is_better":False},
 {"id":"def_first_down_rate_allowed","name":"First Down Rate Allowed","side":"defense","unit":"% plays","higher_is_better":False},
 {"id":"def_third_down_stop_rate","name":"3rd Down Stop Rate","side":"defense","unit":"%","higher_is_better":True},
 {"id":"def_fourth_down_stop_rate","name":"4th Down Stop Rate","side":"defense","unit":"%","higher_is_better":True},
 {"id":"def_sack_rate","name":"Sack Rate","side":"defense","unit":"% dropbacks","higher_is_better":True},
 {"id":"def_turnovers_per_drive","name":"Turnovers per Drive","side":"defense","unit":"TO/drive","higher_is_better":True},
 {"id":"off_yards_per_rush","name":"Rushing Yards per Attempt","side":"offense","unit":"yds/rush","higher_is_better":True},
 {"id":"off_explosive_play_rate","name":"Overall Explosive Play Rate","side":"offense","unit":"% plays","higher_is_better":True},
 {"id":"off_pass_play_share","name":"Pass Play Share","side":"offense","unit":"% plays","higher_is_better":None},
 {"id":"off_rush_play_share","name":"Rush Play Share","side":"offense","unit":"% plays","higher_is_better":None},
 {"id":"def_yards_per_rush_allowed","name":"Rushing Yards Allowed/Attempt","side":"defense","unit":"yds/rush","higher_is_better":False},
 {"id":"def_explosive_play_rate_allowed","name":"Overall Explosive Plays Allowed","side":"defense","unit":"% plays","higher_is_better":False},
 {"id":"def_pass_play_share_allowed","name":"Opponent Pass Play Share","side":"defense","unit":"% plays","higher_is_better":None},
 {"id":"def_rush_play_share_allowed","name":"Opponent Rush Play Share","side":"defense","unit":"% plays","higher_is_better":None},
 {"id":"off_avg_plays_per_drive","name":"Average Plays per Drive","side":"offense","unit":"plays/drive","higher_is_better":True},
 {"id":"off_avg_yards_per_drive","name":"Average Yards per Drive","side":"offense","unit":"yds/drive","higher_is_better":True},
 {"id":"off_drive_success_rate","name":"Drive Success Rate","side":"offense","unit":"% drives","higher_is_better":True},
 {"id":"off_three_and_out_rate","name":"3-and-Out Rate","side":"offense","unit":"% drives","higher_is_better":False},
 {"id":"def_avg_plays_per_drive_allowed","name":"Plays per Drive Allowed","side":"defense","unit":"plays/drive","higher_is_better":False},
 {"id":"def_avg_yards_per_drive_allowed","name":"Yards per Drive Allowed","side":"defense","unit":"yds/drive","higher_is_better":False},
 {"id":"def_drive_success_rate_allowed","name":"Drive Success Rate Allowed","side":"defense","unit":"% drives","higher_is_better":False},
 {"id":"def_three_and_out_rate","name":"Defensive 3-and-Out Rate","side":"defense","unit":"% drives","higher_is_better":True},
]
def fnum(x):
 try:
  if x is None or str(x).strip() in ("","NA","NaN"): return None
  return float(x)
 except (ValueError,TypeError): return None
def istrue(x): return str(x).strip().lower() in {"1","true","t","yes"}
def parse(raw):
 if raw[:2]==b"\x1f\x8b": raw=gzip.decompress(raw)
 return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
def calculate(rows):
 req={"posteam","defteam","play_type","yards_gained","epa","success","game_id","drive","yardline_100"}
 if not rows: raise ValueError("Empty dataset")
 missing=req-set(rows[0])
 if missing: raise ValueError("Missing required columns: "+", ".join(sorted(missing)))
 off=defaultdict(lambda:defaultdict(float)); de=defaultdict(lambda:defaultdict(float)); rz={}
 for r in rows:
  oteam, dteam=r.get("posteam"),r.get("defteam")
  kind=r.get("play_type")
  if oteam not in TEAMS or dteam not in TEAMS or kind not in ("pass","run"): continue
  yards,epa,success=fnum(r.get("yards_gained")),fnum(r.get("epa")),fnum(r.get("success"))
  if yards is None or epa is None or success is None: continue
  game,drive=r.get("game_id"),r.get("drive")
  a,b=off[oteam],de[dteam]
  for v in (a,b):
   v["plays"]+=1;v["yards"]+=yards;v["epa"]+=epa;v["success"]+=success
  if kind=="pass":
   a["pass"]+=1;b["pass"]+=1
   a["pass_yards_total"]+=yards;b["pass_yards_total"]+=yards
   if yards>=20:a["explosive_pass"]+=1;b["explosive_pass"]+=1
  else:
   a["rush"]+=1;b["rush"]+=1
   a["rush_yards_total"]+=yards;b["rush_yards_total"]+=yards
   if yards>=10:a["explosive_rush"]+=1;b["explosive_rush"]+=1
  # Optional advanced-stat fields: tolerate absent columns in older/synthetic fixtures.
  down=fnum(r.get("down")); first_down=istrue(r.get("first_down"))
  pass_attempt=istrue(r.get("pass_attempt")); complete=istrue(r.get("complete_pass"))
  sack=istrue(r.get("sack")); turnover=istrue(r.get("interception")) or istrue(r.get("fumble_lost"))
  if kind=="pass":
   a["pass_epa"]+=epa;b["pass_epa"]+=epa;a["pass_epa_n"]+=1;b["pass_epa_n"]+=1
   if pass_attempt:
    a["pass_attempts"]+=1;b["pass_attempts"]+=1
    a["pass_yards"]+=yards;b["pass_yards"]+=yards
    a["completions"]+=int(complete);b["completions"]+=int(complete)
   if sack:
    a["sacks_allowed"]+=1;b["sacks"]+=1
  if kind=="run":
   a["rush_epa"]+=epa;b["rush_epa"]+=epa;a["rush_epa_n"]+=1;b["rush_epa_n"]+=1
  a["first_downs"]+=int(first_down);b["first_downs_allowed"]+=int(first_down)
  if down==3:
   a["third_plays"]+=1;b["third_plays"]+=1
   a["third_converted"]+=int(first_down or istrue(r.get("touchdown")));b["third_converted"]+=int(first_down or istrue(r.get("touchdown")))
  if down==4:
   a["fourth_plays"]+=1;b["fourth_plays"]+=1
   a["fourth_converted"]+=int(first_down or istrue(r.get("touchdown")));b["fourth_converted"]+=int(first_down or istrue(r.get("touchdown")))
  if turnover:
   a["turnovers"]+=1;b["takeaways"]+=1
  rzkey=(oteam,game,drive)
  state=rz.setdefault(rzkey,{"in":False,"td":False,"def":dteam})
  yline=fnum(r.get("yardline_100"))
  if yline is not None and yline<=20:state["in"]=True
  if istrue(r.get("touchdown")) or istrue(r.get("pass_touchdown")) or istrue(r.get("rush_touchdown")):state["td"]=True
 for (team,game,drive),state in rz.items():
  if state["in"]:
   off[team]["rz_drives"]+=1
   if state["td"]:off[team]["rz_td"]+=1
   de[state["def"]]["rz_drives"]+=1
   if state["td"]:de[state["def"]]["rz_td"]+=1
 # Aggregate drive-level outcomes from the same PBP rows (pass/run plays).
 drives=defaultdict(lambda:{"plays":0,"yards":0.0,"first_downs":0,"td":False})
 for r in rows:
  t,game,drive=r.get("posteam"),r.get("game_id"),r.get("drive")
  if t not in TEAMS or not drive or r.get("play_type") not in ("pass","run"): continue
  y,fd=fnum(r.get("yards_gained")),istrue(r.get("first_down"))
  if y is None: continue
  ds=drives[(t,game,drive)];ds["plays"]+=1;ds["yards"]+=y;ds["first_downs"]+=int(fd)
  if istrue(r.get("touchdown")) or istrue(r.get("pass_touchdown")) or istrue(r.get("rush_touchdown")):ds["td"]=True
 for (t,game,drive),ds in drives.items():
  o=off[t];d=de[next((r.get("defteam") for r in rows if r.get("posteam")==t and r.get("game_id")==game and r.get("drive")==drive),None)]
  o["drive_count"]+=1;o["drive_plays"]+=ds["plays"];o["drive_yards"]+=ds["yards"]
  o["drive_success"]+=int(ds["first_down"]>0 or ds["td"]);o["three_and_out"]+=int(ds["plays"]<=3 and ds["first_downs"]==0 and not ds["td"])
  d["drive_count_allowed"]+=1;d["drive_plays_allowed"]+=ds["plays"];d["drive_yards_allowed"]+=ds["yards"]
  d["drive_success_allowed"]+=int(ds["first_downs"]>0 or ds["td"]);d["three_and_outs"]+=int(ds["plays"]<=3 and ds["first_downs"]==0 and not ds["td"])
 out=[]
 for t in TEAMS:
  o,d=off[t],de[t]
  if not o["plays"] or not d["plays"]:raise ValueError(f"No valid plays for {t}; aborting 32-team snapshot")
  out.append({"team":t,"off_yards_per_play":o["yards"]/o["plays"],"off_epa_per_play":o["epa"]/o["plays"],"off_success_rate":o["success"]/o["plays"],
   "off_explosive_pass_rate":o["explosive_pass"]/o["pass"] if o["pass"] else None,"off_explosive_rush_rate":o["explosive_rush"]/o["rush"] if o["rush"] else None,
   "off_redzone_td_rate":o["rz_td"]/o["rz_drives"] if o["rz_drives"] else None,
   "def_yards_allowed_per_play":d["yards"]/d["plays"],"def_epa_allowed_per_play":d["epa"]/d["plays"],"def_success_rate_allowed":d["success"]/d["plays"],
   "def_explosive_pass_rate_allowed":d["explosive_pass"]/d["pass"] if d["pass"] else None,"def_explosive_rush_rate_allowed":d["explosive_rush"]/d["rush"] if d["rush"] else None,
   "def_redzone_td_rate_allowed":d["rz_td"]/d["rz_drives"] if d["rz_drives"] else None,
   "off_pass_epa_per_play":o["pass_epa"]/o["pass_epa_n"] if o["pass_epa_n"] else None,"off_rush_epa_per_play":o["rush_epa"]/o["rush_epa_n"] if o["rush_epa_n"] else None,
   "off_completion_rate":o["completions"]/o["pass_attempts"] if o["pass_attempts"] else None,"off_yards_per_pass_attempt":o["pass_yards"]/o["pass_attempts"] if o["pass_attempts"] else None,
   "off_first_down_rate":o["first_downs"]/o["plays"],"off_third_down_rate":o["third_converted"]/o["third_plays"] if o["third_plays"] else None,
   "off_fourth_down_rate":o["fourth_converted"]/o["fourth_plays"] if o["fourth_plays"] else None,"off_sack_rate_allowed":o["sacks_allowed"]/(o["pass_attempts"]+o["sacks_allowed"]) if (o["pass_attempts"]+o["sacks_allowed"]) else None,
   "off_turnovers_per_drive":o["turnovers"]/max(1,len({(x.get("game_id"),x.get("drive")) for x in rows if x.get("posteam")==t})),
   "def_pass_epa_allowed":d["pass_epa"]/d["pass_epa_n"] if d["pass_epa_n"] else None,"def_rush_epa_allowed":d["rush_epa"]/d["rush_epa_n"] if d["rush_epa_n"] else None,
   "def_completion_rate_allowed":d["completions"]/d["pass_attempts"] if d["pass_attempts"] else None,"def_yards_per_pass_attempt_allowed":d["pass_yards"]/d["pass_attempts"] if d["pass_attempts"] else None,
   "def_first_down_rate_allowed":d["first_downs_allowed"]/d["plays"],"def_third_down_stop_rate":1-d["third_converted"]/d["third_plays"] if d["third_plays"] else None,
   "def_fourth_down_stop_rate":1-d["fourth_converted"]/d["fourth_plays"] if d["fourth_plays"] else None,"def_sack_rate":d["sacks"]/(d["pass_attempts"]+d["sacks"]) if (d["pass_attempts"]+d["sacks"]) else None,
   "def_turnovers_per_drive":d["takeaways"]/max(1,len({(x.get("game_id"),x.get("drive")) for x in rows if x.get("defteam")==t})),
   "off_yards_per_rush":o["rush_yards_total"]/o["rush"] if o["rush"] else None,
   "off_explosive_play_rate":(o["explosive_pass"]+o["explosive_rush"])/o["plays"],
   "off_pass_play_share":o["pass"]/o["plays"],"off_rush_play_share":o["rush"]/o["plays"],
   "def_yards_per_rush_allowed":d["rush_yards_total"]/d["rush"] if d["rush"] else None,
   "def_explosive_play_rate_allowed":(d["explosive_pass"]+d["explosive_rush"])/d["plays"],
   "def_pass_play_share_allowed":d["pass"]/d["plays"],"def_rush_play_share_allowed":d["rush"]/d["plays"],
   "off_avg_plays_per_drive":o["drive_plays"]/o["drive_count"] if o["drive_count"] else None,
   "off_avg_yards_per_drive":o["drive_yards"]/o["drive_count"] if o["drive_count"] else None,
   "off_drive_success_rate":o["drive_success"]/o["drive_count"] if o["drive_count"] else None,
   "off_three_and_out_rate":o["three_and_out"]/o["drive_count"] if o["drive_count"] else None,
   "def_avg_plays_per_drive_allowed":d["drive_plays_allowed"]/d["drive_count_allowed"] if d["drive_count_allowed"] else None,
   "def_avg_yards_per_drive_allowed":d["drive_yards_allowed"]/d["drive_count_allowed"] if d["drive_count_allowed"] else None,
   "def_drive_success_rate_allowed":d["drive_success_allowed"]/d["drive_count_allowed"] if d["drive_count_allowed"] else None,
   "def_three_and_out_rate":d["three_and_outs"]/d["drive_count_allowed"] if d["drive_count_allowed"] else None,
   "off_plays":int(o["plays"]),"def_plays":int(d["plays"])})
 return out
def rank(data):
 for m in METRICS:
  if m.get("higher_is_better") is None: continue
  key=m["id"];vals=[(x["team"],x.get(key)) for x in data]
  if any(v is None for _,v in vals):continue
  vals.sort(key=lambda kv:kv[1],reverse=m["higher_is_better"])
  last=None;ranknum=0
  for i,(team,value) in enumerate(vals,1):
   if last is None or value!=last:ranknum=i
   next(x for x in data if x["team"]==team)[key+"_rank"]=ranknum
   last=value
def refresh():
 request=urllib.request.Request(URL,headers={"User-Agent":"NFL-Analytics-data-refresh/1.0"})
 with urllib.request.urlopen(request,timeout=120) as resp:raw=resp.read()
 rows=parse(raw);data=calculate(rows);rank(data)
 if len(data)!=32:raise RuntimeError(f"Team count is {len(data)}, expected 32")
 payload={"season":SEASON,"source":"nflverse play-by-play","source_url":URL,"updated_at":datetime.now(timezone.utc).isoformat(),"team_count":32,"plays_loaded":len(rows),"data":data,"metrics":METRICS}
 os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
 with open(OUT,"w",encoding="utf-8") as file:json.dump(payload,file,ensure_ascii=False,indent=2)
 print(f"Refresh OK: {len(rows):,} rows, 32 teams saved to {OUT}")
if __name__=="__main__":refresh()
