#!/usr/bin/env python3
"""Build individual defensive-tackle analytics from nflverse PFR, PBP and snap counts.

Only DT/NT roster entries are included. Unavailable charting metrics remain null;
defensive snaps are never substituted for pass-rush snaps.
"""
import csv, gzip, io, json, os, urllib.request, unicodedata, re
from collections import defaultdict
from datetime import datetime, timezone

SEASON = int(os.environ.get("NFL_SEASON", "2026"))
PBP_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pbp/play_by_play_{SEASON}.csv.gz"
PLAYERS_URL = "https://github.com/nflverse/nflverse-data/releases/download/players/players.csv"
DEF_URL = f"https://github.com/nflverse/nflverse-data/releases/download/pfr_advstats/advstats_week_def_{SEASON}.csv"
SNAPS_URL = f"https://github.com/nflverse/nflverse-data/releases/download/snap_counts/snap_counts_{SEASON}.csv"
OUT = os.environ.get("NFL_DT_OUTPUT", "public/data/dt_players_2026.json")

METRICS = [
 {"key":"sacks","label":"Sacks (PFR)","category":"Pass-Rush-Produktion","format":"decimal","higher_is_better":True},
 {"key":"pressures","label":"Pressures (PFR)","category":"Pass-Rush-Produktion","format":"number","higher_is_better":True},
 {"key":"qb_hits","label":"QB Hits (PFR)","category":"Pass-Rush-Produktion","format":"number","higher_is_better":True},
 {"key":"hurries","label":"QB Hurries (PFR)","category":"Pass-Rush-Produktion","format":"number","higher_is_better":True},
 {"key":"tfls","label":"Tackles for Loss","category":"Run Defense","format":"number","higher_is_better":True},
 {"key":"pass_rush_snaps","label":"Pass-Rush Snaps","category":"Einsatz","format":"number","higher_is_better":True},
 {"key":"sack_rate","label":"Sack Rate (Sacks / Pass-Rush-Snaps)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"pressure_rate","label":"Pressure Rate (Pressures / Pass-Rush-Snaps)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"quick_pressure_rate","label":"Quick Pressure Rate","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"pass_rush_win_rate","label":"Pass Rush Win Rate (ESPN)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"run_stop_win_rate","label":"Run Stop Win Rate (ESPN)","category":"Run Defense","format":"percent","higher_is_better":True},
 {"key":"negative_plays_forced_rate","label":"Negative Plays Forced Rate (Sacks + TFLs / Defensive Snaps)","category":"Run Defense","format":"percent","higher_is_better":True},
 {"key":"double_team_rate","label":"Double-Team Rate","category":"Gegnerische Aufmerksamkeit","format":"percent","higher_is_better":True},
 {"key":"defensive_snaps","label":"Defensive Snaps","category":"Einsatz","format":"number","higher_is_better":True},
 {"key":"defensive_snap_share","label":"Defensive Snap Share","category":"Einsatz","format":"percent","higher_is_better":True},
 {"key":"combined_tackles","label":"Combined Tackles","category":"Run Defense","format":"number","higher_is_better":True},
 {"key":"solo_tackles","label":"Solo Tackles","category":"Run Defense","format":"number","higher_is_better":True},
 {"key":"missed_tackles","label":"Missed Tackles","category":"Run Defense","format":"number","higher_is_better":False},
 {"key":"missed_tackle_rate","label":"Missed Tackle Rate","category":"Run Defense","format":"percent","higher_is_better":False},
 {"key":"forced_fumbles","label":"Forced Fumbles","category":"Disruptive Plays","format":"number","higher_is_better":True}
]

def download(url):
    req = urllib.request.Request(url, headers={"User-Agent":"NFL-Analytics-DT-refresh/1.0"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return response.read()

def parse(raw):
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))

def num(value):
    try:
        if value is None or str(value).strip() in ("", "NA", "NaN", "null"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None

def normalize_name(value):
    value = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]", "", value)

