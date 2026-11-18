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
   if yards>=20:a["explosive_pass"]+=1;b["explosive_pass"]+=1
  else:
   a["rush"]+=1;b["rush"]+=1
   if yards>=10:a["explosive_rush"]+=1;b["explosive_rush"]+=1
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
 out=[]
 for t in TEAMS:
  o,d=off[t],de[t]
  if not o["plays"] or not d["plays"]:raise ValueError(f"No valid plays for {t}; aborting 32-team snapshot")
  out.append({"team":t,"off_yards_per_play":o["yards"]/o["plays"],"off_epa_per_play":o["epa"]/o["plays"],"off_success_rate":o["success"]/o["plays"],
   "off_explosive_pass_rate":o["explosive_pass"]/o["pass"] if o["pass"] else None,"off_explosive_rush_rate":o["explosive_rush"]/o["rush"] if o["rush"] else None,
   "off_redzone_td_rate":o["rz_td"]/o["rz_drives"] if o["rz_drives"] else None,
   "def_yards_allowed_per_play":d["yards"]/d["plays"],"def_epa_allowed_per_play":d["epa"]/d["plays"],"def_success_rate_allowed":d["success"]/d["plays"],
   "def_explosive_pass_rate_allowed":d["explosive_pass"]/d["pass"] if d["pass"] else None,"def_explosive_rush_rate_allowed":d["explosive_rush"]/d["rush"] if d["rush"] else None,
   "def_redzone_td_rate_allowed":d["rz_td"]/d["rz_drives"] if d["rz_drives"] else None,"off_plays":int(o["plays"]),"def_plays":int(d["plays"])})
 return out
def rank(data):
 for m in METRICS:
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
