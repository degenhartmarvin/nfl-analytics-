#!/usr/bin/env python3
"""Build a combined edge-rusher snapshot from nflverse PBP, PFR weekly defense and snap counts.

DE and OLB roster designations are grouped as Edge Rusher. Interior DT/NT players are excluded.
Unavailable charting metrics are kept null; they are never estimated from unrelated statistics.
"""
import csv, gzip, io, json, os, urllib.request
from collections import defaultdict
from datetime import datetime, timezone

SEASON = int(os.environ.get("NFL_SEASON", "2026"))
PBP_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
DEF_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_{SEASON}.csv"
SNAPS_URL = f"https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{SEASON}.csv"
OUT = os.environ.get("NFL_EDGE_OUTPUT", "public/data/edge_players_2026.json")

METRICS = [
 {"key":"sacks","label":"Sacks","category":"Pass-Rush-Produktion","format":"decimal","higher_is_better":True},
 {"key":"sack_rate","label":"Sack Rate","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"Nicht verfügbar: pass-rush snaps fehlen in den verwendeten öffentlichen Rohdaten."},
 {"key":"pressures","label":"Pressures","category":"Pressure & Pass-Rush-Effizienz","format":"number","higher_is_better":True},
 {"key":"pressure_rate","label":"Pressure Rate","category":"Pressure & Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"Nicht verfügbar: pass-rush snaps fehlen; wird nicht durch defensive snaps ersetzt."},
 {"key":"qb_hits","label":"QB Hits","category":"Pass-Rush-Produktion","format":"number","higher_is_better":True},
 {"key":"tfls","label":"Tackles for Loss (TFLs)","category":"Disruptive Plays","format":"number","higher_is_better":True},
 {"key":"quick_pressure_rate","label":"Quick Pressure Rate (unter 2,5 Sek.)","category":"Pressure & Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"Nicht verfügbar: die NFL Next Gen Stats Quick-Pressure-Ereignisse liegen nicht im genutzten PFR-Wochendatensatz."},
 {"key":"negative_plays_forced_rate","label":"Negative Plays Forced Rate (Sacks + TFLs je Defensive Snap)","category":"Disruptive Plays","format":"percent","higher_is_better":True},
 {"key":"double_team_rate","label":"Double-Team Rate","category":"Gegnerische Aufmerksamkeit","format":"percent","higher_is_better":True,"availability_note":"Nicht verfügbar: keine verlässlichen individuellen Double-Team-Snap-Zahlen im verwendeten öffentlichen Datensatz."},
 {"key":"pass_rush_win_rate","label":"Pass Rush Win Rate (ESPN)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True,"availability_note":"ESPN veröffentlicht nur eine begrenzte Ranglisten-Abdeckung; kein verlässlicher vollständiger Spieler-Datensatz im automatisierten Pipeline-Feed."},
 {"key":"run_stop_win_rate","label":"Run Stop Win Rate (ESPN)","category":"Run Defense","format":"percent","higher_is_better":True,"availability_note":"ESPN veröffentlicht nur eine begrenzte Ranglisten-Abdeckung; kein verlässlicher vollständiger Spieler-Datensatz im automatisierten Pipeline-Feed."}
]

def download(url):
    request = urllib.request.Request(url, headers={"User-Agent":"NFL-Analytics-Edge-refresh/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()

def parse(raw):
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def num(value):
    try:
        if value is None or str(value).strip() in ("", "NA", "NaN"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def build(pbp, player_rows, defense_rows=(), snap_rows=()):
    roster = {}
    for player in player_rows:
        position = str(player.get("position") or "").upper().strip()
        pid = player.get("gsis_id") or player.get("player_id")
        if pid and position in {"DE", "OLB", "EDGE"}:
            roster[pid] = player
    pfr_to_gsis = {}
    for pid, player in roster.items():
        pfr_id = player.get("pfr_id") or player.get("player_pfr_id")
        if pfr_id:
            pfr_to_gsis[pfr_id] = pid

    snap_totals = defaultdict(float)
    player_teams = defaultdict(set)
    team_game_totals = {}
    games = defaultdict(set)
    for row in snap_rows:
        if str(row.get("season","")).strip() != str(SEASON) or str(row.get("game_type","REG")).upper() != "REG":
            continue
        pfr_id = row.get("pfr_player_id") or row.get("player_pfr_id")
        pid = pfr_to_gsis.get(pfr_id)
        snaps = num(row.get("defense_snaps"))
        pct = num(row.get("defense_pct"))
        team = row.get("team") or ""
        game = row.get("game_id") or row.get("pfr_game_id") or ""
        if pid and snaps is not None:
            snap_totals[pid] += snaps
            if team: player_teams[pid].add(team)
            if game and snaps > 0: games[pid].add(game)
        if team and game and snaps is not None and pct is not None and pct > 0:
            pct = pct / 100 if pct > 1 else pct
            team_game_totals[(team, game)] = max(team_game_totals.get((team, game), 0), snaps / pct)
    team_totals = defaultdict(float)
    for (team, _game), total in team_game_totals.items():
        team_totals[team] += total

    totals = defaultdict(lambda: defaultdict(float))
    negative_play_ids = defaultdict(set)
    teams = defaultdict(dict)

    def add(pid, key, amount=1, team=""):
        if pid not in roster:
            return
        totals[pid][key] += amount
        if team:
            teams[pid][team] = teams[pid].get(team, 0) + 1

    for row in pbp:
        if str(row.get("season", SEASON)).strip() != str(SEASON):
            continue
        if str(row.get("game_type","REG")).upper() != "REG":
            continue
        team = row.get("defteam") or ""
        game_id = row.get("game_id") or ""
        play_id = row.get("play_id") or ""
        for i in (1, 2):
            pid = row.get(f"qb_hit_{i}_player_id")
            add(pid, "qb_hits", team=team)
            pid = row.get(f"tackle_for_loss_{i}_player_id")
            add(pid, "tfls", team=team)
            if pid and game_id and play_id:
                negative_play_ids[pid].add((game_id, play_id))
        sack_id = row.get("sack_player_id")
        if sack_id:
            add(sack_id, "sacks", 1, team)
            if game_id and play_id:
                negative_play_ids[sack_id].add((game_id, play_id))
        else:
            for i in (1, 2):
                pid = row.get(f"half_sack_{i}_player_id")
                if pid:
                    add(pid, "sacks", 0.5, team)
                    if game_id and play_id:
                        negative_play_ids[pid].add((game_id, play_id))

    pressures_by_id = defaultdict(float)
    for row in defense_rows:
        if str(row.get("season","")).strip() != str(SEASON) or str(row.get("game_type","REG")).upper() != "REG":
            continue
        pid = pfr_to_gsis.get(row.get("pfr_player_id") or row.get("pfr_id"))
        if not pid:
            continue
        pressure = num(row.get("def_pressures"))
        if pressure is not None:
            pressures_by_id[pid] += pressure
        team = row.get("team") or ""
        if team:
            teams[pid][team] = teams[pid].get(team, 0) + 1

    output = []
    for pid, player in roster.items():
        s = totals[pid]
        snaps = int(snap_totals.get(pid, 0))
        if snaps <= 0 and not any(s.values()) and pressures_by_id.get(pid, 0) <= 0:
            continue
        team = max(teams[pid], key=teams[pid].get) if teams[pid] else (player.get("team") or "")
        name = player.get("display_name") or player.get("full_name") or player.get("name") or pid
        snap_denominator = sum(team_totals[t] for t in player_teams.get(pid, set()))
        sacks = s["sacks"]
        tfls = s["tfls"]
        negative_plays = len(negative_play_ids[pid])
        row = {
            "player_id": pid, "player_name": name, "team": team,
            "roster_position": str(player.get("position") or "").upper(),
            "defensive_snaps": snaps,
            "defensive_snap_share": snaps / snap_denominator if snap_denominator > 0 else None,
            "games_played": len(games[pid]),
            "sacks": sacks, "pressures": pressures_by_id.get(pid) or None,
            "qb_hits": int(s["qb_hits"]), "tfls": int(tfls),
            "negative_plays_forced": negative_plays,
            "negative_plays_forced_rate": negative_plays / snaps if snaps > 0 else None,
            # Do not invent denominators or charting values that are absent from source data.
            "sack_rate": None, "pressure_rate": None, "quick_pressure_rate": None,
            "double_team_rate": None, "pass_rush_win_rate": None, "run_stop_win_rate": None
        }
        output.append(row)

    for metric in METRICS:
        key = metric["key"]
        valid = [p for p in output if p.get(key) is not None]
        valid.sort(key=lambda p: p[key], reverse=metric["higher_is_better"])
        previous = object()
        rank = 0
        for index, player in enumerate(valid, 1):
            if player[key] != previous:
                rank = index
            player[key + "_rank"] = rank
            previous = player[key]
    return sorted(output, key=lambda p: (p.get("defensive_snaps") or 0), reverse=True)

def main():
    pbp = parse(download(PBP_URL))
    players = parse(download(PLAYERS_URL))
    defense = parse(download(DEF_URL))
    snaps = parse(download(SNAPS_URL))
    data = build(pbp, players, defense, snaps)
    if not data:
        raise RuntimeError("No edge-rusher data produced; refusing to overwrite snapshot.")
    payload = {
        "season": SEASON,
        "source": "nflverse player registry + play-by-play + weekly PFR advanced defense + snap counts",
        "source_url": DEF_URL, "snap_counts_url": SNAPS_URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "player_count": len(data), "players": data, "metrics": METRICS,
        "limitations": [
            "The combined group uses the roster positions DE, OLB and EDGE; public roster data does not reliably identify each team's defensive front, so some 4-3 off-ball OLB designations may be included.",
            "Sack rate and pressure rate per pass-rush snap are not calculated because the selected source files do not provide individual pass-rush snap counts.",
            "Quick pressure rate, double-team rate, ESPN pass-rush win rate and ESPN run-stop win rate remain blank until a reproducible player-level feed is available. No estimates or proxy values are substituted.",
            "PFR pressure totals are charted pressure counts. TFLs and QB hits are player-attributed play-by-play events."
        ]
    }
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    print(f"Edge refresh OK: {len(pbp):,} plays + {len(defense):,} PFR rows + {len(snaps):,} snap rows, {len(data)} edge players saved.")

if __name__ == "__main__":
    main()
