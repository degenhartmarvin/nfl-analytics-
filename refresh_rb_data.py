#!/usr/bin/env python3
"""Build RB player snapshot from nflverse PBP, NFL Next Gen Stats and PFR advanced rushing."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
NGS_URL="https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_rushing.csv.gz"
PFR_URL="https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_season_rush.csv.gz"
OUT=os.environ.get("NFL_RB_OUTPUT","public/data/rb_players_2026.json")

def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NFL-Analytics-RB-refresh/1.0"})
    with urllib.request.urlopen(req,timeout=120) as response: return response.read()

def parse(raw):
    if raw[:2]==b"\x1f\x8b": raw=gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def num(v):
    try:
        if v is None or str(v).strip() in ("","NA","NaN"): return None
        return float(v)
    except (TypeError,ValueError): return None

def truth(v): return str(v).strip().lower() in ("1","true","t","yes")

def build(pbp, players, ngs_rows=None, pfr_rows=None):
    roster={}
    for p in players:
        pid=p.get("gsis_id") or p.get("player_id")
        if pid and (p.get("position") or p.get("position_group")):
            roster[pid]=p
    stats=defaultdict(lambda:defaultdict(float))
    team_rush=Counter(); team_targets=Counter(); player_teams=defaultdict(Counter)
    for row in pbp:
        team=row.get("posteam") or ""
        kind=row.get("play_type")
        if kind=="run" and truth(row.get("rush_attempt")):
            team_rush[team]+=1
            pid=row.get("rusher_player_id")
            if pid in roster and roster[pid].get("position")=="RB":
                s=stats[pid]; player_teams[pid][team]+=1
                y=num(row.get("yards_gained")) or 0
                s["carries"]+=1; s["rushing_yards"]+=y
                s["rushing_tds"]+=int(truth(row.get("rush_touchdown")) or truth(row.get("touchdown")))
                s["rushing_first_downs"]+=int(truth(row.get("first_down")))
                s["epa_total"]+=num(row.get("epa")) or 0; s["epa_n"]+=1
                s["success_total"]+=num(row.get("success")) or 0; s["success_n"]+=1
                s["stuffed"]+=int(y<=0)
                s["explosive_runs"]+=int(y>=10)
                s["longest_rush"]=max(s["longest_rush"],y)
                s["redzone_carries"]+=int((num(row.get("yardline_100")) or 100)<=20)
                s["redzone_tds"]+=int((num(row.get("yardline_100")) or 100)<=20 and (truth(row.get("rush_touchdown")) or truth(row.get("touchdown"))))
                s["short_yardage_attempts"]+=int(num(row.get("ydstogo")) is not None and num(row.get("ydstogo"))<=2 and num(row.get("down")) in (3,4))
                s["short_yardage_conversions"]+=int(num(row.get("ydstogo")) is not None and num(row.get("ydstogo"))<=2 and num(row.get("down")) in (3,4) and (truth(row.get("first_down")) or truth(row.get("touchdown"))))
                s["fumbles"]+=int(truth(row.get("fumble")))
                s["fumbles_lost"]+=int(truth(row.get("fumble_lost")))
        if kind=="pass" and truth(row.get("pass_attempt")):
            team_targets[team]+=1
            pid=row.get("receiver_player_id")
            if pid in roster and roster[pid].get("position")=="RB":
                s=stats[pid]; player_teams[pid][team]+=1
                s["targets"]+=1
                if truth(row.get("complete_pass")):
                    s["receptions"]+=1; s["receiving_yards"]+=num(row.get("yards_gained")) or 0
                    s["receiving_tds"]+=int(truth(row.get("pass_touchdown")) or truth(row.get("touchdown")))
                    s["receiving_first_downs"]+=int(truth(row.get("first_down")))
                    s["receiving_yac"]+=num(row.get("yards_after_catch")) or 0
                    s["longest_reception"]=max(s["longest_reception"],num(row.get("yards_gained")) or 0)
                s["rec_epa_total"]+=num(row.get("epa")) or 0; s["rec_epa_n"]+=1
                s["rec_success_total"]+=num(row.get("success")) or 0; s["rec_success_n"]+=1
    # Join NFL Next Gen Stats by stable GSIS ID (season aggregate, week 0).
    ngs={}
    for row in ngs_rows or []:
        if str(row.get("season",""))!=str(SEASON) or str(row.get("week","")) not in ("0","0.0"): continue
        if str(row.get("season_type","")).upper() not in ("REG","REGULAR",""): continue
        if row.get("player_position")!="RB": continue
        pid=row.get("player_gsis_id")
        if pid: ngs[pid]=row
    # PFR season advanced rushing stats use PFR IDs; sum additive fields if traded.
    pfr=defaultdict(lambda:defaultdict(float))
    for row in pfr_rows or []:
        if str(row.get("season",""))!=str(SEASON) or str(row.get("pos","")).upper()!="RB": continue
        pid=row.get("pfr_id") or row.get("player_pfr_id")
        if not pid: continue
        for key in ("ybc","yac","brk_tkl"):
            val=num(row.get(key))
            if val is not None: pfr[pid][key]+=val
    out=[]
    for pid,s in stats.items():
        if not s["carries"] and not s["targets"]: continue
        player=roster[pid]; team=player_teams[pid].most_common(1)[0][0] if player_teams[pid] else ""
        name=player.get("display_name") or player.get("full_name") or player.get("name") or pid
        ng=ngs.get(pid,{})
        pf=pfr.get(player.get("pfr_id") or "",{})
        carries=s["carries"]; rec=s["receptions"]; targets=s["targets"]
        ybc=pf.get("ybc"); yac=pf.get("yac"); broken=pf.get("brk_tkl")
        ryoe=num(ng.get("rush_yards_over_expected")); ryoe_att=num(ng.get("rush_yards_over_expected_per_att"))
        row={
          "player_id":pid,"player_name":name,"team":team,
          "carries":int(carries),"rushing_yards":int(s["rushing_yards"]),"rushing_tds":int(s["rushing_tds"]),
          "yards_per_carry":s["rushing_yards"]/carries if carries else None,
          "rushing_first_downs":int(s["rushing_first_downs"]),"scrimmage_yards":int(s["rushing_yards"]+s["receiving_yards"]),
          "fumbles":int(s["fumbles"]),"fumbles_lost":int(s["fumbles_lost"]),
          "yards_before_contact":ybc,"yards_before_contact_per_carry":(ybc/carries) if ybc is not None and carries else None,
          "yards_after_contact":yac,"yards_after_contact_per_carry":(yac/carries) if yac is not None and carries else None,
          "broken_tackles":broken,"broken_tackles_per_carry":broken/carries if broken is not None and carries else None,
          "ryoe":ryoe,"ryoe_per_attempt":ryoe_att if ryoe_att is not None else (ryoe/carries if ryoe is not None and carries else None),
          "ngs_efficiency":num(ng.get("efficiency")),"heavy_box_rate":num(ng.get("percent_attempts_gte_eight_defenders")),
          "avg_time_to_line":num(ng.get("avg_time_to_los")),
          "explosive_runs":int(s["explosive_runs"]),"explosive_run_rate":s["explosive_runs"]/carries if carries else None,
          "success_rate":s["success_total"]/s["success_n"] if s["success_n"] else None,
          "epa_per_rush":s["epa_total"]/s["epa_n"] if s["epa_n"] else None,
          "stuff_rate":s["stuffed"]/carries if carries else None,"longest_rush":s["longest_rush"] if carries else None,
          "redzone_carries":int(s["redzone_carries"]),"redzone_tds":int(s["redzone_tds"]),
          "redzone_td_rate":s["redzone_tds"]/s["redzone_carries"] if s["redzone_carries"] else None,
          "short_yardage_attempts":int(s["short_yardage_attempts"]),
          "short_yardage_conversions":int(s["short_yardage_conversions"]),
          "short_yardage_conversion_rate":s["short_yardage_conversions"]/s["short_yardage_attempts"] if s["short_yardage_attempts"] else None,
          "targets":int(targets),"receptions":int(rec),"receiving_yards":int(s["receiving_yards"]),
          "receiving_tds":int(s["receiving_tds"]),"receiving_first_downs":int(s["receiving_first_downs"]),
          "catch_rate":rec/targets if targets else None,"yards_per_target":s["receiving_yards"]/targets if targets else None,
          "yards_per_reception":s["receiving_yards"]/rec if rec else None,
          "target_share":targets/team_targets[team] if team and team_targets[team] else None,
          "receiving_yac":int(s["receiving_yac"]),"receiving_epa_per_target":s["rec_epa_total"]/s["rec_epa_n"] if s["rec_epa_n"] else None,
          "receiving_success_rate":s["rec_success_total"]/s["rec_success_n"] if s["rec_success_n"] else None,
          "longest_reception":s["longest_reception"] if targets else None
        }
        out.append(row)
    high={
      "carries":True,"rushing_yards":True,"rushing_tds":True,"yards_per_carry":True,"rushing_first_downs":True,
      "scrimmage_yards":True,"fumbles":False,"fumbles_lost":False,"yards_before_contact":True,
      "yards_before_contact_per_carry":True,"yards_after_contact":True,"yards_after_contact_per_carry":True,
      "broken_tackles":True,"broken_tackles_per_carry":True,"ryoe":True,"ryoe_per_attempt":True,
      "ngs_efficiency":True,"heavy_box_rate":True,"avg_time_to_line":False,"explosive_runs":True,
      "explosive_run_rate":True,"success_rate":True,"epa_per_rush":True,"stuff_rate":False,
      "longest_rush":True,"redzone_carries":True,"redzone_tds":True,"redzone_td_rate":True,
      "short_yardage_attempts":True,"short_yardage_conversions":True,"short_yardage_conversion_rate":True,
      "targets":True,"receptions":True,"receiving_yards":True,"receiving_tds":True,"receiving_first_downs":True,
      "catch_rate":True,"yards_per_target":True,"yards_per_reception":True,"target_share":True,
      "receiving_yac":True,"receiving_epa_per_target":True,"receiving_success_rate":True,"longest_reception":True
    }
    min_carries={"yards_per_carry":50,"yards_before_contact_per_carry":50,"yards_after_contact_per_carry":50,
      "broken_tackles_per_carry":50,"ryoe_per_attempt":50,"ngs_efficiency":50,"explosive_run_rate":50,
      "success_rate":50,"epa_per_rush":50,"stuff_rate":50,"redzone_td_rate":10,"short_yardage_conversion_rate":5}
    min_targets={"catch_rate":15,"yards_per_target":15,"yards_per_reception":10,"target_share":15,
      "receiving_epa_per_target":20,"receiving_success_rate":15}
    for metric,is_high in high.items():
        valid=[x for x in out if x.get(metric) is not None and x["carries"]>=min_carries.get(metric,0) and x["targets"]>=min_targets.get(metric,0)]
        valid.sort(key=lambda x:x[metric],reverse=is_high)
        previous=None; rank=0
        for i,x in enumerate(valid,1):
            if previous is None or x[metric]!=previous: rank=i
            x[metric+"_rank"]=rank; previous=x[metric]
    return sorted(out,key=lambda x:x["scrimmage_yards"],reverse=True)

def main():
    pbp=parse(download(PBP_URL)); players=parse(download(PLAYERS_URL))
    ngs=parse(download(NGS_URL)); pfr=parse(download(PFR_URL))
    data=build(pbp,players,ngs,pfr)
    if not data: raise RuntimeError("No RB data produced; refusing to overwrite snapshot.")
    payload={"season":SEASON,"source":"nflverse play-by-play + NFL Next Gen Stats + PFR advanced rushing",
      "source_urls":{"pbp":PBP_URL,"ngs":NGS_URL,"pfr":PFR_URL},
      "updated_at":datetime.now(timezone.utc).isoformat(),"player_count":len(data),"players":data}
    os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
    with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
    print(f"RB refresh OK: {len(data)} players saved to {OUT}")

if __name__=="__main__": main()
