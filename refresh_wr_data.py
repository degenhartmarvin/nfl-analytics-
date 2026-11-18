#!/usr/bin/env python3
"""Build WR player snapshot from nflverse play-by-play and player registry."""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict, Counter
from datetime import datetime, timezone

SEASON=int(os.environ.get("NFL_SEASON","2026"))
PBP_URL=f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL="https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
OUT=os.environ.get("NFL_WR_OUTPUT","public/data/wr_players_2026.json")

def download(url):
    req=urllib.request.Request(url,headers={"User-Agent":"NFL-Analytics-player-refresh/1.0"})
    with urllib.request.urlopen(req,timeout=120) as response:
        return response.read()

def parse(raw):
    if raw[:2]==b"\x1f\x8b":
        raw=gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def num(value):
    try:
        if value is None or str(value).strip() in ("","NA","NaN"):
            return None
        return float(value)
    except (TypeError,ValueError):
        return None

def truth(value):
    return str(value).strip().lower() in ("1","true","t","yes")

def build(pbp, player_rows):
    roster={}
    for player in player_rows:
        player_id=player.get("gsis_id") or player.get("player_id")
        position=player.get("position") or player.get("position_group")
        if player_id and position:
            roster[player_id]=player

    stats=defaultdict(lambda:defaultdict(float))
    team_targets=defaultdict(float)
    player_teams=defaultdict(Counter)
    drops_available=any("drop" in row for row in pbp)

    for row in pbp:
        if row.get("play_type")!="pass" or not truth(row.get("pass_attempt")):
            continue
        team=row.get("posteam") or ""
        team_targets[team]+=1
        player_id=row.get("receiver_player_id")
        if not player_id or player_id not in roster:
            continue
        if roster[player_id].get("position")!="WR":
            continue

        player_stats=stats[player_id]
        player_stats["targets"]+=1
        if team:
            player_teams[player_id][team]+=1
        yards=num(row.get("yards_gained")) or 0
        epa=num(row.get("epa"))
        success=num(row.get("success"))
        completed=truth(row.get("complete_pass"))

        if completed:
            player_stats["receptions"]+=1
            player_stats["receiving_yards"]+=yards
            player_stats["first_downs"]+=int(truth(row.get("first_down")))
            player_stats["yac_total"]+=num(row.get("yards_after_catch")) or 0
            player_stats["longest_reception"]=max(player_stats["longest_reception"],yards)
            if yards>=20:
                player_stats["explosive_receptions"]+=1
            if truth(row.get("pass_touchdown")) or truth(row.get("touchdown")):
                player_stats["receiving_tds"]+=1
        if epa is not None:
            player_stats["epa_total"]+=epa
            player_stats["epa_n"]+=1
        if success is not None:
            player_stats["success_total"]+=success
            player_stats["success_n"]+=1
        if drops_available:
            player_stats["drops"]+=int(truth(row.get("drop")))

    output=[]
    for player_id,player_stats in stats.items():
        player=roster[player_id]
        targets=player_stats["targets"]
        receptions=player_stats["receptions"]
        team=player_teams[player_id].most_common(1)[0][0] if player_teams[player_id] else ""
        name=player.get("display_name") or player.get("full_name") or player.get("name") or player_id
        output.append({
            "player_id":player_id,"player_name":name,"team":team,
            "targets":int(targets),"receptions":int(receptions),
            "receiving_yards":int(player_stats["receiving_yards"]),
            "receiving_tds":int(player_stats["receiving_tds"]),
            "first_downs":int(player_stats["first_downs"]),
            "yards_per_reception":player_stats["receiving_yards"]/receptions if receptions else None,
            "yards_per_target":player_stats["receiving_yards"]/targets if targets else None,
            "catch_rate":receptions/targets if targets else None,
            "target_share":targets/team_targets[team] if team and team_targets[team] else None,
            "epa_per_target":player_stats["epa_total"]/player_stats["epa_n"] if player_stats["epa_n"] else None,
            "success_rate":player_stats["success_total"]/player_stats["success_n"] if player_stats["success_n"] else None,
            "explosive_receptions":int(player_stats["explosive_receptions"]),
            "longest_reception":player_stats["longest_reception"],
            "yac_total":int(player_stats["yac_total"]),
            "yac_per_reception":player_stats["yac_total"]/receptions if receptions else None,
            "drops":int(player_stats["drops"]) if drops_available else None,
            "drop_rate":player_stats["drops"]/targets if drops_available and targets else None
        })

    higher_is_better={key:True for key in (
        "receiving_yards","receptions","targets","receiving_tds","first_downs",
        "yards_per_reception","yards_per_target","catch_rate","target_share",
        "epa_per_target","success_rate","explosive_receptions","longest_reception",
        "yac_total","yac_per_reception")}
    higher_is_better.update({"drops":False,"drop_rate":False})
    for metric,is_high in higher_is_better.items():
        valid=[player for player in output if player.get(metric) is not None]
        valid.sort(key=lambda player:player[metric],reverse=is_high)
        previous=None
        rank_value=0
        for index,player in enumerate(valid,1):
            if previous is None or player[metric]!=previous:
                rank_value=index
            player[metric+"_rank"]=rank_value
            previous=player[metric]
    return sorted(output,key=lambda player:player["receiving_yards"],reverse=True)

def main():
    pbp=parse(download(PBP_URL))
    players=parse(download(PLAYERS_URL))
    player_data=build(pbp,players)
    if not player_data:
        raise RuntimeError("No WR data produced; refusing to overwrite snapshot.")
    payload={"season":SEASON,"source":"nflverse play-by-play + players registry",
        "source_url":PBP_URL,"updated_at":datetime.now(timezone.utc).isoformat(),
        "player_count":len(player_data),"players":player_data}
    os.makedirs(os.path.dirname(OUT) or ".",exist_ok=True)
    with open(OUT,"w",encoding="utf-8") as file:
        json.dump(payload,file,ensure_ascii=False,indent=2)
    print(f"WR refresh OK: {len(player_data)} players saved to {OUT}")

if __name__=="__main__":
    main()
