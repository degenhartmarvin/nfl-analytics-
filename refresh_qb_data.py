#!/usr/bin/env python3
"""Build QB player snapshot from the same nflverse play-by-play feed as team/WR data."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
OUT=os.environ.get("NFL_QB_OUTPUT","public/data/qb_players_2026.json")
QBR_URL="https://github.com/nflverse/nflverse-data/releases/download/espn_data/qbr_season_level.csv"
NGS_URL="https://github.com/nflverse/nflverse-data/releases/download/nextgen_stats/ngs_passing.csv.gz"

def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NFL-Analytics-QB-refresh/1.0"})
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

def norm_name(value):
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in str(value or "")).split())

def supplemental_maps(qbr_rows, ngs_rows, season):
    qbr_values=defaultdict(list)
    for row in qbr_rows:
        if str(row.get("season","")) != str(season): continue
        if str(row.get("season_type","")).lower() not in ("regular","reg","regular season",""): continue
        if str(row.get("qualified","1")).strip() in ("0","False","false"): continue
        name=norm_name(row.get("name_display") or row.get("name") or row.get("name_short"))
        value=num(row.get("qbr_total"))
        if name and value is not None: qbr_values[name].append(value)
    qbr={name:sum(values)/len(values) for name,values in qbr_values.items()}
    ttt={}
    # nflverse NGS publishes week=0 as the season-to-date regular-season aggregate.
    for row in ngs_rows:
        if str(row.get("season","")) != str(season): continue
        week=str(row.get("week","")).strip()
        if week not in ("0","0.0"): continue
        if str(row.get("season_type","")).lower() not in ("reg","regular","regular season",""): continue
        name=norm_name(row.get("player_display_name") or row.get("player_name") or row.get("player"))
        value=num(row.get("avg_time_to_throw") or row.get("time_to_throw"))
        if name and value is not None: ttt[name]=value
    return qbr,ttt

def build(pbp, player_rows, qbr_rows=None, ngs_rows=None):
    roster={}
    for p in player_rows:
        pid=p.get("gsis_id") or p.get("player_id")
        if pid and (p.get("position") or p.get("position_group")):
            roster[pid]=p
    stats=defaultdict(lambda:defaultdict(float))
    teams=defaultdict(Counter)
    team_attempts=Counter()
    for row in pbp:
        if row.get("posteam") and truth(row.get("pass_attempt")):
            team_attempts[row["posteam"]]+=1
        pid=row.get("passer_player_id")
        if pid and pid in roster and roster[pid].get("position")=="QB":
            s=stats[pid]
            team=row.get("posteam") or ""
            if team: teams[pid][team]+=1
            play=row.get("play_type")
            is_pass=play=="pass"
            is_dropback=truth(row.get("qb_dropback")) if row.get("qb_dropback") not in (None,"") else (truth(row.get("pass_attempt")) or truth(row.get("sack")))
            if is_dropback:
                s["dropbacks"]+=1
                epa=num(row.get("epa")); success=num(row.get("success"))
                if epa is not None: s["dropback_epa"]+=epa; s["dropback_epa_n"]+=1
                if success is not None: s["dropback_success"]+=success; s["dropback_success_n"]+=1
            if is_pass and truth(row.get("pass_attempt")):
                s["attempts"]+=1
                complete=truth(row.get("complete_pass"))
                yards=num(row.get("passing_yards"))
                if yards is None: yards=num(row.get("yards_gained"))
                yards=yards or 0
                s["pass_yards"]+=yards
                s["completions"]+=int(complete)
                s["pass_tds"]+=int(truth(row.get("pass_touchdown")))
                s["interceptions"]+=int(truth(row.get("interception")))
                s["first_downs"]+=int(truth(row.get("first_down")))
                air=num(row.get("air_yards"))
                if air is not None:
                    s["air_yards_total"]+=air; s["air_yards_n"]+=1
                    if air>=20:
                        s["deep_attempts"]+=1
                        if complete: s["deep_completions"]+=1
                if yards>=20 and complete: s["explosive_completions"]+=1
                if row.get("cpoe") not in (None,""):
                    cpoe=num(row.get("cpoe"))
                    if cpoe is not None: s["cpoe_total"]+=cpoe; s["cpoe_n"]+=1
                if row.get("epa") not in (None,""):
                    epa=num(row.get("epa"))
                    if epa is not None: s["pass_epa"]+=epa; s["pass_epa_n"]+=1
                if row.get("success") not in (None,""):
                    su=num(row.get("success"))
                    if su is not None: s["pass_success"]+=su; s["pass_success_n"]+=1
                if truth(row.get("fumble_lost")): s["fumbles_lost"]+=1
            if truth(row.get("sack")):
                s["sacks"]+=1
                s["sack_yards"]+=abs(num(row.get("yards_gained")) or 0)
                if truth(row.get("fumble_lost")): s["fumbles_lost"]+=1

        # Attribute QB rushing (including scrambles) by rusher ID.
        rid=row.get("rusher_player_id")
        if rid and rid in roster and roster[rid].get("position")=="QB" and row.get("play_type")=="run":
            s=stats[rid]
            s["rush_attempts"]+=1
            ry=num(row.get("yards_gained")) or 0
            s["rush_yards"]+=ry
            s["rush_tds"]+=int(truth(row.get("rush_touchdown")) or truth(row.get("touchdown")))
            s["rush_first_downs"]+=int(truth(row.get("first_down")))
            s["longest_rush"]=ry if s["rush_attempts"]==1 else max(s["longest_rush"],ry)
            if ry>=10: s["explosive_rushes"]+=1
            if truth(row.get("fumble_lost")) and row.get("fumbler_player_id")==rid: s["fumbles_lost"]+=1

    qbr_map,ttt_map=supplemental_maps(qbr_rows or [],ngs_rows or [],SEASON)
    out=[]
    for pid,s in stats.items():
        p=roster[pid]; att=s["attempts"]; comp=s["completions"]; yds=s["pass_yards"]
        td=s["pass_tds"]; ints=s["interceptions"]; sacks=s["sacks"]; db=s["dropbacks"]
        team=teams[pid].most_common(1)[0][0] if teams[pid] else ""
        # Keep only the clear primary passer for each team; short-term backups
        # and one-game replacements are excluded from the QB leaderboard.
        team_att=team_attempts.get(team,0)
        if not team_att or att/team_att <= 0.50:
            continue
        name=p.get("display_name") or p.get("full_name") or p.get("name") or pid
        c_pct=comp/att if att else None
        ypa=yds/att if att else None
        td_pct=td/att if att else None
        int_pct=ints/att if att else None
        # Official NFL passer-rating formula, on the 0-158.3 scale.
        rating=None
        if att:
            a=max(0,min(2.375,(c_pct-.3)*5))
            b=max(0,min(2.375,((ypa or 0)-3)*.25))
            c=max(0,min(2.375,(td_pct or 0)*20))
            d=max(0,min(2.375,2.375-(int_pct or 0)*25))
            rating=((a+b+c+d)/6)*100
        out.append({
            "player_id":pid,"player_name":name,"team":team,
            "qbr_total":qbr_map.get(norm_name(name)),
            "time_to_throw":ttt_map.get(norm_name(name)),
            "attempts":int(att),"completions":int(comp),"passing_yards":int(yds),
            "passing_tds":int(td),"interceptions":int(ints),"passing_first_downs":int(s["first_downs"]),
            "completion_rate":c_pct,"yards_per_attempt":ypa,
            "yards_per_completion":yds/comp if comp else None,
            "td_rate":td_pct,"interception_rate":int_pct,
            "passer_rating":rating,
            "adjusted_yards_per_attempt":(yds+20*td-45*ints)/att if att else None,
            "net_yards_per_attempt":(yds-s["sack_yards"])/(att+sacks) if att+sacks else None,
            "any_a":(yds+20*td-45*ints)/(att+sacks) if att+sacks else None,
            "dropbacks":int(db),"sacks_taken":int(sacks),
            "sack_rate":sacks/db if db else None,
            "epa_per_dropback":s["dropback_epa"]/s["dropback_epa_n"] if s["dropback_epa_n"] else None,
            "pass_epa_per_attempt":s["pass_epa"]/s["pass_epa_n"] if s["pass_epa_n"] else None,
            "success_rate":s["dropback_success"]/s["dropback_success_n"] if s["dropback_success_n"] else None,
            "cpoe":s["cpoe_total"]/s["cpoe_n"] if s["cpoe_n"] else None,
            "air_yards_total":round(s["air_yards_total"],1),
            "average_depth_of_target":s["air_yards_total"]/s["air_yards_n"] if s["air_yards_n"] else None,
            "deep_attempts":int(s["deep_attempts"]),
            "deep_completions":int(s["deep_completions"]),
            "deep_completion_rate":s["deep_completions"]/s["deep_attempts"] if s["deep_attempts"] else None,
            "explosive_completions":int(s["explosive_completions"]),
            "rush_attempts":int(s["rush_attempts"]),"rushing_yards":int(s["rush_yards"]),
            "rushing_tds":int(s["rush_tds"]),
            "yards_per_rush":s["rush_yards"]/s["rush_attempts"] if s["rush_attempts"] else None,
            "rushing_first_downs":int(s["rush_first_downs"]),
            "explosive_rushes":int(s["explosive_rushes"]),
            "longest_rush":s["longest_rush"] if s["rush_attempts"] else None,
            "fumbles_lost":int(s["fumbles_lost"])
        })
    higher={
        "attempts":True,"completions":True,"passing_yards":True,"passing_tds":True,
        "interceptions":False,"passing_first_downs":True,"completion_rate":True,
        "yards_per_attempt":True,"yards_per_completion":True,"td_rate":True,
        "interception_rate":False,"passer_rating":True,"adjusted_yards_per_attempt":True,
        "net_yards_per_attempt":True,"any_a":True,"dropbacks":True,"sacks_taken":False,
        "sack_rate":False,"epa_per_dropback":True,"pass_epa_per_attempt":True,
        "success_rate":True,"cpoe":True,"air_yards_total":True,
        "average_depth_of_target":True,"qbr_total":True,"time_to_throw":False,"deep_attempts":True,"deep_completions":True,
        "deep_completion_rate":True,"explosive_completions":True,
        "rush_attempts":True,"rushing_yards":True,"rushing_tds":True,
        "yards_per_rush":True,"rushing_first_downs":True,"explosive_rushes":True,
        "longest_rush":True,"fumbles_lost":False
    }
    # All displayed players are primary team passers. Rate/efficiency rankings
    # also require at least 100 attempts to avoid tiny-sample outliers.
    min_att={"completion_rate","yards_per_attempt","yards_per_completion","td_rate",
        "interception_rate","passer_rating","adjusted_yards_per_attempt","net_yards_per_attempt",
        "any_a","sack_rate","epa_per_dropback","pass_epa_per_attempt","success_rate","cpoe",
        "average_depth_of_target","deep_completion_rate","qbr_total","time_to_throw"}
    for metric,is_high in higher.items():
        valid=[x for x in out if x.get(metric) is not None and (metric not in min_att or x["attempts"]>=100)]
        valid.sort(key=lambda x:x[metric],reverse=is_high)
        prev=None; rank=0
        for i,x in enumerate(valid,1):
            if prev is None or x[metric]!=prev: rank=i
            x[metric+"_rank"]=rank; prev=x[metric]
    return sorted(out,key=lambda x:x["passing_yards"],reverse=True)

def main():
    pbp=parse(download(PBP_URL)); players=parse(download(PLAYERS_URL))
    qbr_rows=parse(download(QBR_URL)); ngs_rows=parse(download(NGS_URL))
    data=build(pbp,players,qbr_rows,ngs_rows)
    if not data: raise RuntimeError("No QB data produced; refusing to overwrite snapshot.")
    payload={"season":SEASON,"source":"nflverse play-by-play + ESPN Total QBR + NFL Next Gen Stats + players registry",
        "supplemental_sources":{"qbr":QBR_URL,"time_to_throw":NGS_URL},
        "source_url":PBP_URL,"updated_at":datetime.now(timezone.utc).isoformat(),
        "player_count":len(data),"players":data}
    os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
    with open(OUT,"w",encoding="utf-8") as f: json.dump(payload,f,ensure_ascii=False,indent=2)
    print(f"QB refresh OK: {len(data)} players saved to {OUT}")

if __name__=="__main__": main()