def build(pbp, player_rows, defense_rows=(), snap_rows=()):
    roster = {}
    for p in player_rows:
        pos = str(p.get("position") or "").upper().strip()
        pid = p.get("gsis_id") or p.get("player_id")
        if pid and pos in {"DT", "NT"}:
            roster[pid] = p
    pfr_to_gsis = {
        p.get("pfr_id") or p.get("player_pfr_id"): pid
        for pid, p in roster.items()
        if p.get("pfr_id") or p.get("player_pfr_id")
    }

    snap_totals = defaultdict(float)
    player_teams = defaultdict(set)
    games = defaultdict(set)
    team_game_totals = {}
    for row in snap_rows:
        if str(row.get("season", "")).strip() != str(SEASON) or str(row.get("game_type", "REG")).upper() != "REG":
            continue
        pid = pfr_to_gsis.get(row.get("pfr_player_id") or row.get("player_pfr_id"))
        snaps, pct = num(row.get("defense_snaps")), num(row.get("defense_pct"))
        team, game = row.get("team") or "", row.get("game_id") or row.get("pfr_game_id") or ""
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

    pbp_tfls = defaultdict(float)
    forced_fumbles = defaultdict(float)
    negative_play_ids = defaultdict(set)
    team_counts = defaultdict(lambda: defaultdict(int))
    for row in pbp:
        if str(row.get("season", SEASON)).strip() != str(SEASON) or str(row.get("game_type", "REG")).upper() != "REG":
            continue
        team, game, play = row.get("defteam") or "", row.get("game_id") or "", row.get("play_id") or ""
        for i in (1, 2):
            pid = row.get(f"tackle_for_loss_{i}_player_id")
            if pid in roster:
                pbp_tfls[pid] += 1
                if game and play: negative_play_ids[pid].add((game, play))
            pid = row.get(f"forced_fumble_player_{i}_player_id")
            if pid in roster:
                forced_fumbles[pid] += 1
        sack_pid = row.get("sack_player_id")
        if sack_pid in roster and game and play:
            negative_play_ids[sack_pid].add((game, play))
        else:
            for i in (1, 2):
                half_pid = row.get(f"half_sack_{i}_player_id")
                if half_pid in roster and game and play:
                    negative_play_ids[half_pid].add((game, play))
        for i in (1, 2):
            for key in ("tackle_for_loss", "forced_fumble"):
                pid = row.get(f"{key}_{i}_player_id")
                if pid in roster and team:
                    team_counts[pid][team] += 1

    pfr = defaultdict(lambda: defaultdict(float))
    pfr_seen = defaultdict(set)
    for row in defense_rows:
        if str(row.get("season", "")).strip() != str(SEASON) or str(row.get("game_type", "REG")).upper() != "REG":
            continue
        pid = pfr_to_gsis.get(row.get("pfr_player_id") or row.get("pfr_id"))
        if not pid: continue
        for source, target in (
            ("def_sacks", "sacks"), ("def_pressures", "pressures"),
            ("def_times_hitqb", "qb_hits"), ("def_times_hurried", "hurries"),
            ("def_tackles_combined", "combined_tackles"),
            ("def_tackles_solo", "solo_tackles"), ("def_missed_tackles", "missed_tackles")
        ):
            value = num(row.get(source))
            if value is not None:
                pfr[pid][target] += value
                pfr_seen[pid].add(target)
        team = row.get("team") or ""
        if team: team_counts[pid][team] += 1

    output = []
    for pid, player in roster.items():
        snaps = int(snap_totals.get(pid, 0))
        if snaps <= 0 and not pfr[pid] and not pbp_tfls[pid] and not forced_fumbles[pid]:
            continue
        teams = team_counts[pid]
        team = max(teams, key=teams.get) if teams else (player.get("team") or "")
        denominator = sum(team_totals[t] for t in player_teams.get(pid, set()))
        sacks = pfr[pid].get("sacks") if "sacks" in pfr_seen[pid] else None
        pressures = pfr[pid].get("pressures") if "pressures" in pfr_seen[pid] else None
        qb_hits = pfr[pid].get("qb_hits") if "qb_hits" in pfr_seen[pid] else None
        hurries = pfr[pid].get("hurries") if "hurries" in pfr_seen[pid] else None
        combined = pfr[pid].get("combined_tackles") if "combined_tackles" in pfr_seen[pid] else None
        solo = pfr[pid].get("solo_tackles") if "solo_tackles" in pfr_seen[pid] else None
        missed = pfr[pid].get("missed_tackles") if "missed_tackles" in pfr_seen[pid] else None
        attempts = (combined or 0) + (missed or 0)
        name = player.get("display_name") or player.get("full_name") or player.get("name") or pid
        pos = str(player.get("position") or "").upper()
        # NT roster designation is a conservative signal for an interior 0/1-technique role.
        # DTs are not automatically tagged; exact alignment shares require charting data.
        technique_01 = pos == "NT"
        row = {
            "player_id": pid, "player_name": name, "team": team,
            "roster_position": pos, "interior_technique_01": technique_01,
            "defensive_snaps": snaps,
            "defensive_snap_share": snaps / denominator if denominator > 0 else None,
            "games_played": len(games[pid]),
            "sacks": sacks, "pressures": pressures, "qb_hits": qb_hits, "hurries": hurries,
            "tfls": int(pbp_tfls[pid]), "forced_fumbles": int(forced_fumbles[pid]),
            "combined_tackles": combined, "solo_tackles": solo, "missed_tackles": missed,
            "missed_tackle_rate": missed / attempts if missed is not None and attempts > 0 else None,
            "pass_rush_snaps": None, "sack_rate": None, "pressure_rate": None,
            "quick_pressure_rate": None, "pass_rush_win_rate": None, "run_stop_win_rate": None,
            "double_team_rate": None,
            "negative_plays_forced": len(negative_play_ids[pid]),
            "negative_plays_forced_rate": len(negative_play_ids[pid]) / snaps if snaps > 0 else None
        }
        output.append(row)

    for metric in METRICS:
        key = metric["key"]
        valid = [p for p in output if p.get(key) is not None]
        valid.sort(key=lambda p: p[key], reverse=metric["higher_is_better"])
        previous, rank = object(), 0
        for index, player in enumerate(valid, 1):
            if player[key] != previous: rank = index
            player[key + "_rank"] = rank
            previous = player[key]
    return sorted(output, key=lambda p: (p.get("defensive_snaps") or 0), reverse=True)

