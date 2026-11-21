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
 {"key":"sacks_per_game","label":"Sacks per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"pressures_per_game","label":"Pressures per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"qb_hits_per_game","label":"QB Hits per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"hurries_per_game","label":"QB Hurries per Game","category":"Produktion pro Spiel","format":"decimal","higher_is_better":True},
 {"key":"qb_hits_per_100_def_snaps","label":"QB Hit Rate per 100 Defensive Snaps","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"hurries_per_100_def_snaps","label":"Hurry Rate per 100 Defensive Snaps","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"pressure_to_sack_rate","label":"Pressure-to-Sack Conversion","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"tfls_per_100_def_snaps","label":"TFLs per 100 Defensive Snaps","category":"Run Defense","format":"decimal","higher_is_better":True},
 {"key":"tfls","label":"Tackles for Loss","category":"Run Defense","format":"number","higher_is_better":True},
 {"key":"pass_rush_snaps","label":"Pass-Rush Snaps","category":"Einsatz","format":"number","higher_is_better":True},
 {"key":"sack_rate","label":"Sack Rate (Sacks / Pass-Rush-Snaps)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"pressure_rate","label":"Pressure Rate (Pressures / Pass-Rush-Snaps)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"quick_pressure_rate","label":"Quick Pressure Rate","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"pass_rush_win_rate","label":"Pass Rush Win Rate (ESPN)","category":"Pass-Rush-Effizienz","format":"percent","higher_is_better":True},
 {"key":"run_stop_win_rate","label":"Run Stop Win Rate (ESPN)","category":"Run Defense","format":"percent","higher_is_better":True},
 {"key":"pass_rush_wins","label":"Pass Rush Wins (ESPN)","category":"Pass-Rush-Effizienz","format":"number","higher_is_better":True},
 {"key":"pass_rush_attempts","label":"Pass-Rush-Snaps (ESPN)","category":"Pass-Rush-Effizienz","format":"number","higher_is_better":True},
 {"key":"run_stop_wins","label":"Run Stop Wins (ESPN)","category":"Run Defense","format":"number","higher_is_better":True},
 {"key":"run_stop_attempts","label":"Run-Stop-Snaps (ESPN)","category":"Run Defense","format":"number","higher_is_better":True},
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

# ESPN Analytics DT leaderboard values reproduced by NFL Lines, through Week 10, 2026.
ESPN_DT_WIN_RATES = {
 "alim mcneill":{"pass_rush_win_rate":0.27,"pass_rush_wins":54,"pass_rush_attempts":200},
 "brandon dorlus":{"pass_rush_win_rate":0.26,"pass_rush_wins":28,"pass_rush_attempts":106},
 "maason smith":{"pass_rush_win_rate":0.25,"pass_rush_wins":31,"pass_rush_attempts":124},
 "aaron donald":{"pass_rush_win_rate":0.24,"pass_rush_wins":26,"pass_rush_attempts":107},
 "jeffery simmons":{"pass_rush_win_rate":0.24,"pass_rush_wins":39,"pass_rush_attempts":162},
 "levi drake rodriguez":{"pass_rush_win_rate":0.22,"pass_rush_wins":21,"pass_rush_attempts":94},
 "christian barmore":{"pass_rush_win_rate":0.21,"pass_rush_wins":22,"pass_rush_attempts":107},
 "zach allen":{"pass_rush_win_rate":0.20,"pass_rush_wins":35,"pass_rush_attempts":176},
 "milton williams":{"pass_rush_win_rate":0.19,"pass_rush_wins":28,"pass_rush_attempts":150},
 "vita vea":{"pass_rush_win_rate":0.19,"pass_rush_wins":24,"pass_rush_attempts":129},
 "osa odighizuwa":{"pass_rush_win_rate":0.19,"pass_rush_wins":28,"pass_rush_attempts":151},
 "arik armstead":{"pass_rush_win_rate":0.18,"pass_rush_wins":26,"pass_rush_attempts":141},
 "chris jones":{"pass_rush_win_rate":0.18,"pass_rush_wins":23,"pass_rush_attempts":130},
 "jalen redmond":{"pass_rush_win_rate":0.18,"pass_rush_wins":24,"pass_rush_attempts":136},
 "calijah kancey":{"pass_rush_win_rate":0.17,"pass_rush_wins":20,"pass_rush_attempts":115},
 "jonathan allen":{"pass_rush_win_rate":0.17,"pass_rush_wins":22,"pass_rush_attempts":127},
 "quinnen williams":{"pass_rush_win_rate":0.17,"pass_rush_wins":28,"pass_rush_attempts":163,"run_stop_win_rate":0.42,"run_stop_wins":61,"run_stop_attempts":143},
 "braden fiske":{"pass_rush_win_rate":0.17,"pass_rush_wins":19,"pass_rush_attempts":112},
 "dj reader":{"pass_rush_win_rate":0.17,"pass_rush_wins":17,"pass_rush_attempts":101},
 "adetomiwa adebawore":{"pass_rush_win_rate":0.17,"pass_rush_wins":20,"pass_rush_attempts":120},
 "dexter lawrence ii":{"pass_rush_win_rate":0.17,"pass_rush_wins":25,"pass_rush_attempts":150},
 "moro ojomo":{"pass_rush_win_rate":0.17,"pass_rush_wins":21,"pass_rush_attempts":126},
 "lacale london":{"run_stop_win_rate":0.46,"run_stop_wins":75,"run_stop_attempts":162},
 "mason graham":{"run_stop_win_rate":0.42,"run_stop_wins":51,"run_stop_attempts":121},
 "keeanu benton":{"run_stop_win_rate":0.41,"run_stop_wins":45,"run_stop_attempts":109},
 "malcolm roach":{"run_stop_win_rate":0.41,"run_stop_wins":45,"run_stop_attempts":110},
 "teair tart":{"run_stop_win_rate":0.40,"run_stop_wins":50,"run_stop_attempts":124},
 "dj jones":{"run_stop_win_rate":0.40,"run_stop_wins":54,"run_stop_attempts":135},
 "lee hunter":{"run_stop_win_rate":0.40,"run_stop_wins":45,"run_stop_attempts":114},
 "grady jarrett":{"run_stop_win_rate":0.40,"run_stop_wins":39,"run_stop_attempts":98},
 "jarran reed":{"run_stop_win_rate":0.40,"run_stop_wins":51,"run_stop_attempts":129}
}

# The published leaderboard keys contain spaces; normalize them to the same
# alphanumeric format used for player names before matching.
ESPN_DT_WIN_RATES = {re.sub(r"[^a-z0-9]", "", name.lower()): value for name, value in ESPN_DT_WIN_RATES.items()}

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
            "sacks_per_game": sacks / len(games[pid]) if sacks is not None and len(games[pid]) else None,
            "pressures_per_game": pressures / len(games[pid]) if pressures is not None and len(games[pid]) else None,
            "qb_hits_per_game": qb_hits / len(games[pid]) if qb_hits is not None and len(games[pid]) else None,
            "hurries_per_game": hurries / len(games[pid]) if hurries is not None and len(games[pid]) else None,
            "qb_hits_per_100_def_snaps": qb_hits / snaps * 100 if qb_hits is not None and snaps > 0 else None,
            "hurries_per_100_def_snaps": hurries / snaps * 100 if hurries is not None and snaps > 0 else None,
            "pressure_to_sack_rate": sacks / pressures if sacks is not None and pressures is not None and pressures > 0 else None,
            "tfls_per_100_def_snaps": pbp_tfls[pid] / snaps * 100 if snaps > 0 else None,
            "tfls": int(pbp_tfls[pid]), "forced_fumbles": int(forced_fumbles[pid]),
            "combined_tackles": combined, "solo_tackles": solo, "missed_tackles": missed,
            "missed_tackle_rate": missed / attempts if missed is not None and attempts > 0 else None,
            "pass_rush_snaps": None, "sack_rate": None, "pressure_rate": None,
            "quick_pressure_rate": None, "pass_rush_win_rate": None, "run_stop_win_rate": None,
            "pass_rush_wins": None, "pass_rush_attempts": None, "run_stop_wins": None, "run_stop_attempts": None,
            "double_team_rate": None,
            "negative_plays_forced": len(negative_play_ids[pid]),
            "negative_plays_forced_rate": len(negative_play_ids[pid]) / snaps if snaps > 0 else None
        }
        output.append(row)

    for player in output:
        espn = ESPN_DT_WIN_RATES.get(normalize_name(player["player_name"]))
        if espn:
            player.update(espn)

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
        "source": "nflverse PFR weekly defensive advanced stats + play-by-play + snap counts; ESPN Analytics DT win-rate leaderboard (through Week 10, reproduced by NFL Lines)",
        "source_url": DEF_URL, "snap_counts_url": SNAPS_URL,
        "espn_win_rates_source_url": "https://nfllines.com/defensive-line-ratings/players/",
        "espn_win_rates_through_week": 10,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "player_count": len(data), "players": data, "metrics": METRICS,
        "limitations": [
            "PFR is the single source for sacks, pressures, QB hits and hurries. TFLs and forced fumbles are player-attributed nflverse play-by-play events.",
            "Sack Rate and Pressure Rate remain blank until reliable player-level pass-rush snap counts are integrated; defensive snaps are not used as a substitute.",
            "QB Hit Rate, Hurry Rate and TFL rate are normalized per 100 defensive snaps, not per pass-rush snap; they measure overall defensive-snap frequency.",
            "Pressure-to-Sack Conversion is sacks divided by PFR pressures; per-game rates use games with defensive snaps in the PFR snap-count feed.",
            "ESPN DT pass-rush win rate is populated for the published top-20 leaderboard (including ties); run-stop win rate is populated for the published top-10 leaderboard. Values are through Week 10, 2026, as reproduced by NFL Lines; players outside the published lists remain null.",
            "0/1-technique name highlighting is enabled for explicit NT roster designations only. DTs are not guessed into a technique group without alignment-share data."
        ]
    }
    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"DT refresh OK: {len(data)} DT/NT players saved from {len(pbp):,} plays, {len(defense):,} PFR rows and {len(snaps):,} snap rows.")

if __name__ == "__main__":
    main()
