#!/usr/bin/env python3
"""Build WR player snapshot from nflverse PBP and player registry."""
import csv,gzip,io,json,os,urllib.request
from collections import defaultdict,Counter
from datetime import datetime,timezone
SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
OUT=os.environ.get("NFL_WR_OUTPUT","public/data/wr_players_2026.json")
def download(url):
 req=urllib.request.Request(url,headers={"User-Agent":"NFL-Analytics-player-refresh/1.0"})
 with urllib.request.urlopen(req,timeout=120) as resp:return resp.read()
def parse(raw):
 if raw[:2]==b"\x1f\x8b":raw=gzip.decompress(raw)
 return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
def num(v):
 try:
  if v is None or str(v).strip() in ("","NA","NaN"):return None
  return float(v)
 except (ValueError,TypeError):return None
def truth(v):return str(v).strip().lower() in ("1","true","t","yes")
def build(pbp,players):
 roster={}
 for p in players:
  pid=p.get("gsis_id") or p.get("player_id");pos=p.get("position") or p.get("position_group")
  if pid and pos:roster[pid]=p
 stats=defaultdict(lambda:defaultdict(float));team_targets=defaultdict(float);teams=defaultdict(Counter)
 drops_col=any("drop" in r for r in pbp)
 for r in pbp:
  if r.get("play_type")!="pass" or not truth(r.get("pass_attempt")):continue
  pid=r.get("receiver_player_id")
  if not pid or pid not in roster or roster[pid].get("position")!="WR":continue
  s=stats[pid];s["targets"]+=1
  if team:teams[pid][team]+=1
  yards=num(r.get("yards_gained")) or 0;epa=num(r.get("epa"));succ=num(r.get("success"));complete=truth(r.get("complete_pass"))
  if complete:
   s["receptions"]+=1;s["receiving_yards"]+=yards;s["first_downs"]+=int(truth(r.get("first_down")))
   s["yac_total"]+=num(r.get("yards_after_catch")) or 0;s["longest_reception"]=max(s["longest_reception"],yards)
   if yards>=20:s["explosive_receptions"]+=1
   if truth(r.get("pass_touchdown")) or truth(r.get("touchdown")):s["receiving_tds"]+=1
  if epa is not None:s["epa_total"]+=epa;s["epa_n"]+=1
  if succ is not None:s["success_total"]+=succ;s["success_n"]+=1
  if drops_col:s["drops"]+=int(truth(r.get("drop")))
 out=[]
 for pid,s in stats.items():
  p=roster[pid];targets=s["targets"];rec=s["receptions"];team=teams[pid].most_common(1)[0][0] if teams[pid] else ""
  out.append({"player_id":pid,"player_name":p.get("display_name") or p.get("full_name") or p.get("name") or pid,"team":team,
   "targets":int(targets),"receptions":int(rec),"receiving_yards":int(s["receiving_yards"]),"receiving_tds":int(s["receiving_tds"]),
   "first_downs":int(s["first_downs"]),"yards_per_reception":s["receiving_yards"]/rec if rec else None,
   "yards_per_target":s["receiving_yards"]/targets if targets else None,"catch_rate":rec/targets if targets else None,
   "target_share":targets/team_targets[team] if team and team_targets[team] else None,
   "epa_per_target":s["epa_total"]/s["epa_n"] if s["epa_n"] else None,"success_rate":s["success_total"]/s["success_n"] if s["success_n"] else None,
   "explosive_receptions":int(s["explosive_receptions"]),"longest_reception":s["longest_reception"],
   "yac_total":int(s["yac_total"]),"yac_per_reception":s["yac_total"]/rec if rec else None,
   "drops":int(s["drops"]) if drops_col else None,"drop_rate":s["drops"]/targets if drops_col and targets else None})
 metrics={k:True for k in ("receiving_yards","receptions","targets","receiving_tds","first_downs","yards_per_reception","yards_per_target","catch_rate","target_share","epa_per_target","success_rate","explosive_receptions","longest_reception","yac_total","yac_per_reception")}
 metrics.update({"drops":False,"drop_rate":False})
 for key,high in metrics.items():
  vals=[x for x in out if x.get(key) is not None];vals.sort(key=lambda x:x[key],reverse=high);last=None;rank=0
  for i,x in enumerate(vals,1):
   if last is None or x[key]!=last:rank=i
   x[key+"_rank"]=rank;last=x[key]
 return sorted(out,key=lambda x:x["receiving_yards"],reverse=True)
def main():
 pbp=parse(download(PBP_URL));players=parse(download(PLAYERS_URL));data=build(pbp,players)
 if not data:raise RuntimeError("No WR records produced, refusing to overwrite snapshot.")
 payload={"season":SEASON,"source":"nflverse play-by-play + players registry","source_url":PBP_URL,"updated_at":datetime.now(timezone.utc).isoformat(),"player_count":len(data),"players":data}
 os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
 with open(OUT,"w",encoding="utf-8") as f:json.dump(payload,f,ensure_ascii=False,indent=2)
 print(f"WR refresh OK: {len(data)} players saved to {OUT}")
if __name__=="__main__":main()