def main():
    pbp, players = parse(download(PBP_URL)), parse(download(PLAYERS_URL))
    defense, snaps = parse(download(DEF_URL)), parse(download(SNAPS_URL))
    data = build(pbp, players, defense, snaps)
    if not data:
        raise RuntimeError("No DT/NT player rows produced; refusing to overwrite snapshot.")
    payload = {
        "season": SEASON,
        "source": "nflverse PFR weekly defensive advanced stats + play-by-play + snap counts",
        "source_url": DEF_URL, "snap_counts_url": SNAPS_URL,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "player_count": len(data), "players": data, "metrics": METRICS,
        "limitations": [
            "PFR is the single source for sacks, pressures, QB hits and hurries. TFLs and forced fumbles are player-attributed nflverse play-by-play events.",
            "Sack Rate and Pressure Rate remain blank until reliable player-level pass-rush snap counts are integrated; defensive snaps are not used as a substitute.",
            "Quick Pressure Rate, Double-Team Rate and ESPN win rates remain blank until a reproducible DT-specific source is verified.",
            "0/1-technique name highlighting is enabled for explicit NT roster designations only. DTs are not guessed into a technique group without alignment-share data."
        ]
    }
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"DT refresh OK: {len(data)} DT/NT players saved from {len(pbp):,} plays, {len(defense):,} PFR rows and {len(snaps):,} snap rows.")

if __name__ == "__main__":
    main()
